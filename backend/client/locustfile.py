import os
import random
import time
from locust import HttpUser, task, between, events
from locust.runners import MasterRunner, WorkerRunner

# Environment Configuration
WORKLOAD_PROFILE = os.getenv("WORKLOAD_PROFILE", "LOW").upper()
COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://localhost:8000")

# Adjust wait times or object sizes based on profile
if WORKLOAD_PROFILE == "HIGH":
    WAIT_TIME = between(0.01, 0.1)
    PAYLOAD_SIZE = 4 * 1024 * 1024  # 4MB
elif WORKLOAD_PROFILE == "MEDIUM":
    WAIT_TIME = between(0.1, 0.5)
    PAYLOAD_SIZE = 1 * 1024 * 1024  # 1MB
else:
    WAIT_TIME = between(0.5, 2.0)
    PAYLOAD_SIZE = 512 * 1024       # 512KB

# Pre-generate some dummy payload to avoid CPU overhead during test
DUMMY_PAYLOAD = os.urandom(PAYLOAD_SIZE)

class StorageClientUser(HttpUser):
    wait_time = WAIT_TIME
    host = COORDINATOR_URL
    
    def on_start(self):
        # We will read/write from a pool of 100 objects to ensure repeatable hits
        self.object_pool = [f"obj-{i}" for i in range(1, 101)]

    @task(3)
    def write_object(self):
        """30% of traffic is writes"""
        obj_id = random.choice(self.object_pool)
        
        start_time = time.time()
        
        # We delete first in case it already exists, to simulate overwriting
        # In a real system, POST might just overwrite, but our API returns 409 if exists.
        self.client.delete(f"/api/data/{obj_id}", catch_response=True)
        
        with self.client.post(
            f"/api/data/{obj_id}", 
            data=DUMMY_PAYLOAD,
            name="/api/data/[id] (WRITE)",
            catch_response=True
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Write failed: {response.status_code}")

    @task(7)
    def read_object(self):
        """70% of traffic is reads"""
        obj_id = random.choice(self.object_pool)
        
        with self.client.get(
            f"/api/data/{obj_id}", 
            name="/api/data/[id] (READ)",
            catch_response=True
        ) as response:
            # If 404, it just means it hasn't been written yet. We won't count it as a failure for throughput contention
            # but we will mark it successful so locust doesn't scream errors continuously during warmup.
            if response.status_code == 200:
                response.success()
            elif response.status_code == 404:
                response.success()
            else:
                response.failure(f"Read failed: {response.status_code}")

# Add custom metric tracking for MB/s (Throughput)
# Locust naturally tracks requests/sec and response times (p50, p95, p99)
# We hook into request events to calculate bytes per second.

class ThroughputStats:
    def __init__(self):
        self.read_bytes = 0
        self.write_bytes = 0
        self.start_time = time.time()

stats = ThroughputStats()

@events.request.add_listener
def on_request(request_type, name, response_time, response_length, exception, context, **kwargs):
    if exception:
        return
    
    if "READ" in name and response_length:
        stats.read_bytes += response_length
    elif "WRITE" in name:
        stats.write_bytes += PAYLOAD_SIZE

@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    duration = time.time() - stats.start_time
    if duration > 0:
        read_mbps = (stats.read_bytes / (1024 * 1024)) / duration
        write_mbps = (stats.write_bytes / (1024 * 1024)) / duration
        print(f"\n--- Storage Contention Results ---")
        print(f"Test Duration: {duration:.2f} s")
        print(f"Avg Read Throughput:  {read_mbps:.2f} MB/s")
        print(f"Avg Write Throughput: {write_mbps:.2f} MB/s")
        print(f"----------------------------------\n")
