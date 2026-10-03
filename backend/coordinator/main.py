from fastapi import FastAPI, HTTPException, Request, Depends
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST, Counter, Gauge, Histogram
from fastapi.responses import StreamingResponse, Response
import os
import time
import asyncio
import datetime
import httpx
import uuid
import hashlib
import json
from pydantic import BaseModel
from typing import List

try:
    from coordinator.database import init_db, get_db
    from coordinator.workload import WorkloadManager
except ModuleNotFoundError:
    from database import init_db, get_db
    from workload import WorkloadManager
from recovery.recovery_worker import RecoveryWorker

app = FastAPI(title="Coordinator Service")

SERVICE_NAME = os.getenv("SERVICE_NAME", "coordinator")
REPLICATION_FACTOR = int(os.getenv("REPLICATION_FACTOR", "3"))
BLOCK_SIZE_MB = int(os.getenv("BLOCK_SIZE_MB", "4"))
BLOCK_SIZE_BYTES = BLOCK_SIZE_MB * 1024 * 1024
FAILURE_THRESHOLD = int(os.getenv("FAILURE_THRESHOLD", "3"))
POLL_INTERVAL = 2.0

# --- PROMETHEUS METRICS ---
client_requests_total = Counter('client_requests_total', 'Total client requests', ['method', 'endpoint'])
client_latency_seconds = Histogram('client_latency_seconds', 'Client latency', ['method', 'endpoint'])

@app.middleware("http")
async def prometheus_middleware(request: Request, call_next):
    method = request.method
    # basic route path matching for prometheus
    path = request.url.path
    if path.startswith("/api/data/"):
        endpoint = "/api/data/{object_id}"
    else:
        endpoint = path
        
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    if path not in ["/health", "/metrics", "/api/replication/status", "/api/recovery/status"]:
        client_requests_total.labels(method=method, endpoint=endpoint).inc()
        client_latency_seconds.labels(method=method, endpoint=endpoint).observe(process_time)
        
    return response

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

recovery_worker = RecoveryWorker(get_db)
workload_manager = WorkloadManager()

DEFAULT_STORAGE_NODES = [
    ("storage1", "http://localhost:8001"),
    ("storage2", "http://localhost:8002"),
    ("storage3", "http://localhost:8004"),
    ("storage4", "http://localhost:8005"),
]

@app.on_event("startup")
async def startup_event():
    await init_db()
    # Pre-register default cluster storage nodes
    db = await get_db()
    try:
        now = time.time()
        for node_id, url in DEFAULT_STORAGE_NODES:
            await db.execute('''
                INSERT INTO nodes (node_id, url, status, last_heartbeat, consecutive_failures, created_at)
                VALUES (?, ?, 'INITIALIZING', ?, 0, ?)
                ON CONFLICT(node_id) DO UPDATE SET url=excluded.url
            ''', (node_id, url, now, now))
        await db.commit()
    finally:
        await db.close()
    asyncio.create_task(failure_detector())

class NodeRegistration(BaseModel):
    node_id: str
    url: str

async def log_event(db, event_type: str, details: dict):
    now = time.time()
    await db.execute('''
        INSERT INTO events (event_type, details, created_at)
        VALUES (?, ?, ?)
    ''', (event_type, json.dumps(details), now))
    print(f"EVENT [{event_type}]: {details}")

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

# --- NODE MANAGEMENT ---

@app.post("/api/nodes/register")
@app.post("/nodes/register")
async def register_node(node: NodeRegistration):
    db = await get_db()
    try:
        now = time.time()
        await db.execute('''
            INSERT INTO nodes (node_id, url, status, last_heartbeat, consecutive_failures, created_at)
            VALUES (?, ?, 'HEALTHY', ?, 0, ?)
            ON CONFLICT(node_id) DO UPDATE SET
            url=excluded.url,
            status='HEALTHY',
            last_heartbeat=excluded.last_heartbeat,
            consecutive_failures=0
        ''', (node.node_id, node.url, now, now))
        await db.commit()
        return {"status": "registered", "node_id": node.node_id}
    finally:
        await db.close()

# We keep this just in case, but rely on polling
@app.post("/api/nodes/{node_id}/heartbeat")
@app.post("/nodes/{node_id}/heartbeat")
async def node_heartbeat(node_id: str):
    db = await get_db()
    try:
        now = time.time()
        cursor = await db.execute('''
            UPDATE nodes SET last_heartbeat=?, status="HEALTHY", consecutive_failures=0
            WHERE node_id=?
        ''', (now, node_id))
        await db.commit()
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="Node not registered")
        return {"status": "ok"}
    finally:
        await db.close()

async def failure_detector():
    """Background task to poll nodes and detect failures."""
    while True:
        try:
            db = await get_db()
            async with db.execute('SELECT node_id, url, status, consecutive_failures FROM nodes') as cur:
                nodes = await cur.fetchall()
                
            now = time.time()
            async with httpx.AsyncClient(timeout=1.0) as client:
                for node in nodes:
                    node_id = node['node_id']
                    url = node['url']
                    status = node['status']
                    failures = node['consecutive_failures']
                    
                    is_healthy = False
                    try:
                        resp = await client.get(f"{url}/health")
                        if resp.status_code == 200:
                            is_healthy = True
                    except Exception:
                        if "localhost" in url:
                            try:
                                alt_url = url.replace("localhost", "127.0.0.1")
                                resp = await client.get(f"{alt_url}/health")
                                if resp.status_code == 200:
                                    is_healthy = True
                            except Exception:
                                pass
                        
                    if is_healthy:
                        if status == 'FAILED':
                            # Node returning from failure -> Enter RECONCILING
                            await log_event(db, "NODE_RECONCILING", {"node_id": node_id})
                            try:
                                blocks_resp = await client.get(f"{url}/blocks")
                                if blocks_resp.status_code == 200:
                                    physical_blocks = blocks_resp.json().get("blocks", [])
                                    for pb_id in physical_blocks:
                                        # Check how many healthy replicas exist on OTHER nodes
                                        async with db.execute('''
                                            SELECT COUNT(*) as c FROM block_replicas r
                                            JOIN nodes n ON r.node_id = n.node_id
                                            WHERE r.block_id = ? AND r.node_id != ? AND r.replica_status = 'STORED' AND n.status = 'HEALTHY'
                                        ''', (pb_id, node_id)) as rep_cur:
                                            other_reps = (await rep_cur.fetchone())['c']
                                            
                                        if other_reps >= REPLICATION_FACTOR:
                                            # System already has 3 healthy replicas elsewhere!
                                            # This block is EXCESS. Delete it to prevent 4/3 replicas.
                                            try:
                                                await client.delete(f"{url}/blocks/{pb_id}")
                                            except Exception:
                                                pass
                                            await db.execute('DELETE FROM block_replicas WHERE block_id=? AND node_id=?', (pb_id, node_id))
                                        else:
                                            # Valid replica, restore to STORED
                                            await db.execute('''
                                                INSERT INTO block_replicas (block_id, node_id, replica_status, created_at)
                                                VALUES (?, ?, 'STORED', ?)
                                                ON CONFLICT(block_id, node_id) DO UPDATE SET replica_status='STORED'
                                            ''', (pb_id, node_id, now))
                            except Exception as recon_err:
                                print(f"Error during node reconciliation for {node_id}: {recon_err}")
                            await log_event(db, "NODE_RECOVERED", {"node_id": node_id, "reconciled": True})
                            
                        await db.execute('''
                            UPDATE nodes SET status='HEALTHY', consecutive_failures=0, last_heartbeat=?
                            WHERE node_id=?
                        ''', (now, node_id))
                    else:
                        new_failures = failures + 1
                        new_status = 'SUSPECTED' if new_failures < FAILURE_THRESHOLD else 'FAILED'
                        
                        await db.execute('''
                            UPDATE nodes SET status=?, consecutive_failures=?, last_heartbeat=?
                            WHERE node_id=?
                        ''', (new_status, new_failures, now, node_id))
                        
                        if status != 'FAILED' and new_status == 'FAILED':
                            # Transition to FAILED
                            await log_event(db, "NODE_FAILURE_DETECTED", {"node_id": node_id})
                            
                            # Mark replicas unavailable
                            await db.execute('''
                                UPDATE block_replicas SET replica_status='UNAVAILABLE'
                                WHERE node_id=?
                            ''', (node_id,))
                            
                            # Identify affected blocks
                            async with db.execute('''
                                SELECT block_id FROM block_replicas WHERE node_id=?
                            ''', (node_id,)) as affected_cur:
                                affected_blocks = [r['block_id'] for r in await affected_cur.fetchall()]
                                
                            for b_id in affected_blocks:
                                await log_event(db, "BLOCK_UNDER_REPLICATED", {"block_id": b_id, "failed_node": node_id})
                                
                            if affected_blocks:
                                await log_event(db, "RECOVERY_STARTED", {"trigger": "NODE_FAILURE", "node_id": node_id})
                                
            await db.commit()
            await db.close()
        except Exception as e:
            print(f"Failure detector error: {e}")
        
        await asyncio.sleep(POLL_INTERVAL)

# --- ADMIN APIS ---

@app.post("/api/admin/fail/{node_id}")
async def admin_fail_node(node_id: str):
    db = await get_db()
    try:
        async with db.execute('SELECT url FROM nodes WHERE node_id=?', (node_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Node not found")
        
        url = row['url']
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{url}/admin/fail")
            return resp.json()
    finally:
        await db.close()

@app.post("/api/admin/recover/{node_id}")
async def admin_recover_node(node_id: str):
    db = await get_db()
    try:
        async with db.execute('SELECT url FROM nodes WHERE node_id=?', (node_id,)) as cur:
            row = await cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Node not found")
        
        url = row['url']
        async with httpx.AsyncClient() as client:
            resp = await client.post(f"{url}/admin/recover")
            return resp.json()
    finally:
        await db.close()
        
@app.post("/api/admin/reset-cluster")
async def admin_reset_cluster():
    db = await get_db()
    try:
        await workload_manager.stop()
        await recovery_worker.stop()
        await db.execute('DELETE FROM events')
        await db.execute('DELETE FROM block_replicas')
        await db.execute('DELETE FROM blocks')
        await db.execute('DELETE FROM objects')
        await db.execute('DELETE FROM recovery_jobs')
        await db.commit()
        return {"status": "cluster reset"}
    finally:
        await db.close()

class SeedRequest(BaseModel):
    total_size_mb: int = 512
    object_size_mb: int = 16

@app.post("/api/admin/seed")
async def seed_dataset(req: SeedRequest):
    db = await get_db()
    now = time.time()
    try:
        async with db.execute('SELECT node_id, url FROM nodes WHERE status = "HEALTHY"') as cur:
            active_nodes = [dict(r) for r in await cur.fetchall()]
            
        if len(active_nodes) < REPLICATION_FACTOR:
            raise HTTPException(status_code=503, detail=f"Need at least {REPLICATION_FACTOR} healthy nodes to seed, found {len(active_nodes)}")

        total_mb = max(16, req.total_size_mb)
        obj_size_mb = max(4, req.object_size_mb)
        num_objects = max(1, total_mb // obj_size_mb)
        obj_bytes = obj_size_mb * 1024 * 1024
        
        seeded_objects = 0
        seeded_blocks = 0
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            for obj_idx in range(num_objects):
                obj_id = f"dataset-obj-{obj_idx+1}"
                await db.execute('DELETE FROM objects WHERE object_id = ?', (obj_id,))
                await db.execute('INSERT INTO objects (object_id, size_bytes, created_at) VALUES (?, ?, ?)',
                                 (obj_id, obj_bytes, now))
                seeded_objects += 1
                
                for blk_idx in range(0, obj_bytes, BLOCK_SIZE_BYTES):
                    chunk_size = min(BLOCK_SIZE_BYTES, obj_bytes - blk_idx)
                    block_data = os.urandom(chunk_size)
                    block_id = f"{obj_id}-blk-{blk_idx // BLOCK_SIZE_BYTES}"
                    checksum = hashlib.sha256(block_data).hexdigest()
                    
                    await db.execute('''
                        INSERT INTO blocks (block_id, object_id, block_index, size_bytes, checksum, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        ON CONFLICT(block_id) DO UPDATE SET checksum=excluded.checksum, size_bytes=excluded.size_bytes
                    ''', (block_id, obj_id, blk_idx // BLOCK_SIZE_BYTES, chunk_size, checksum, now))
                    
                    offset = (obj_idx + (blk_idx // BLOCK_SIZE_BYTES)) % len(active_nodes)
                    selected_nodes = [active_nodes[(offset + i) % len(active_nodes)] for i in range(REPLICATION_FACTOR)]
                    
                    for node in selected_nodes:
                        try:
                            resp = await client.post(f"{node['url']}/blocks/{block_id}", content=block_data)
                            resp.raise_for_status()
                            await db.execute('''
                                INSERT INTO block_replicas (block_id, node_id, replica_status, created_at)
                                VALUES (?, ?, 'STORED', ?)
                                ON CONFLICT(block_id, node_id) DO UPDATE SET replica_status='STORED'
                            ''', (block_id, node["node_id"], now))
                        except Exception as e:
                            print(f"Error seeding block {block_id} to {node['node_id']}: {e}")
                    seeded_blocks += 1
                    
        await db.commit()
        await log_event(db, "DATASET_SEEDED", {"total_mb": total_mb, "objects": seeded_objects, "blocks": seeded_blocks})
        return {
            "status": "success",
            "total_size_mb": total_mb,
            "objects_seeded": seeded_objects,
            "blocks_seeded": seeded_blocks
        }
    finally:
        await db.close()

# --- WORKLOAD APIS ---

class WorkloadStartRequest(BaseModel):
    profile: str = "LOW"

class WorkloadProfileRequest(BaseModel):
    profile: str = "HIGH"

@app.post("/api/workload/start")
async def start_workload(req: WorkloadStartRequest):
    await workload_manager.start(req.profile)
    db = await get_db()
    try:
        await log_event(db, "WORKLOAD_STARTED", {"profile": req.profile})
    finally:
        await db.close()
    return {"status": "started", "profile": req.profile}

@app.post("/api/workload/stop")
async def stop_workload():
    await workload_manager.stop()
    db = await get_db()
    try:
        await log_event(db, "WORKLOAD_STOPPED", {})
    finally:
        await db.close()
    return {"status": "stopped"}

@app.put("/api/workload/profile")
async def update_workload_profile(req: WorkloadProfileRequest):
    await workload_manager.set_profile(req.profile)
    db = await get_db()
    try:
        await log_event(db, "WORKLOAD_CHANGED", {"profile": req.profile})
    finally:
        await db.close()
    return {"status": "updated", "profile": req.profile}

@app.get("/api/workload/status")
async def get_workload_status():
    return workload_manager.get_status()

# --- CENTRAL SYSTEM STATUS API (PHASE 1) ---

@app.get("/api/system/status")
async def get_system_status():
    db = await get_db()
    try:
        async with db.execute('SELECT node_id, status FROM nodes') as cur:
            nodes = await cur.fetchall()
            total_nodes = len(nodes)
            healthy_nodes = sum(1 for n in nodes if n["status"] == "HEALTHY")
            failed_nodes = sum(1 for n in nodes if n["status"] != "HEALTHY")

        rep_status = await get_replication_status()
        wl_status = workload_manager.get_status()
        rec_status = recovery_worker.get_status()
        
        ctrl_url = os.environ.get("CONTROLLER_URL", "http://localhost:8003")
        ctrl_status = {"online": False, "enabled": False, "state": "OFFLINE", "current_rate_mbps": None, "decision_reason": None}
        exp_status = {"running": False, "experiment_id": None, "strategy": None, "workload": None, "phase": None}
        
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                c_resp = None
                try:
                    c_resp = await client.get(f"{ctrl_url}/api/controller/status")
                except Exception:
                    if "localhost" in ctrl_url:
                        alt_ctrl = ctrl_url.replace("localhost", "127.0.0.1")
                        try:
                            c_resp = await client.get(f"{alt_ctrl}/api/controller/status")
                        except Exception:
                            pass
                    elif "127.0.0.1" in ctrl_url:
                        alt_ctrl = ctrl_url.replace("127.0.0.1", "localhost")
                        try:
                            c_resp = await client.get(f"{alt_ctrl}/api/controller/status")
                        except Exception:
                            pass

                if c_resp and c_resp.status_code == 200:
                    c_data = c_resp.json()
                    ctrl_status = {
                        "online": True,
                        "enabled": c_data.get("is_enabled", False),
                        "state": c_data.get("state", "IDLE"),
                        "current_rate_mbps": c_data.get("current_rate_mbps"),
                        "decision_reason": c_data.get("decision_reason")
                    }

                e_resp = None
                try:
                    e_resp = await client.get(f"{ctrl_url}/api/experiments/status")
                except Exception:
                    pass
                if e_resp and e_resp.status_code == 200:
                    e_data = e_resp.json()
                    exp_status = {
                        "running": e_data.get("status") == "RUNNING",
                        "experiment_id": e_data.get("experiment_id"),
                        "strategy": e_data.get("strategy"),
                        "workload": e_data.get("workload"),
                        "phase": e_data.get("phase")
                    }
        except Exception:
            pass

        # Transition logic: INITIALIZING -> READY only when all required services are reachable
        all_required_reachable = (total_nodes >= 4) and (healthy_nodes >= 4) and (failed_nodes == 0) and ctrl_status.get("online", False)

        if not all_required_reachable:
            if failed_nodes > 0:
                system_state = "FAILURE_DETECTED"
            else:
                system_state = "INITIALIZING"
        elif exp_status["running"]:
            phase = exp_status.get("phase", "")
            if "FAULT_INJECTION" in phase:
                system_state = "FAULT_INJECTION"
            elif "BASELINE" in phase:
                system_state = "BASELINE"
            elif "RECOVERY" in phase:
                system_state = "THROTTLED" if (rec_status.get("status") == "THROTTLED") else "RECOVERING"
            elif "COMPLETE" in phase:
                system_state = "EXPERIMENT_COMPLETE"
            else:
                system_state = "INITIALIZING"
        elif rec_status.get("running"):
            if rec_status.get("status") == "THROTTLED":
                system_state = "THROTTLED"
            elif rec_status.get("status") == "STARTING":
                system_state = "RECOVERY_STARTING"
            else:
                system_state = "RECOVERING"
        elif rep_status["under_replicated_blocks"] > 0:
            system_state = "UNDER_REPLICATED"
        elif wl_status["running"] and not rec_status["running"]:
            system_state = "BASELINE"
        else:
            system_state = "READY"

        return {
            "system_state": system_state,
            "cluster": {
                "total_nodes": total_nodes,
                "healthy_nodes": healthy_nodes,
                "failed_nodes": failed_nodes
            },
            "replication": {
                "replication_factor": REPLICATION_FACTOR,
                "total_blocks": rep_status["total_blocks"],
                "healthy_blocks": rep_status["healthy_blocks"],
                "under_replicated_blocks": rep_status["under_replicated_blocks"],
                "critical_blocks": rep_status["critical_blocks"]
            },
            "client": {
                "running": wl_status["running"],
                "workload": wl_status["profile"],
                "requests_per_second": wl_status["rps"] if wl_status["running"] else None,
                "throughput_mbps": wl_status["throughput_mbps"] if wl_status["running"] else None,
                "p50_ms": wl_status["p50_ms"] if wl_status["running"] else None,
                "p95_ms": wl_status["p95_ms"] if wl_status["running"] else None,
                "p99_ms": wl_status["p99_ms"] if wl_status["running"] else None,
                "error_rate": wl_status["error_rate"] if wl_status["running"] else None
            },
            "recovery": {
                "running": rec_status["running"],
                "mode": rec_status["mode"],
                "progress_percent": rec_status["progress_percent"],
                "recovered_bytes": rec_status["completed_bytes"] if rec_status["running"] else None,
                "remaining_bytes": rec_status["remaining_bytes"] if rec_status["running"] else None,
                "configured_rate_mbps": rec_status["configured_rate_mbps"],
                "actual_rate_mbps": rec_status["actual_rate_mbps"],
                "eta_seconds": rec_status["eta_seconds"]
            },
            "controller": ctrl_status,
            "experiment": exp_status
        }
    finally:
        await db.close()

@app.get("/api/events")
async def get_events():
    db = await get_db()
    try:
        async with db.execute('SELECT * FROM events ORDER BY created_at DESC') as cur:
            events = await cur.fetchall()
            return [dict(e) for e in events]
    finally:
        await db.close()

# --- COORDINATOR METADATA APIS ---

@app.get("/api/nodes")
async def get_nodes():
    db = await get_db()
    try:
        async with db.execute('SELECT * FROM nodes') as cursor:
            nodes = [dict(n) for n in await cursor.fetchall()]
            
        async def fetch_node_metrics(node):
            url = node["url"]
            node["block_count"] = 0
            node["stored_blocks"] = 0
            try:
                async with httpx.AsyncClient(timeout=1.0) as client:
                    resp = None
                    try:
                        resp = await client.get(f"{url}/metrics/json")
                    except Exception:
                        if "localhost" in url:
                            alt_url = url.replace("localhost", "127.0.0.1")
                            try:
                                resp = await client.get(f"{alt_url}/metrics/json")
                            except Exception:
                                pass
                        elif "127.0.0.1" in url:
                            alt_url = url.replace("127.0.0.1", "localhost")
                            try:
                                resp = await client.get(f"{alt_url}/metrics/json")
                            except Exception:
                                pass
                    if resp and resp.status_code == 200:
                        data = resp.json()
                        node["status"] = data.get("status", node["status"])
                        node["block_count"] = data.get("block_count", 0)
                        node["stored_blocks"] = data.get("block_count", 0)
                        node["stored_bytes"] = data.get("stored_bytes", 0)
                        node["cpu_percent"] = data.get("cpu_percent", 0.0)
                        node["memory_percent"] = data.get("memory_percent", 0.0)
                        node["disk_percent"] = data.get("disk_percent", 0.0)
                        node["network_rx_bytes"] = data.get("network_rx_bytes", 0)
                        node["network_tx_bytes"] = data.get("network_tx_bytes", 0)
                        node["reads_total"] = data.get("reads_total", 0)
                        node["writes_total"] = data.get("writes_total", 0)
            except Exception:
                pass
            return node
            
        results = await asyncio.gather(*(fetch_node_metrics(n) for n in nodes))
        return results
    finally:
        await db.close()

@app.get("/api/blocks")
async def get_blocks():
    db = await get_db()
    try:
        async with db.execute('SELECT * FROM blocks') as cursor:
            blocks = await cursor.fetchall()
            return [dict(b) for b in blocks]
    finally:
        await db.close()

@app.get("/api/blocks/under-replicated")
async def get_under_replicated_blocks():
    db = await get_db()
    try:
        query = f'''
            SELECT b.block_id, COUNT(r.node_id) as healthy_replicas
            FROM blocks b
            LEFT JOIN block_replicas r ON b.block_id = r.block_id AND r.replica_status = 'STORED'
            LEFT JOIN nodes n ON r.node_id = n.node_id AND n.status = 'HEALTHY'
            GROUP BY b.block_id
            HAVING healthy_replicas < {REPLICATION_FACTOR}
        '''
        async with db.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]
    finally:
        await db.close()

@app.get("/api/objects")
async def get_objects():
    db = await get_db()
    try:
        async with db.execute('SELECT * FROM objects') as cursor:
            objects = await cursor.fetchall()
            return [dict(o) for o in objects]
    finally:
        await db.close()

@app.get("/api/replication/status")
async def get_replication_status():
    db = await get_db()
    try:
        async with db.execute('SELECT COUNT(*) as c FROM blocks') as cursor:
            total_blocks = (await cursor.fetchone())['c']
            
        query = '''
            SELECT b.block_id, COUNT(n.node_id) as healthy_replicas
            FROM blocks b
            LEFT JOIN block_replicas r ON b.block_id = r.block_id AND r.replica_status = 'STORED'
            LEFT JOIN nodes n ON r.node_id = n.node_id AND n.status = 'HEALTHY'
            GROUP BY b.block_id
        '''
        
        healthy_blocks = 0
        under_replicated_blocks = 0
        critical_blocks = 0
        
        async with db.execute(query) as cursor:
            async for row in cursor:
                reps = row['healthy_replicas']
                if reps >= REPLICATION_FACTOR:
                    healthy_blocks += 1
                elif reps > 0:
                    under_replicated_blocks += 1
                else:
                    critical_blocks += 1
                    
        return {
            "replication_factor": REPLICATION_FACTOR,
            "total_blocks": total_blocks,
            "healthy_blocks": healthy_blocks,
            "under_replicated_blocks": under_replicated_blocks,
            "critical_blocks": critical_blocks
        }
    finally:
        await db.close()

# --- RECOVERY APIS ---

@app.get("/api/recovery/status")
async def get_recovery_status():
    return recovery_worker.get_status()

@app.get("/api/recovery/jobs")
async def get_recovery_jobs():
    db = await get_db()
    try:
        async with db.execute('SELECT * FROM recovery_jobs ORDER BY started_at DESC LIMIT 50') as cur:
            jobs = [dict(r) for r in await cur.fetchall()]
            return jobs
    finally:
        await db.close()

@app.post("/api/recovery/start")
async def start_recovery():
    await recovery_worker.start()
    return {"status": "Recovery started"}

@app.post("/api/recovery/stop")
async def stop_recovery():
    await recovery_worker.stop()
    return {"status": "Recovery stopped"}

class RateUpdate(BaseModel):
    rate_mbps: float

@app.put("/api/recovery/rate")
async def update_recovery_rate(rate: RateUpdate):
    recovery_worker.set_rate(rate.rate_mbps)
    
    # Log rate change
    db = await get_db()
    try:
        now = time.time()
        await db.execute('''
            INSERT INTO events (event_type, details, created_at)
            VALUES (?, ?, ?)
        ''', ("RECOVERY_RATE_CHANGED", f'{{"rate_mbps": {rate.rate_mbps}}}', now))
        await db.commit()
    finally:
        await db.close()
        
    return {"status": "success", "rate_mbps": recovery_worker.rate_mbps}

# --- CLIENT APIS ---

@app.post("/api/data/{object_id}")
async def upload_object(object_id: str, request: Request):
    data = await request.body()
    size_bytes = len(data)
    
    db = await get_db()
    now = time.time()
    try:
        async with db.execute('SELECT object_id FROM objects WHERE object_id = ?', (object_id,)) as cur:
            if await cur.fetchone():
                raise HTTPException(status_code=409, detail="Object already exists")
                
        async with db.execute('SELECT node_id, url FROM nodes WHERE status = "HEALTHY"') as cur:
            active_nodes = [dict(r) for r in await cur.fetchall()]
            
        if len(active_nodes) < REPLICATION_FACTOR:
            raise HTTPException(status_code=503, detail="Not enough healthy nodes for replication")
            
        await db.execute('INSERT INTO objects (object_id, size_bytes, created_at) VALUES (?, ?, ?)',
                         (object_id, size_bytes, now))
                         
        blocks_data = []
        for i in range(0, size_bytes, BLOCK_SIZE_BYTES):
            chunk = data[i:i+BLOCK_SIZE_BYTES]
            block_id = f"{object_id}-blk-{i//BLOCK_SIZE_BYTES}"
            checksum = hashlib.sha256(chunk).hexdigest()
            blocks_data.append({
                "block_id": block_id,
                "block_index": i//BLOCK_SIZE_BYTES,
                "data": chunk,
                "size_bytes": len(chunk),
                "checksum": checksum
            })
            
        async with httpx.AsyncClient(timeout=10.0) as client:
            for b_info in blocks_data:
                await db.execute('''
                    INSERT INTO blocks (block_id, object_id, block_index, size_bytes, checksum, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (b_info["block_id"], object_id, b_info["block_index"], b_info["size_bytes"], b_info["checksum"], now))
                
                selected_nodes = active_nodes[:REPLICATION_FACTOR]
                
                for node in selected_nodes:
                    try:
                        resp = await client.post(f"{node['url']}/blocks/{b_info['block_id']}", content=b_info["data"])
                        resp.raise_for_status()
                        await db.execute('''
                            INSERT INTO block_replicas (block_id, node_id, replica_status, created_at)
                            VALUES (?, ?, ?, ?)
                        ''', (b_info["block_id"], node["node_id"], "STORED", now))
                    except Exception as e:
                        pass
        await db.commit()
        return {"status": "success", "object_id": object_id, "size_bytes": size_bytes}
    finally:
        await db.close()

@app.get("/api/data/{object_id}")
async def download_object(object_id: str):
    db = await get_db()
    try:
        async with db.execute('SELECT size_bytes FROM objects WHERE object_id = ?', (object_id,)) as cur:
            obj = await cur.fetchone()
            if not obj:
                raise HTTPException(status_code=404, detail="Object not found")
                
        async with db.execute('''
            SELECT block_id, checksum FROM blocks 
            WHERE object_id = ? ORDER BY block_index ASC
        ''', (object_id,)) as cur:
            blocks = [dict(r) for r in await cur.fetchall()]
            
        async def stream_blocks():
            async with httpx.AsyncClient(timeout=10.0) as client:
                for block in blocks:
                    block_id = block["block_id"]
                    async with db.execute('''
                        SELECT n.url FROM block_replicas r
                        JOIN nodes n ON r.node_id = n.node_id
                        WHERE r.block_id = ? AND r.replica_status = 'STORED' AND n.status = 'HEALTHY'
                    ''', (block_id,)) as cur:
                        replicas = [r['url'] for r in await cur.fetchall()]
                        
                    if not replicas:
                        raise HTTPException(status_code=500, detail=f"No healthy replicas for block {block_id}")
                        
                    data = None
                    for url in replicas:
                        try:
                            resp = await client.get(f"{url}/blocks/{block_id}")
                            resp.raise_for_status()
                            fetched_data = resp.content
                            
                            fetched_checksum = hashlib.sha256(fetched_data).hexdigest()
                            if fetched_checksum == block["checksum"]:
                                data = fetched_data
                                break
                        except Exception:
                            continue
                            
                    if data is None:
                        raise HTTPException(status_code=500, detail=f"Failed to retrieve valid block {block_id}")
                        
                    yield data
                    
        return StreamingResponse(stream_blocks(), media_type="application/octet-stream")
    finally:
        await db.close()

@app.delete("/api/data/{object_id}")
async def delete_object(object_id: str):
    db = await get_db()
    try:
        async with db.execute('SELECT block_id FROM blocks WHERE object_id = ?', (object_id,)) as cur:
            blocks = [r['block_id'] for r in await cur.fetchall()]
            
        if not blocks:
            raise HTTPException(status_code=404, detail="Object not found")
            
        async with httpx.AsyncClient(timeout=5.0) as client:
            for block_id in blocks:
                async with db.execute('''
                    SELECT n.url FROM block_replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.block_id = ?
                ''', (block_id,)) as cur:
                    urls = [r['url'] for r in await cur.fetchall()]
                    
                for url in urls:
                    try:
                        await client.delete(f"{url}/blocks/{block_id}")
                    except Exception:
                        pass
                        
        await db.execute('DELETE FROM objects WHERE object_id = ?', (object_id,))
        await db.commit()
        return {"status": "deleted", "object_id": object_id}
    finally:
        await db.close()
