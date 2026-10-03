import asyncio
import time
import random
import os
from collections import deque
import httpx

PROFILES = {
    "LOW": {"rps": 8, "size_bytes": 256 * 1024, "concurrency": 2},
    "MEDIUM": {"rps": 25, "size_bytes": 512 * 1024, "concurrency": 5},
    "HIGH": {"rps": 60, "size_bytes": 1024 * 1024, "concurrency": 10}
}

class WorkloadManager:
    def __init__(self, base_url="http://127.0.0.1:8000"):
        self.base_url = base_url
        self.running = False
        self.profile = "LOW"
        self.worker_tasks = []
        self.aggregator_task = None
        
        # Lock and stats
        self.total_requests = 0
        self.total_errors = 0
        self.total_bytes = 0
        
        # Recent requests window for live rolling stats (cleared/aged every sec)
        self.recent_latencies = deque(maxlen=1000)
        self.recent_bytes = deque(maxlen=1000)
        self.recent_errors = deque(maxlen=1000)
        self.recent_timestamps = deque(maxlen=1000)
        
        # Bounded history for live charts (120 samples = 2 minutes of 1s samples)
        self.history = deque(maxlen=120)
        
        # Object pool for reads/writes
        self.object_pool = [f"workload-obj-{i}" for i in range(1, 31)]
        
        # Current calculated metrics
        self.current_rps = 0.0
        self.current_throughput_mbps = 0.0
        self.p50_ms = 0.0
        self.p95_ms = 0.0
        self.p99_ms = 0.0
        self.errors_per_second = 0.0

    def get_status(self):
        return {
            "running": self.running,
            "profile": self.profile if self.running else None,
            "rps": round(self.current_rps, 2) if self.running else 0.0,
            "throughput_mbps": round(self.current_throughput_mbps, 2) if self.running else 0.0,
            "p50_ms": round(self.p50_ms, 2) if self.running else 0.0,
            "p95_ms": round(self.p95_ms, 2) if self.running else 0.0,
            "p99_ms": round(self.p99_ms, 2) if self.running else 0.0,
            "errors_per_second": round(self.errors_per_second, 2) if self.running else 0.0,
            "total_requests": self.total_requests,
            "history": list(self.history)
        }

    async def start(self, profile="LOW"):
        if self.running:
            await self.set_profile(profile)
            return
        
        if profile.upper() not in PROFILES:
            profile = "LOW"
        self.profile = profile.upper()
        self.running = True
        
        self.aggregator_task = asyncio.create_task(self._aggregate_loop())
        
        cfg = PROFILES[self.profile]
        concurrency = cfg["concurrency"]
        for worker_id in range(concurrency):
            t = asyncio.create_task(self._worker_loop(worker_id))
            self.worker_tasks.append(t)

    async def stop(self):
        self.running = False
        for t in self.worker_tasks:
            t.cancel()
        if self.aggregator_task:
            self.aggregator_task.cancel()
            
        self.worker_tasks = []
        self.current_rps = 0.0
        self.current_throughput_mbps = 0.0
        self.p50_ms = 0.0
        self.p95_ms = 0.0
        self.p99_ms = 0.0
        self.errors_per_second = 0.0

    async def set_profile(self, profile):
        if profile.upper() not in PROFILES:
            return
        was_running = self.running
        if was_running:
            await self.stop()
            await self.start(profile)
        else:
            self.profile = profile.upper()

    async def _worker_loop(self, worker_id: int):
        client = httpx.AsyncClient(timeout=10.0)
        try:
            while self.running:
                cfg = PROFILES.get(self.profile, PROFILES["LOW"])
                target_rps_per_worker = max(1.0, cfg["rps"] / max(1, cfg["concurrency"]))
                sleep_interval = 1.0 / target_rps_per_worker
                
                # Jitter sleep slightly
                await asyncio.sleep(random.uniform(sleep_interval * 0.8, sleep_interval * 1.2))
                if not self.running:
                    break
                
                # 70% READ, 30% WRITE
                is_write = random.random() < 0.30
                obj_id = random.choice(self.object_pool)
                payload_size = cfg["size_bytes"]
                
                start_t = time.perf_counter()
                transferred_bytes = 0
                is_err = False
                
                try:
                    if is_write:
                        # Write payload
                        data = os.urandom(payload_size)
                        # We delete first if exists, to allow overwriting
                        await client.delete(f"{self.base_url}/api/data/{obj_id}")
                        resp = await client.post(f"{self.base_url}/api/data/{obj_id}", content=data)
                        if resp.status_code == 200:
                            transferred_bytes = len(data)
                        else:
                            is_err = True
                    else:
                        # Read payload
                        resp = await client.get(f"{self.base_url}/api/data/{obj_id}")
                        if resp.status_code == 200:
                            transferred_bytes = len(resp.content)
                        elif resp.status_code == 404:
                            # Object not seeded yet, seed it once
                            seed_data = os.urandom(payload_size)
                            await client.post(f"{self.base_url}/api/data/{obj_id}", content=seed_data)
                            transferred_bytes = len(seed_data)
                        else:
                            is_err = True
                except Exception:
                    is_err = True
                    
                dur_ms = (time.perf_counter() - start_t) * 1000.0
                
                # Record sample
                now = time.time()
                self.total_requests += 1
                if is_err:
                    self.total_errors += 1
                self.total_bytes += transferred_bytes
                
                self.recent_latencies.append(dur_ms)
                self.recent_bytes.append(transferred_bytes)
                self.recent_errors.append(1 if is_err else 0)
                self.recent_timestamps.append(now)
        finally:
            await client.aclose()

    async def _aggregate_loop(self):
        while self.running:
            await asyncio.sleep(1.0)
            now = time.time()
            cutoff = now - 2.0 # Rolling 2s window for current rates
            
            latencies = []
            bytes_transferred = 0
            errors = 0
            count = 0
            
            for i in range(len(self.recent_timestamps) - 1, -1, -1):
                if i < len(self.recent_timestamps) and self.recent_timestamps[i] >= cutoff:
                    latencies.append(self.recent_latencies[i])
                    bytes_transferred += self.recent_bytes[i]
                    errors += self.recent_errors[i]
                    count += 1
                else:
                    break
                    
            window_sec = 2.0
            self.current_rps = count / window_sec
            self.current_throughput_mbps = (bytes_transferred / (1024 * 1024)) / window_sec
            self.errors_per_second = errors / window_sec
            
            if latencies:
                latencies.sort()
                n = len(latencies)
                self.p50_ms = latencies[int(n * 0.50)]
                self.p95_ms = latencies[min(n - 1, int(n * 0.95))]
                self.p99_ms = latencies[min(n - 1, int(n * 0.99))]
            else:
                self.p50_ms = 0.0
                self.p95_ms = 0.0
                self.p99_ms = 0.0
                
            sample = {
                "time": time.strftime("%H:%M:%S", time.localtime(now)),
                "timestamp": now,
                "rps": round(self.current_rps, 2),
                "throughput_mbps": round(self.current_throughput_mbps, 2),
                "p50_ms": round(self.p50_ms, 2),
                "p95_ms": round(self.p95_ms, 2),
                "p99_ms": round(self.p99_ms, 2),
                "error_rate": round(self.errors_per_second, 2)
            }
            self.history.append(sample)
