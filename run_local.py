import os
import sys
import time
import subprocess
import httpx
import asyncio

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(ROOT_DIR, "backend")
FRONTEND_DIR = os.path.join(ROOT_DIR, "frontend")

# Ensure data directories exist inside backend/data
for i in range(1, 5):
    os.makedirs(os.path.join(BACKEND_DIR, "data", f"storage{i}"), exist_ok=True)
os.makedirs(os.path.join(BACKEND_DIR, "data", "coordinator"), exist_ok=True)
os.makedirs(os.path.join(BACKEND_DIR, "data", "controller"), exist_ok=True)

processes = []

def start_backend_process(env_vars, command):
    env = os.environ.copy()
    env.update(env_vars)
    env["PYTHONPATH"] = BACKEND_DIR
    p = subprocess.Popen(command, env=env, cwd=BACKEND_DIR)
    processes.append(p)
    return p

print("==================================================")
print("Starting Adaptive Storage Recovery (Local Mode)...")
print("==================================================")

# 1. Storage Node 1 (Port 8001)
start_backend_process({
    "SERVICE_NAME": "storage1",
    "NODE_ID": "storage1",
    "DATA_DIR": os.path.join(BACKEND_DIR, "data", "storage1")
}, [sys.executable, "-m", "uvicorn", "storage_node.main:app", "--host", "0.0.0.0", "--port", "8001"])

# 2. Storage Node 2 (Port 8002)
start_backend_process({
    "SERVICE_NAME": "storage2",
    "NODE_ID": "storage2",
    "DATA_DIR": os.path.join(BACKEND_DIR, "data", "storage2")
}, [sys.executable, "-m", "uvicorn", "storage_node.main:app", "--host", "0.0.0.0", "--port", "8002"])

# 3. Storage Node 3 (Port 8004)
start_backend_process({
    "SERVICE_NAME": "storage3",
    "NODE_ID": "storage3",
    "DATA_DIR": os.path.join(BACKEND_DIR, "data", "storage3")
}, [sys.executable, "-m", "uvicorn", "storage_node.main:app", "--host", "0.0.0.0", "--port", "8004"])

# 4. Storage Node 4 (Port 8005)
start_backend_process({
    "SERVICE_NAME": "storage4",
    "NODE_ID": "storage4",
    "DATA_DIR": os.path.join(BACKEND_DIR, "data", "storage4")
}, [sys.executable, "-m", "uvicorn", "storage_node.main:app", "--host", "0.0.0.0", "--port", "8005"])

# 5. Coordinator (Port 8000)
start_backend_process({
    "SERVICE_NAME": "coordinator",
    "DB_PATH": os.path.join(BACKEND_DIR, "data", "coordinator", "coordinator.db")
}, [sys.executable, "-m", "uvicorn", "coordinator.main:app", "--host", "0.0.0.0", "--port", "8000"])

# 6. Adaptive Controller (Port 8003)
start_backend_process({
    "SERVICE_NAME": "controller",
    "COORDINATOR_URL": "http://127.0.0.1:8000",
    "PROMETHEUS_URL": "http://127.0.0.1:9090",
    "DB_PATH": os.path.join(BACKEND_DIR, "data", "controller", "experiments.db")
}, [sys.executable, "-m", "uvicorn", "controller.main:app", "--host", "0.0.0.0", "--port", "8003"])

# 7. Frontend Dashboard (Port 3000)
if os.path.exists(FRONTEND_DIR):
    cmd = ["cmd", "/c", "npm", "run", "dev"] if sys.platform == "win32" else ["npm", "run", "dev"]
    env = os.environ.copy()
    p = subprocess.Popen(cmd, env=env, cwd=FRONTEND_DIR)
    processes.append(p)

async def check_service_health(client, name, url, timeout_secs=15):
    alt_url = url.replace("localhost", "127.0.0.1") if "localhost" in url else url.replace("127.0.0.1", "localhost")
    start = time.time()
    last_err = None
    while time.time() - start < timeout_secs:
        for u in [url, alt_url]:
            try:
                resp = await client.get(u, timeout=2.0)
                if resp.status_code == 200:
                    print(f"[STARTUP] {name} healthy", flush=True)
                    return True
            except Exception as e:
                last_err = e
        await asyncio.sleep(0.5)
    print(f"[STARTUP ERROR] {name} failed: {last_err}", flush=True)
    return False

async def initialize_cluster():
    async with httpx.AsyncClient() as client:
        # 1. Health checks for all services
        health_targets = [
            ("Coordinator", "http://localhost:8000/health"),
            ("Storage1", "http://localhost:8001/health"),
            ("Storage2", "http://localhost:8002/health"),
            ("Storage3", "http://localhost:8004/health"),
            ("Storage4", "http://localhost:8005/health"),
            ("Controller", "http://localhost:8003/health"),
        ]

        all_ok = True
        for name, url in health_targets:
            ok = await check_service_health(client, name, url)
            if not ok:
                all_ok = False

        if not all_ok:
            print("[STARTUP ERROR] One or more services failed health check.", flush=True)

        # 2. Register storage nodes
        nodes = [
            ("storage1", "http://localhost:8001"),
            ("storage2", "http://localhost:8002"),
            ("storage3", "http://localhost:8004"),
            ("storage4", "http://localhost:8005"),
        ]

        for node_id, url in nodes:
            try:
                await client.post("http://localhost:8000/nodes/register", json={"node_id": node_id, "url": url}, timeout=3.0)
            except Exception:
                try:
                    await client.post("http://127.0.0.1:8000/nodes/register", json={"node_id": node_id, "url": url}, timeout=3.0)
                except Exception as reg_err:
                    print(f"[REGISTRY ERROR] Failed to register {node_id}: {reg_err}", flush=True)

        # Verify registration via /api/nodes
        verified = False
        for _ in range(10):
            try:
                res = await client.get("http://localhost:8000/api/nodes", timeout=3.0)
                if res.status_code == 200:
                    node_list = res.json()
                    reg_ids = {n.get("node_id") for n in node_list}
                    if {"storage1", "storage2", "storage3", "storage4"}.issubset(reg_ids):
                        verified = True
                        print("[REGISTRY] 4 storage nodes registered", flush=True)
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if not verified:
            print("[REGISTRY ERROR] Failed to verify 4 registered storage nodes", flush=True)

        # 3. Wait for system state transition to READY
        ready = False
        for _ in range(20):
            try:
                s_resp = await client.get("http://localhost:8000/api/system/status", timeout=3.0)
                if s_resp.status_code == 200:
                    data = s_resp.json()
                    if data.get("system_state") == "READY":
                        ready = True
                        print("[SYSTEM] READY", flush=True)
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)

        if not ready:
            print("[SYSTEM] Still initializing or waiting for ready state...", flush=True)

asyncio.run(initialize_cluster())

print("\n==================================================", flush=True)
print("Adaptive Storage Recovery is running!", flush=True)
print("Frontend Dashboard: http://localhost:3000", flush=True)
print("Coordinator API:    http://localhost:8000 (Docs: /docs)", flush=True)
print("Controller API:     http://localhost:8003 (Docs: /docs)", flush=True)
print("Press Ctrl+C to stop all services.", flush=True)
print("==================================================", flush=True)

try:
    for p in processes:
        p.wait()
except KeyboardInterrupt:
    print("\nStopping services...")
    for p in processes:
        p.terminate()
