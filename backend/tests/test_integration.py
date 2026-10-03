import pytest
import httpx
import os
import hashlib
import time

COORDINATOR_URL = os.environ.get("COORDINATOR_URL", "http://localhost:8000")
STORAGE_NODES = [
    "http://localhost:8001",
    "http://localhost:8002",
    "http://localhost:8003",
    "http://localhost:8004",
]

def test_integration_upload_reconstruct():
    """
    Proves:
    - uploaded object is split into blocks
    - exactly 3 replicas exist
    - blocks exist physically
    - reconstruction matches checksum
    """
    original_data = os.urandom(5 * 1024 * 1024)
    original_checksum = hashlib.sha256(original_data).hexdigest()
    object_id = "test-obj-01"

    with httpx.Client() as client:
        time.sleep(2)
        nodes_resp = client.get(f"{COORDINATOR_URL}/api/nodes")
        if nodes_resp.status_code != 200:
            pytest.skip("Coordinator not available")
        active_nodes = [n for n in nodes_resp.json() if n["status"] == "HEALTHY"]
        if len(active_nodes) < 3:
            pytest.skip("Not enough active nodes to run integration test")

    with httpx.Client(timeout=30.0) as client:
        resp = client.post(f"{COORDINATOR_URL}/api/data/{object_id}", content=original_data)
        if resp.status_code == 409:
            client.delete(f"{COORDINATOR_URL}/api/data/{object_id}")
            resp = client.post(f"{COORDINATOR_URL}/api/data/{object_id}", content=original_data)
            
        assert resp.status_code == 200

    with httpx.Client() as client:
        blocks_resp = client.get(f"{COORDINATOR_URL}/api/blocks")
        blocks = [b for b in blocks_resp.json() if b["object_id"] == object_id]
        assert len(blocks) == 2

    block_ids = [b["block_id"] for b in blocks]
    for b_id in block_ids:
        replica_count = 0
        with httpx.Client() as client:
            for node_url in STORAGE_NODES:
                try:
                    head_resp = client.head(f"{node_url}/blocks/{b_id}")
                    if head_resp.status_code == 200:
                        replica_count += 1
                except:
                    pass
        assert replica_count == 3, f"Block {b_id} does not have exactly 3 replicas"

    with httpx.Client(timeout=30.0) as client:
        download_resp = client.get(f"{COORDINATOR_URL}/api/data/{object_id}")
        assert download_resp.status_code == 200
        downloaded_checksum = hashlib.sha256(download_resp.content).hexdigest()
        assert downloaded_checksum == original_checksum

    with httpx.Client() as client:
        client.delete(f"{COORDINATOR_URL}/api/data/{object_id}")


def test_failure_detection_and_under_replicated():
    """
    Proves:
    replication 3/3 -> fail one node -> coordinator detects failure -> 
    affected blocks become 2/3 -> blocks appear in under-replicated endpoint.
    """
    object_id = "test-fail-obj"
    original_data = os.urandom(1 * 1024 * 1024)
    
    with httpx.Client(timeout=10.0) as client:
        client.delete(f"{COORDINATOR_URL}/api/data/{object_id}")
        client.post(f"{COORDINATOR_URL}/api/data/{object_id}", content=original_data)
        
        # 1. Verify 3/3 initially (under-replicated should not contain our block)
        blocks_resp = client.get(f"{COORDINATOR_URL}/api/blocks")
        blocks = [b for b in blocks_resp.json() if b["object_id"] == object_id]
        assert len(blocks) == 1
        block_id = blocks[0]["block_id"]
        
        ur_resp = client.get(f"{COORDINATOR_URL}/api/blocks/under-replicated")
        ur_blocks = [b["block_id"] for b in ur_resp.json()]
        assert block_id not in ur_blocks
        
        # Find which nodes hold the block
        nodes_holding_block = []
        for node_url in STORAGE_NODES:
            try:
                if client.head(f"{node_url}/blocks/{block_id}").status_code == 200:
                    # Map URL to node_id (assuming node_id is something like storage1)
                    node_id = node_url.split("//")[1].split(":")[0]
                    if "localhost" in node_id:
                        # Fallback for local testing
                        node_id = f"storage{node_url[-1]}"
                    nodes_holding_block.append(node_id)
            except:
                pass
                
        assert len(nodes_holding_block) == 3
        
        node_to_fail = nodes_holding_block[0]
        
        # 2. Fail one node
        client.post(f"{COORDINATOR_URL}/api/admin/fail/{node_to_fail}")
        
        # 3. Wait for coordinator to detect (Poll interval 2s + threshold 3 = ~6-8s)
        time.sleep(10)
        
        # 4. Check events
        events_resp = client.get(f"{COORDINATOR_URL}/api/events")
        events = events_resp.json()
        failure_detected = any(e["event_type"] == "NODE_FAILURE_DETECTED" and str(node_to_fail) in e["details"] for e in events)
        assert failure_detected, "NODE_FAILURE_DETECTED event not found"
        
        # 5. Check under-replicated endpoint
        ur_resp_after = client.get(f"{COORDINATOR_URL}/api/blocks/under-replicated")
        ur_blocks_after = [b["block_id"] for b in ur_resp_after.json()]
        assert block_id in ur_blocks_after, "Block not marked as under-replicated"
        
        # The endpoint also returns the count of healthy replicas
        ur_block_info = next(b for b in ur_resp_after.json() if b["block_id"] == block_id)
        assert ur_block_info["healthy_replicas"] == 2
        
        # Recover the node
        client.post(f"{COORDINATOR_URL}/api/admin/recover/{node_to_fail}")
        time.sleep(5)
        
        client.delete(f"{COORDINATOR_URL}/api/data/{object_id}")
