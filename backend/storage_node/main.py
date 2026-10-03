import os
import asyncio
import datetime
import hashlib
import psutil
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from prometheus_client import Counter, Gauge, generate_latest, CONTENT_TYPE_LATEST

import httpx

app = FastAPI(title="Storage Node Service")

SERVICE_NAME = os.getenv("SERVICE_NAME", "storage_node")
NODE_ID = os.getenv("NODE_ID", "unknown-node")
DATA_DIR = os.getenv("DATA_DIR", "/app/data")
COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://localhost:8000")
NODE_PORT = os.getenv("PORT", "8001")
NODE_URL = os.getenv("NODE_URL", f"http://localhost:{NODE_PORT}")

os.makedirs(DATA_DIR, exist_ok=True)

# State
SIMULATED_FAILURE = False

async def auto_register():
    for _ in range(15):
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                urls = [COORDINATOR_URL]
                if "localhost" in COORDINATOR_URL:
                    urls.append(COORDINATOR_URL.replace("localhost", "127.0.0.1"))
                elif "127.0.0.1" in COORDINATOR_URL:
                    urls.append(COORDINATOR_URL.replace("127.0.0.1", "localhost"))
                for curl in urls:
                    try:
                        res = await client.post(
                            f"{curl}/nodes/register",
                            json={"node_id": NODE_ID, "url": NODE_URL}
                        )
                        if res.status_code == 200:
                            return
                    except Exception:
                        pass
        except Exception:
            pass
        await asyncio.sleep(1)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(auto_register())

# Application Metrics (JSON)
app_metrics = {
    "reads_total": 0,
    "writes_total": 0,
    "read_bytes_total": 0,
    "write_bytes_total": 0,
    "request_errors_total": 0
}

# Prometheus Metrics
PROM_READS = Counter('storage_reads_total', 'Total read requests', ['node_id'])
PROM_WRITES = Counter('storage_writes_total', 'Total write requests', ['node_id'])
PROM_READ_BYTES = Counter('storage_read_bytes_total', 'Total bytes read', ['node_id'])
PROM_WRITE_BYTES = Counter('storage_write_bytes_total', 'Total bytes written', ['node_id'])
PROM_ERRORS = Counter('storage_errors_total', 'Total request errors', ['node_id'])
PROM_CPU = Gauge('storage_cpu_percent', 'CPU utilization', ['node_id'])
PROM_MEM = Gauge('storage_memory_percent', 'Memory utilization', ['node_id'])
PROM_DISK = Gauge('storage_disk_percent', 'Disk utilization', ['node_id'])


def check_failure():
    """Dependency to block requests if node is in simulated failure mode."""
    if SIMULATED_FAILURE:
        raise HTTPException(status_code=503, detail="Node is currently in failed state (simulated)")

@app.get("/health")
async def health_check():
    if SIMULATED_FAILURE:
        return Response(content='{"status": "unhealthy"}', status_code=503, media_type="application/json")
        
    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "timestamp": datetime.datetime.utcnow().isoformat()
    }

# --- ADMIN ENDPOINTS ---

@app.post("/admin/fail")
async def admin_fail():
    global SIMULATED_FAILURE
    SIMULATED_FAILURE = True
    return {"status": "failed", "node_id": NODE_ID}

@app.post("/admin/recover")
async def admin_recover():
    global SIMULATED_FAILURE
    SIMULATED_FAILURE = False
    return {"status": "recovered", "node_id": NODE_ID}

@app.get("/admin/status")
async def admin_status():
    return {
        "node_id": NODE_ID,
        "failed": SIMULATED_FAILURE
    }

def get_storage_stats():
    total_bytes = 0
    count = 0
    try:
        if os.path.exists(DATA_DIR):
            for entry in os.scandir(DATA_DIR):
                if entry.is_file() and entry.name.endswith(".blk"):
                    count += 1
                    total_bytes += entry.stat().st_size
    except Exception:
        pass
    return count, total_bytes

# --- METRICS ENDPOINTS ---

@app.get("/metrics/json")
async def get_metrics_json():
    block_count, stored_bytes = await asyncio.to_thread(get_storage_stats)
    disk_usage = psutil.disk_usage(DATA_DIR)
    net_io = psutil.net_io_counters()
    
    status_str = "FAILED" if SIMULATED_FAILURE else "HEALTHY"
    return {
        "node_id": NODE_ID,
        "status": status_str,
        "block_count": block_count,
        "stored_bytes": stored_bytes,
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_percent": disk_usage.percent,
        "network_rx_bytes": net_io.bytes_recv,
        "network_tx_bytes": net_io.bytes_sent,
        "reads_total": app_metrics["reads_total"],
        "writes_total": app_metrics["writes_total"]
    }

@app.get("/metrics")
async def get_metrics():
    return await get_metrics_json()

@app.get("/metrics/prometheus")
async def get_prometheus_metrics():
    PROM_CPU.labels(node_id=NODE_ID).set(psutil.cpu_percent())
    PROM_MEM.labels(node_id=NODE_ID).set(psutil.virtual_memory().percent)
    PROM_DISK.labels(node_id=NODE_ID).set(psutil.disk_usage(DATA_DIR).percent)
    
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

# --- BLOCK ENDPOINTS ---

def get_block_path(block_id: str) -> str:
    return os.path.join(DATA_DIR, f"{block_id}.blk")

@app.get("/blocks", dependencies=[Depends(check_failure)])
async def list_blocks():
    try:
        def _list_sync():
            return [f[:-4] for f in os.listdir(DATA_DIR) if f.endswith(".blk")]
        blocks = await asyncio.to_thread(_list_sync)
        return {"blocks": blocks}
    except Exception as e:
        app_metrics["request_errors_total"] += 1
        PROM_ERRORS.labels(node_id=NODE_ID).inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/blocks/{block_id}", dependencies=[Depends(check_failure)])
async def write_block(block_id: str, request: Request):
    try:
        file_path = get_block_path(block_id)
        hasher = hashlib.sha256()
        size_bytes = 0
        
        # We need to write synchronously in chunks or use to_thread per chunk
        def _write_chunk(f, chunk):
            f.write(chunk)
            
        with open(file_path, "wb") as f:
            async for chunk in request.stream():
                await asyncio.to_thread(_write_chunk, f, chunk)
                hasher.update(chunk)
                size_bytes += len(chunk)
                
        ctime = os.path.getctime(file_path)
        checksum = hasher.hexdigest()
        
        app_metrics["writes_total"] += 1
        app_metrics["write_bytes_total"] += size_bytes
        PROM_WRITES.labels(node_id=NODE_ID).inc()
        PROM_WRITE_BYTES.labels(node_id=NODE_ID).inc(size_bytes)
        
        return {
            "block_id": block_id,
            "node_id": NODE_ID,
            "size_bytes": size_bytes,
            "checksum": checksum,
            "creation_timestamp": datetime.datetime.fromtimestamp(ctime).isoformat(),
            "status": "stored"
        }
    except Exception as e:
        app_metrics["request_errors_total"] += 1
        PROM_ERRORS.labels(node_id=NODE_ID).inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/blocks/{block_id}", dependencies=[Depends(check_failure)])
async def read_block(block_id: str):
    file_path = get_block_path(block_id)
    if not os.path.exists(file_path):
        app_metrics["request_errors_total"] += 1
        PROM_ERRORS.labels(node_id=NODE_ID).inc()
        raise HTTPException(status_code=404, detail="Block not found")
        
    try:
        def _read_sync():
            with open(file_path, "rb") as f:
                return f.read()
                
        data = await asyncio.to_thread(_read_sync)
        size_bytes = len(data)
        
        app_metrics["reads_total"] += 1
        app_metrics["read_bytes_total"] += size_bytes
        PROM_READS.labels(node_id=NODE_ID).inc()
        PROM_READ_BYTES.labels(node_id=NODE_ID).inc(size_bytes)
        
        return Response(content=data, media_type="application/octet-stream")
    except Exception as e:
        app_metrics["request_errors_total"] += 1
        PROM_ERRORS.labels(node_id=NODE_ID).inc()
        raise HTTPException(status_code=500, detail=str(e))

@app.head("/blocks/{block_id}", dependencies=[Depends(check_failure)])
async def head_block(block_id: str):
    file_path = get_block_path(block_id)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Block not found")
        
    try:
        def _stat_sync():
            return os.stat(file_path)
            
        stat = await asyncio.to_thread(_stat_sync)
        return Response(headers={"Content-Length": str(stat.st_size)})
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/blocks/{block_id}", dependencies=[Depends(check_failure)])
async def delete_block(block_id: str):
    file_path = get_block_path(block_id)
    if not os.path.exists(file_path):
        app_metrics["request_errors_total"] += 1
        PROM_ERRORS.labels(node_id=NODE_ID).inc()
        raise HTTPException(status_code=404, detail="Block not found")
        
    try:
        os.remove(file_path)
        return {"status": "deleted", "block_id": block_id}
    except Exception as e:
        app_metrics["request_errors_total"] += 1
        PROM_ERRORS.labels(node_id=NODE_ID).inc()
        raise HTTPException(status_code=500, detail=str(e))
