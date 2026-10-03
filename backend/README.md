# Adaptive Storage Recovery - Backend Microservices

Distributed storage control plane and data plane services implementing dynamic, feedback-controlled background recovery to guarantee client Service Level Objectives (SLOs).

---

## Directory Architecture

```
backend/
├── coordinator/       # Master Coordinator API, SQLite metadata DB, & Recovery Worker
├── controller/        # Adaptive Feedback Controller (FSM) & metric evaluators
├── storage_node/      # Physical chunk storage daemon (manages .blk files)
├── recovery/          # Token Bucket rate limiter & HTTP chunk stream transfer
├── client/            # Locust workload generator (LOW, MEDIUM, HIGH traffic profiles)
├── monitoring/        # Prometheus scrape configuration
├── tests/             # Pytest test suite for coordinator, storage nodes & rate limiting
├── run_backend.py     # Standalone backend service orchestrator
├── requirements.txt   # Python dependencies
└── .env.example       # Example environment variables
```

---

## Services & Ports

| Service | Port | Description |
|---|---|---|
| **Coordinator API** | `8000` | Metadata catalog, heartbeat detector, recovery dispatcher |
| **Adaptive Controller** | `8003` | Closed-loop state machine regulating recovery bandwidth |
| **Storage Node 1** | `8001` | Chunk storage daemon 1 |
| **Storage Node 2** | `8002` | Chunk storage daemon 2 |
| **Storage Node 3** | `8004` | Chunk storage daemon 3 |
| **Storage Node 4** | `8005` | Chunk storage daemon 4 |

---

## Quickstart

### 1. Prerequisites
- Python 3.10 to 3.13
- pip / venv

### 2. Setup Virtual Environment (Recommended)

```bash
cd backend
python -m venv .venv

# Windows CMD / PowerShell
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Run All Backend Services

```bash
python run_backend.py
```

This starts all 4 storage nodes, the coordinator, and the controller, performs health checks, and registers the nodes automatically.

- **Coordinator API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Controller API Docs (Swagger):** [http://localhost:8003/docs](http://localhost:8003/docs)

---

## Running Client Workloads

To simulate realistic client traffic (reads/writes) competing for I/O:

### Windows CMD:
```bash
client\start_workload.bat LOW 60
# Options: LOW, MEDIUM, HIGH (duration in seconds)
```

### PowerShell:
```powershell
powershell -ExecutionPolicy Bypass -File client/start_workload.ps1 -Profile MEDIUM -DurationSeconds 60
```

### Python Direct:
```bash
set WORKLOAD_PROFILE=HIGH
python -m locust -f client/locustfile.py --headless -u 100 -r 10 -t 60s --host http://localhost:8000
```

---

## Running Unit & Integration Tests

```bash
pytest tests/ -v
```

---

## Docker Deployment

To launch backend microservices with Prometheus and Grafana via Docker Compose from the root directory:

```bash
docker compose up --build -d
```
