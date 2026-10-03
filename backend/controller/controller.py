import asyncio
import httpx
import os
from controller.state_machine import AdaptiveStateMachine
from controller.config import ControllerConfig

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://coordinator:8000")

class DynamicController:
    def __init__(self):
        self.config = ControllerConfig()
        self.state_machine = AdaptiveStateMachine(self.config)
        self.is_enabled = False
        self.task = None
        
        # Configurable Baselines
        self.baseline_p99 = 50.0
        self.baseline_throughput = 50.0
        
        self.current_p99 = 0.0
        self.current_throughput = 0.0
        self.current_disk_percent = 0.0
        self.current_network_percent = 0.0
        self.is_recovery_active = False
        self.latest_decision_reason = "Initialized"

    async def fetch_metrics(self):
        prom_url = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
        got_prom = False
        
        # 1. Try Prometheus
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                rate_query = 'sum(rate(client_requests_total[10s]))'
                resp = await client.get(f"{prom_url}/api/v1/query", params={"query": rate_query})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('data', {}).get('result'):
                        self.current_throughput = float(data['data']['result'][0]['value'][1])
                        got_prom = True
                
                p99_query = 'histogram_quantile(0.99, sum(rate(client_latency_seconds_bucket[10s])) by (le))'
                resp = await client.get(f"{prom_url}/api/v1/query", params={"query": p99_query})
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('data', {}).get('result'):
                        val = data['data']['result'][0]['value'][1]
                        if val != 'NaN':
                            self.current_p99 = float(val) * 1000.0
                            got_prom = True
        except Exception:
            pass
            
        # 2. If Prometheus didn't provide live data (e.g. running on Windows native), query Coordinator directly
        try:
            async with httpx.AsyncClient(timeout=1.5) as client:
                wl_resp = await client.get(f"{COORDINATOR_URL}/api/workload/status")
                if wl_resp.status_code == 200:
                    wl = wl_resp.json()
                    if wl.get("running"):
                        self.current_throughput = wl.get("throughput_mbps", 0.0)
                        self.current_p99 = wl.get("p99_ms", 0.0)
                        
                nodes_resp = await client.get(f"{COORDINATOR_URL}/api/nodes")
                if nodes_resp.status_code == 200:
                    nodes = nodes_resp.json()
                    if nodes:
                        self.current_disk_percent = max([n.get("disk_percent", 0.0) for n in nodes], default=0.0)
                        # Estimate network utilization relative to 100MB/s link
                        max_net_bytes = max([n.get("network_rx_bytes", 0) + n.get("network_tx_bytes", 0) for n in nodes], default=0)
                        self.current_network_percent = min(100.0, (max_net_bytes / (100 * 1024 * 1024)) * 100)
                        
                rec_resp = await client.get(f"{COORDINATOR_URL}/api/recovery/status")
                if rec_resp.status_code == 200:
                    rec = rec_resp.json()
                    self.is_recovery_active = rec.get("running", False)
        except Exception as e:
            print(f"Error querying coordinator for telemetry: {e}")
            
        return self.current_p99, self.current_throughput, self.current_disk_percent, self.current_network_percent, self.is_recovery_active

    async def start(self):
        if self.is_enabled:
            return
        self.is_enabled = True
        self.task = asyncio.create_task(self._loop())

    async def stop(self):
        self.is_enabled = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
            
    async def _loop(self):
        while self.is_enabled:
            try:
                p99, tput, disk, net, rec_running = await self.fetch_metrics()
                state, new_rate, changed = self.state_machine.evaluate(
                    p99, tput, self.baseline_p99, self.baseline_throughput,
                    disk_percent=disk, network_percent=net, is_recovery_running=rec_running
                )
                
                if self.state_machine.history:
                    self.latest_decision_reason = self.state_machine.history[-1].get("reason", "Stable")
                
                if changed:
                    print(f"Controller decision: {state} - Setting rate to {new_rate} MB/s ({self.latest_decision_reason})")
                    async with httpx.AsyncClient() as client:
                        await client.put(f"{COORDINATOR_URL}/api/recovery/rate", json={"rate_mbps": new_rate})
            except Exception as e:
                print(f"Controller loop error: {e}")
                
            await asyncio.sleep(self.config.sample_interval_seconds)
