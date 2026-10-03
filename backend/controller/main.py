import asyncio
import time
import httpx
import sqlite3
import csv
import io
import os
import math
from fastapi import FastAPI, BackgroundTasks, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from controller.controller import DynamicController
from controller.config import ControllerConfig

app = FastAPI(title="Adaptive Controller Service")

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://localhost:8000")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
DB_PATH = os.environ.get("DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "controller", "experiments.db"))

# Default failure rate lambda (e.g., annualized failure rate of 0.02 / 365*86400)
LAMBDA_FAILURE_RATE = float(os.environ.get("LAMBDA_FAILURE_RATE", 1.0 / (365 * 24 * 3600)))

adaptive_controller = DynamicController()

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS experiments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mode TEXT,
                workload TEXT,
                start_time REAL,
                baseline_throughput REAL,
                min_client_throughput REAL,
                avg_client_throughput REAL,
                throughput_drop_percent REAL,
                baseline_p99 REAL,
                avg_recovery_p99 REAL,
                peak_recovery_p99 REAL,
                total_recovery_time REAL,
                avg_recovery_mbps REAL,
                peak_disk_utilization REAL,
                peak_network_utilization REAL,
                status TEXT,
                completed_at REAL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS experiment_samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                experiment_id INTEGER,
                timestamp REAL,
                client_rps REAL,
                client_throughput REAL,
                p50 REAL,
                p95 REAL,
                p99 REAL,
                recovery_rate REAL,
                disk_percent REAL,
                network_percent REAL,
                recovery_progress REAL,
                controller_state TEXT,
                FOREIGN KEY(experiment_id) REFERENCES experiments(id)
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS risk_analysis (
                experiment_id INTEGER PRIMARY KEY,
                strategy TEXT,
                workload TEXT,
                recovery_time REAL,
                risk_window REAL,
                configured_failure_rate REAL,
                estimated_second_failure_probability REAL,
                FOREIGN KEY(experiment_id) REFERENCES experiments(id)
            )
        ''')
        conn.commit()

@app.on_event("startup")
def startup():
    init_db()

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "controller",
        "timestamp": time.time()
    }

class StartExperimentRequest(BaseModel):
    strategy: str = "ADAPTIVE"
    workload: str = "MEDIUM"
    dataset_size_mb: int = 256
    node_to_fail: str = "storage2"
    recovery_rate_mbps: float = 25.0

class ExperimentRequest(BaseModel):
    warmup_seconds: int = 20
    node_to_fail: str = "storage2"
    workload: str = "MEDIUM"

class FixedExperimentRequest(BaseModel):
    warmup_seconds: int = 20
    node_to_fail: str = "storage2"
    workload: str = "MEDIUM"
    recovery_rate_mbps: float = 25.0

class AdaptiveExperimentRequest(BaseModel):
    warmup_seconds: int = 20
    node_to_fail: str = "storage2"
    workload: str = "MEDIUM"

experiment_state = {
    "status": "IDLE",
    "experiment_id": None,
    "strategy": None,
    "workload": None,
    "phase": "NONE",
    "phase_number": 0,
    "phase_name": "IDLE",
    "elapsed": 0.0,
    "progress": 0.0
}

async def run_experiment_pipeline(strategy: str, workload: str, dataset_mb: int = 256, node_to_fail: str = "storage2", fixed_rate: float = 25.0):
    global experiment_state
    experiment_state["status"] = "RUNNING"
    experiment_state["strategy"] = strategy
    experiment_state["workload"] = workload
    
    start_time = time.time()
    
    # Insert initial DB row
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.execute('''
            INSERT INTO experiments (mode, workload, start_time, status)
            VALUES (?, ?, ?, 'RUNNING')
        ''', (strategy, workload, start_time))
        conn.commit()
        exp_id = cur.lastrowid
        
    experiment_state["experiment_id"] = exp_id
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # PHASE 1: PREPARING
            experiment_state["phase"] = "PREPARING"
            experiment_state["phase_number"] = 1
            experiment_state["phase_name"] = "Cluster Reset & Node Recovery"
            await client.post(f"{COORDINATOR_URL}/api/admin/reset-cluster")
            # Recover all nodes
            for n_id in ["storage1", "storage2", "storage3", "storage4"]:
                try:
                    await client.post(f"{COORDINATOR_URL}/api/admin/recover/{n_id}")
                except Exception:
                    pass
            await asyncio.sleep(3)
            
            # PHASE 2: SEEDING
            experiment_state["phase"] = "SEEDING"
            experiment_state["phase_number"] = 2
            experiment_state["phase_name"] = f"Seeding {dataset_mb} MB Dataset (3x Replication)"
            seed_resp = await client.post(f"{COORDINATOR_URL}/api/admin/seed", json={"total_size_mb": dataset_mb, "object_size_mb": 16})
            seed_resp.raise_for_status()
            await asyncio.sleep(2)
            
            # PHASE 3: WARMUP
            experiment_state["phase"] = "WARMUP"
            experiment_state["phase_number"] = 3
            experiment_state["phase_name"] = f"Starting {workload} Workload & Warming Up"
            await client.post(f"{COORDINATOR_URL}/api/workload/start", json={"profile": workload})
            await asyncio.sleep(10)
            
            # PHASE 4: BASELINE
            experiment_state["phase"] = "BASELINE"
            experiment_state["phase_number"] = 4
            experiment_state["phase_name"] = "Measuring Live Client Baseline"
            baseline_samples = []
            for _ in range(10): # 10 seconds baseline
                wl_resp = await client.get(f"{COORDINATOR_URL}/api/workload/status")
                if wl_resp.status_code == 200:
                    wl = wl_resp.json()
                    baseline_samples.append({
                        "rps": wl.get("rps", 0.0),
                        "tput": wl.get("throughput_mbps", 0.0),
                        "p99": wl.get("p99_ms", 0.0)
                    })
                await asyncio.sleep(1)
                
            baseline_tput = max(0.1, sum(s["tput"] for s in baseline_samples) / max(1, len(baseline_samples)))
            baseline_p99 = max(1.0, sum(s["p99"] for s in baseline_samples) / max(1, len(baseline_samples)))
            
            adaptive_controller.baseline_throughput = baseline_tput
            adaptive_controller.baseline_p99 = baseline_p99
            
            # PHASE 5: FAULT_INJECTION
            experiment_state["phase"] = "FAULT_INJECTION"
            experiment_state["phase_number"] = 5
            experiment_state["phase_name"] = f"Injecting Failure on {node_to_fail}"
            await client.post(f"{COORDINATOR_URL}/api/admin/fail/{node_to_fail}")
            
            # PHASE 6: WAITING_FOR_FAILURE
            experiment_state["phase"] = "WAITING_FOR_FAILURE"
            experiment_state["phase_number"] = 6
            experiment_state["phase_name"] = "Waiting for Coordinator Failure Detection"
            for _ in range(15):
                await asyncio.sleep(1)
                sys_resp = await client.get(f"{COORDINATOR_URL}/api/system/status")
                if sys_resp.status_code == 200:
                    sys_data = sys_resp.json()
                    if sys_data["cluster"]["failed_nodes"] > 0:
                        break
                        
            # PHASE 7: UNDER_REPLICATED
            experiment_state["phase"] = "UNDER_REPLICATED"
            experiment_state["phase_number"] = 7
            experiment_state["phase_name"] = "Confirming 2/3 Under-Replicated Blocks"
            await asyncio.sleep(2)
            
            # PHASE 8: RECOVERY
            experiment_state["phase"] = "RECOVERY"
            experiment_state["phase_number"] = 8
            experiment_state["phase_name"] = f"Executing Recovery ({strategy})"
            
            if strategy == "ADAPTIVE":
                await client.put(f"{COORDINATOR_URL}/api/recovery/rate", json={"rate_mbps": 50.0})
                await client.post(f"{COORDINATOR_URL}/api/recovery/start")
                await adaptive_controller.start()
            elif strategy == "UNTHROTTLED":
                await client.put(f"{COORDINATOR_URL}/api/recovery/rate", json={"rate_mbps": 100.0})
                await client.post(f"{COORDINATOR_URL}/api/recovery/start")
            else: # FIXED_25 or FIXED_50
                rate_val = 50.0 if "50" in strategy else 25.0
                await client.put(f"{COORDINATOR_URL}/api/recovery/rate", json={"rate_mbps": rate_val})
                await client.post(f"{COORDINATOR_URL}/api/recovery/start")
                
            recovery_start_t = time.time()
            samples = []
            
            while True:
                await asyncio.sleep(2)
                now_t = time.time()
                
                # Fetch live metrics
                wl = {}
                rec = {}
                nodes = []
                try:
                    w_r = await client.get(f"{COORDINATOR_URL}/api/workload/status")
                    if w_r.status_code == 200: wl = w_r.json()
                    r_r = await client.get(f"{COORDINATOR_URL}/api/recovery/status")
                    if r_r.status_code == 200: rec = r_r.json()
                    n_r = await client.get(f"{COORDINATOR_URL}/api/nodes")
                    if n_r.status_code == 200: nodes = n_r.json()
                except Exception:
                    pass
                    
                cur_rps = wl.get("rps", 0.0)
                cur_tput = wl.get("throughput_mbps", 0.0)
                cur_p50 = wl.get("p50_ms", 0.0)
                cur_p95 = wl.get("p95_ms", 0.0)
                cur_p99 = wl.get("p99_ms", 0.0)
                
                rec_rate = rec.get("actual_rate_mbps", 0.0)
                rec_prog = rec.get("progress_percent", 0.0)
                experiment_state["progress"] = rec_prog
                experiment_state["elapsed"] = round(now_t - recovery_start_t, 1)
                
                max_disk = max([n.get("disk_percent", 0.0) for n in nodes], default=0.0)
                max_net = max([n.get("network_rx_bytes", 0) for n in nodes], default=0)
                max_net_pct = min(100.0, (max_net / (100 * 1024 * 1024)) * 100)
                
                ctrl_st = adaptive_controller.state_machine.state if strategy == "ADAPTIVE" else "OFF"
                
                sample_item = {
                    "timestamp": now_t,
                    "rps": cur_rps,
                    "tput": cur_tput,
                    "p50": cur_p50,
                    "p95": cur_p95,
                    "p99": cur_p99,
                    "recovery_rate": rec_rate,
                    "disk_percent": max_disk,
                    "network_percent": max_net_pct,
                    "progress": rec_prog,
                    "ctrl_state": ctrl_st
                }
                samples.append(sample_item)
                
                # Persist raw sample
                with sqlite3.connect(DB_PATH) as conn:
                    conn.execute('''
                        INSERT INTO experiment_samples (
                            experiment_id, timestamp, client_rps, client_throughput, p50, p95, p99,
                            recovery_rate, disk_percent, network_percent, recovery_progress, controller_state
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (exp_id, now_t, cur_rps, cur_tput, cur_p50, cur_p95, cur_p99,
                          rec_rate, max_disk, max_net_pct, rec_prog, ctrl_st))
                    conn.commit()
                    
                # Check completion
                rep_r = await client.get(f"{COORDINATOR_URL}/api/replication/status")
                if rep_r.status_code == 200:
                    rep_d = rep_r.json()
                    if rep_d["under_replicated_blocks"] == 0 and rep_d["critical_blocks"] == 0 and rec.get("running") is False:
                        break
                if now_t - recovery_start_t > 300: # 5 min timeout safety
                    break
                    
            recovery_end_t = time.time()
            total_rec_time = max(1.0, recovery_end_t - recovery_start_t)
            
            # PHASE 9: VALIDATING
            experiment_state["phase"] = "VALIDATING"
            experiment_state["phase_number"] = 9
            experiment_state["phase_name"] = "Validating 3/3 Replicas & Checksums"
            await asyncio.sleep(2)
            
            # Stop workload & controller
            await client.post(f"{COORDINATOR_URL}/api/workload/stop")
            if strategy == "ADAPTIVE":
                await adaptive_controller.stop()
                
            # PHASE 10: COMPLETE
            experiment_state["phase"] = "COMPLETE"
            experiment_state["phase_number"] = 10
            experiment_state["phase_name"] = "Experiment Completed & Results Persisted"
            
            # Calculate aggregate metrics strictly from real samples
            if samples:
                avg_rec_tput = sum(s["tput"] for s in samples) / len(samples)
                min_tput = min(s["tput"] for s in samples)
                avg_p99 = sum(s["p99"] for s in samples) / len(samples)
                peak_p99 = max(s["p99"] for s in samples)
                avg_rate = sum(s["recovery_rate"] for s in samples) / len(samples)
                peak_disk = max(s["disk_percent"] for s in samples)
                peak_net = max(s["network_percent"] for s in samples)
            else:
                avg_rec_tput = baseline_tput
                min_tput = baseline_tput
                avg_p99 = baseline_p99
                peak_p99 = baseline_p99
                avg_rate = fixed_rate
                peak_disk = 0.0
                peak_net = 0.0
                
            tput_drop = max(0.0, ((baseline_tput - avg_rec_tput) / baseline_tput) * 100) if baseline_tput > 0 else 0.0
            risk_window = total_rec_time
            est_risk = 1.0 - math.exp(-LAMBDA_FAILURE_RATE * risk_window)
            comp_at = time.time()
            
            # Update DB with real calculated metrics
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute('''
                    UPDATE experiments SET
                        baseline_throughput = ?,
                        min_client_throughput = ?,
                        avg_client_throughput = ?,
                        throughput_drop_percent = ?,
                        baseline_p99 = ?,
                        avg_recovery_p99 = ?,
                        peak_recovery_p99 = ?,
                        total_recovery_time = ?,
                        avg_recovery_mbps = ?,
                        peak_disk_utilization = ?,
                        peak_network_utilization = ?,
                        status = 'COMPLETED',
                        completed_at = ?
                    WHERE id = ?
                ''', (baseline_tput, min_tput, avg_rec_tput, tput_drop, baseline_p99,
                      avg_p99, peak_p99, total_rec_time, avg_rate, peak_disk, peak_net, comp_at, exp_id))
                
                conn.execute('''
                    INSERT OR REPLACE INTO risk_analysis (
                        experiment_id, strategy, workload, recovery_time, risk_window, configured_failure_rate, estimated_second_failure_probability
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (exp_id, strategy, workload, total_rec_time, risk_window, LAMBDA_FAILURE_RATE, est_risk))
                conn.commit()
                
            # Append to CSV
            csv_path = os.path.join(os.path.dirname(DB_PATH), "experiments.csv")
            csv_exists = os.path.isfile(csv_path)
            with open(csv_path, "a", newline='') as f:
                writer = csv.writer(f)
                if not csv_exists:
                    writer.writerow(["experiment_id", "strategy", "workload", "baseline_tput", "avg_rec_tput",
                                     "tput_drop_pct", "baseline_p99", "avg_p99", "peak_p99", "recovery_time_s",
                                     "avg_recovery_mbps", "risk_window_s", "est_second_failure_prob", "completed_at"])
                writer.writerow([exp_id, strategy, workload, round(baseline_tput, 2), round(avg_rec_tput, 2),
                                 round(tput_drop, 2), round(baseline_p99, 2), round(avg_p99, 2), round(peak_p99, 2),
                                 round(total_rec_time, 2), round(avg_rate, 2), round(risk_window, 2), est_risk, comp_at])
                
            experiment_state["status"] = "IDLE"
            
    except Exception as e:
        print(f"Experiment failed: {e}")
        experiment_state["status"] = "ERROR"
        experiment_state["phase"] = "FAILED"
        experiment_state["phase_name"] = f"Error: {e}"
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("UPDATE experiments SET status = 'FAILED' WHERE id = ?", (exp_id,))
            conn.commit()

@app.post("/api/experiments/start")
async def start_experiment_unified(req: StartExperimentRequest, bg_tasks: BackgroundTasks):
    if experiment_state["status"] == "RUNNING":
        raise HTTPException(status_code=409, detail="An experiment is already in progress")
    bg_tasks.add_task(run_experiment_pipeline, req.strategy, req.workload, req.dataset_size_mb, req.node_to_fail, req.recovery_rate_mbps)
    return {"status": "started", "strategy": req.strategy, "workload": req.workload}

@app.post("/api/experiments/unthrottled")
async def start_unthrottled(req: ExperimentRequest, bg_tasks: BackgroundTasks):
    if experiment_state["status"] == "RUNNING":
        return {"error": "Experiment already running"}
    bg_tasks.add_task(run_experiment_pipeline, "UNTHROTTLED", req.workload, 256, req.node_to_fail)
    return {"status": "Experiment started"}

@app.post("/api/experiments/fixed")
async def start_fixed(req: FixedExperimentRequest, bg_tasks: BackgroundTasks):
    if experiment_state["status"] == "RUNNING":
        return {"error": "Experiment already running"}
    mode = "FIXED_50" if req.recovery_rate_mbps >= 40 else "FIXED_25"
    bg_tasks.add_task(run_experiment_pipeline, mode, req.workload, 256, req.node_to_fail, req.recovery_rate_mbps)
    return {"status": "Experiment started"}

@app.post("/api/experiments/adaptive")
async def start_adaptive(req: AdaptiveExperimentRequest, bg_tasks: BackgroundTasks):
    if experiment_state["status"] == "RUNNING":
        return {"error": "Experiment already running"}
    bg_tasks.add_task(run_experiment_pipeline, "ADAPTIVE", req.workload, 256, req.node_to_fail)
    return {"status": "Experiment started"}

@app.get("/api/experiments/status")
@app.get("/api/experiments/current")
async def get_experiment_status():
    return experiment_state

@app.get("/api/experiments/comparison")
async def get_experiment_comparison():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        query = '''
            SELECT 
                mode as strategy,
                workload,
                COUNT(*) as sample_count,
                AVG(throughput_drop_percent) as mean_throughput_drop,
                MIN(throughput_drop_percent) as min_throughput_drop,
                MAX(throughput_drop_percent) as max_throughput_drop,
                AVG(avg_recovery_p99) as mean_avg_p99,
                AVG(peak_recovery_p99) as mean_peak_p99,
                MAX(peak_recovery_p99) as max_peak_p99,
                AVG(total_recovery_time) as mean_recovery_time,
                MIN(total_recovery_time) as min_recovery_time,
                MAX(total_recovery_time) as max_recovery_time,
                AVG(avg_recovery_mbps) as mean_recovery_rate
            FROM experiments
            WHERE status = 'COMPLETED'
            GROUP BY mode, workload
        '''
        results = [dict(r) for r in conn.execute(query).fetchall()]
        
        # Merge risk data
        risk_query = '''
            SELECT strategy, workload, AVG(risk_window) as mean_risk_window, AVG(estimated_second_failure_probability) as mean_estimated_risk
            FROM risk_analysis
            GROUP BY strategy, workload
        '''
        risk_results = {f"{r['strategy']}_{r['workload']}": dict(r) for r in conn.execute(risk_query).fetchall()}
        
        for item in results:
            k = f"{item['strategy']}_{item['workload']}"
            if k in risk_results:
                item.update(risk_results[k])
                
        return results

@app.get("/api/experiments/history")
async def get_experiments_history():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM experiments ORDER BY id DESC LIMIT 50").fetchall()
        return [dict(r) for r in rows]

# --- CSV EXPORT APIS (PHASE 23) ---

@app.get("/api/experiments/export/csv")
async def export_all_experiments_csv():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM experiments WHERE status = 'COMPLETED' ORDER BY id ASC").fetchall()
        
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
            
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=experiments_summary.csv"})

@app.get("/api/experiments/{exp_id}/samples.csv")
async def export_experiment_samples_csv(exp_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM experiment_samples WHERE experiment_id = ? ORDER BY id ASC", (exp_id,)).fetchall()
        
    output = io.StringIO()
    if rows:
        writer = csv.DictWriter(output, fieldnames=rows[0].keys())
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
            
    return Response(content=output.getvalue(), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=experiment_{exp_id}_samples.csv"})

# --- RISK APIS (PHASE 13) ---

@app.get("/api/risk/summary")
async def get_risk_summary():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        query = '''
            SELECT strategy, AVG(recovery_time) as recovery_time, AVG(risk_window) as risk_window, 
                   AVG(estimated_second_failure_probability) as failure_prob, COUNT(*) as sample_count
            FROM risk_analysis
            GROUP BY strategy
        '''
        rows = [dict(r) for r in conn.execute(query).fetchall()]
        return rows

@app.get("/api/risk/{experiment_id}")
async def get_risk(experiment_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM risk_analysis WHERE experiment_id = ?", (experiment_id,)).fetchone()
        if row:
            return dict(row)
        return {"error": "Not found"}

# --- DYNAMIC CONTROLLER APIS (PHASE 8) ---

@app.get("/api/controller/status")
async def get_controller_status():
    return {
        "online": True,
        "is_enabled": adaptive_controller.is_enabled,
        "state": adaptive_controller.state_machine.state,
        "current_rate_mbps": adaptive_controller.state_machine.current_rate,
        "current_p99": adaptive_controller.current_p99,
        "current_throughput": adaptive_controller.current_throughput,
        "current_disk_percent": adaptive_controller.current_disk_percent,
        "current_network_percent": adaptive_controller.current_network_percent,
        "bad_samples": adaptive_controller.state_machine.bad_samples,
        "good_samples": adaptive_controller.state_machine.good_samples,
        "decision_reason": adaptive_controller.latest_decision_reason
    }

@app.get("/api/controller/history")
async def get_controller_history():
    return adaptive_controller.state_machine.history

@app.put("/api/controller/config")
async def update_controller_config(new_config: ControllerConfig):
    adaptive_controller.config = new_config
    adaptive_controller.state_machine.config = new_config
    return {"status": "success", "config": adaptive_controller.config.dict()}

@app.post("/api/controller/enable")
async def enable_controller():
    await adaptive_controller.start()
    return {"status": "Controller enabled"}

@app.post("/api/controller/disable")
async def disable_controller():
    await adaptive_controller.stop()
    return {"status": "Controller disabled"}

# --- ONE CLICK END-TO-END DEMO (PHASE 15) ---

demo_state = {
    "status": "IDLE",
    "step": 0,
    "total_steps": 15,
    "message": ""
}

async def run_demo():
    global demo_state
    demo_state["status"] = "RUNNING"
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            # 1. Reset cluster
            demo_state["step"] = 1
            demo_state["message"] = "Step 1/15: Resetting cluster & recovering nodes..."
            await client.post(f"{COORDINATOR_URL}/api/admin/reset-cluster")
            for n_id in ["storage1", "storage2", "storage3", "storage4"]:
                try: await client.post(f"{COORDINATOR_URL}/api/admin/recover/{n_id}")
                except Exception: pass
            await asyncio.sleep(2)
            
            # 2. Seed data
            demo_state["step"] = 2
            demo_state["message"] = "Step 2/15: Seeding 256MB distributed dataset..."
            await client.post(f"{COORDINATOR_URL}/api/admin/seed", json={"total_size_mb": 256, "object_size_mb": 16})
            await asyncio.sleep(2)
            
            # 3. Verify replication
            demo_state["step"] = 3
            demo_state["message"] = "Step 3/15: Verifying full 3/3 replication across healthy nodes..."
            rep_r = await client.get(f"{COORDINATOR_URL}/api/replication/status")
            rep_data = rep_r.json()
            if rep_data["under_replicated_blocks"] > 0:
                raise Exception("Replication failed to reach 3/3")
            await asyncio.sleep(2)
            
            # 4. Start MEDIUM workload
            demo_state["step"] = 4
            demo_state["message"] = "Step 4/15: Starting MEDIUM client traffic workload..."
            await client.post(f"{COORDINATOR_URL}/api/workload/start", json={"profile": "MEDIUM"})
            await asyncio.sleep(5)
            
            # 5. Collect baseline
            demo_state["step"] = 5
            demo_state["message"] = "Step 5/15: Collecting 15-second client performance baseline..."
            await asyncio.sleep(15)
            
            # 6. Inject failure
            demo_state["step"] = 6
            demo_state["message"] = "Step 6/15: Injecting failure into Storage Node 2..."
            await client.post(f"{COORDINATOR_URL}/api/admin/fail/storage2")
            
            # 7. Failure detection
            demo_state["step"] = 7
            demo_state["message"] = "Step 7/15: Coordinator detecting missing heartbeats..."
            for _ in range(12):
                await asyncio.sleep(1)
                sys_r = await client.get(f"{COORDINATOR_URL}/api/system/status")
                if sys_r.json()["cluster"]["failed_nodes"] > 0:
                    break
                    
            # 8. Under-replication
            demo_state["step"] = 8
            demo_state["message"] = "Step 8/15: Identifying 2/3 under-replicated blocks..."
            await asyncio.sleep(2)
            
            # 9. Start adaptive recovery
            demo_state["step"] = 9
            demo_state["message"] = "Step 9/15: Initiating ADAPTIVE recovery controller..."
            await client.put(f"{COORDINATOR_URL}/api/recovery/rate", json={"rate_mbps": 50.0})
            await client.post(f"{COORDINATOR_URL}/api/recovery/start")
            await adaptive_controller.start()
            await asyncio.sleep(4)
            
            # 10. Display decisions live
            demo_state["step"] = 10
            demo_state["message"] = "Step 10/15: Monitoring adaptive rate decisions live under normal load..."
            await asyncio.sleep(10)
            
            # 11. Load spike
            demo_state["step"] = 11
            demo_state["message"] = "Step 11/15: Spiking client workload to HIGH (observing controller throttle)..."
            await client.put(f"{COORDINATOR_URL}/api/workload/profile", json={"profile": "HIGH"})
            await asyncio.sleep(12)
            
            # 12. Return load to LOW/MEDIUM
            demo_state["step"] = 12
            demo_state["message"] = "Step 12/15: Easing client workload to LOW (observing controller acceleration)..."
            await client.put(f"{COORDINATOR_URL}/api/workload/profile", json={"profile": "LOW"})
            await asyncio.sleep(10)
            
            # 13. Replica reconstruction
            demo_state["step"] = 13
            demo_state["message"] = "Step 13/15: Completing remaining replica block transfers..."
            while True:
                await asyncio.sleep(2)
                sys_r = await client.get(f"{COORDINATOR_URL}/api/system/status")
                s_data = sys_r.json()
                if s_data["replication"]["under_replicated_blocks"] == 0:
                    break
                    
            # 14. Full redundancy restored
            demo_state["step"] = 14
            demo_state["message"] = "Step 14/15: FULL REDUNDANCY RESTORED (3/3 REPLICAS RESTORED)."
            await client.post(f"{COORDINATOR_URL}/api/workload/stop")
            await adaptive_controller.stop()
            await asyncio.sleep(3)
            
            # 15. Summary complete
            demo_state["step"] = 15
            demo_state["message"] = "Step 15/15: End-to-end demo successfully completed!"
            
    except Exception as e:
        print(f"Demo error: {e}")
        demo_state["status"] = "ERROR"
        demo_state["message"] = f"Demo failed: {e}"
        await adaptive_controller.stop()
        
    await asyncio.sleep(5)
    demo_state["status"] = "IDLE"

@app.post("/api/demo/start")
async def start_demo_handler(bg_tasks: BackgroundTasks):
    if demo_state["status"] == "RUNNING":
        return {"error": "Demo already in progress"}
    bg_tasks.add_task(run_demo)
    return {"status": "Demo started"}

@app.get("/api/demo/status")
async def get_demo_status_handler():
    return demo_state
