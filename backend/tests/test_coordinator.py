import os
import pytest
import asyncio
from fastapi.testclient import TestClient
import hashlib

# Ensure DB doesn't conflict
os.environ["DB_PATH"] = "/tmp/test_coordinator.db"

# We must import these after setting DB_PATH
from coordinator.main import app, get_db
from coordinator.database import init_db

client = TestClient(app)

@pytest.fixture(autouse=True)
async def setup_db():
    if os.path.exists(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])
    await init_db()
    yield
    if os.path.exists(os.environ["DB_PATH"]):
        os.remove(os.environ["DB_PATH"])

def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200

# Testing the rest of the endpoints usually requires a mock storage node.
# Since we need to prove an uploaded object is split into blocks, 3 replicas, physical existence, etc.
# we will create a robust integration test script for it.
