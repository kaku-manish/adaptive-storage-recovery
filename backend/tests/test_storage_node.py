import os
import pytest
from fastapi.testclient import TestClient
import hashlib

# Ensure DATA_DIR is set for tests
os.environ["DATA_DIR"] = "/tmp/test_data"
os.makedirs(os.environ["DATA_DIR"], exist_ok=True)

from storage_node.main import app, app_metrics

client = TestClient(app)

@pytest.fixture(autouse=True)
def reset_state():
    # Reset failure state
    client.post("/admin/recover")
    # Reset metrics
    app_metrics["reads_total"] = 0
    app_metrics["writes_total"] = 0
    app_metrics["read_bytes_total"] = 0
    app_metrics["write_bytes_total"] = 0
    app_metrics["request_errors_total"] = 0
    
    # Clean up test files
    for f in os.listdir(os.environ["DATA_DIR"]):
        os.remove(os.path.join(os.environ["DATA_DIR"], f))
    
    yield

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_write_read_block():
    block_id = "test_block_1"
    data = b"Hello, Distributed Storage!"
    expected_checksum = hashlib.sha256(data).hexdigest()
    
    # Write block
    response = client.post(f"/blocks/{block_id}", content=data)
    assert response.status_code == 200
    resp_data = response.json()
    assert resp_data["block_id"] == block_id
    assert resp_data["size_bytes"] == len(data)
    assert resp_data["checksum"] == expected_checksum
    
    # Read block
    read_response = client.get(f"/blocks/{block_id}")
    assert read_response.status_code == 200
    assert read_response.content == data
    
    # Check metrics
    metrics = client.get("/metrics").json()
    assert metrics["app"]["writes_total"] == 1
    assert metrics["app"]["write_bytes_total"] == len(data)
    assert metrics["app"]["reads_total"] == 1
    assert metrics["app"]["read_bytes_total"] == len(data)

def test_head_block():
    block_id = "test_block_head"
    data = b"Data for head"
    client.post(f"/blocks/{block_id}", content=data)
    
    response = client.head(f"/blocks/{block_id}")
    assert response.status_code == 200
    assert response.headers["content-length"] == str(len(data))

def test_delete_block():
    block_id = "test_block_delete"
    client.post(f"/blocks/{block_id}", content=b"Delete me")
    
    # Delete
    del_response = client.delete(f"/blocks/{block_id}")
    assert del_response.status_code == 200
    
    # Verify not found
    read_response = client.get(f"/blocks/{block_id}")
    assert read_response.status_code == 404

def test_failure_mode():
    block_id = "fail_test_block"
    client.post(f"/blocks/{block_id}", content=b"fail test")
    
    # Fail node
    fail_response = client.post("/admin/fail")
    assert fail_response.status_code == 200
    
    # Verify health
    health_response = client.get("/health")
    assert health_response.status_code == 503
    
    # Verify reads block
    read_response = client.get(f"/blocks/{block_id}")
    assert read_response.status_code == 503
    
    # Recover node
    rec_response = client.post("/admin/recover")
    assert rec_response.status_code == 200
    
    # Verify read works again
    read_again = client.get(f"/blocks/{block_id}")
    assert read_again.status_code == 200
