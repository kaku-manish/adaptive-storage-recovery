import aiosqlite
import os
import time

DB_PATH = os.environ.get("DB_PATH", "/app/data/coordinator.db")

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS nodes (
                node_id TEXT PRIMARY KEY,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                last_heartbeat REAL NOT NULL,
                consecutive_failures INTEGER DEFAULT 0,
                created_at REAL NOT NULL
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS objects (
                object_id TEXT PRIMARY KEY,
                size_bytes INTEGER NOT NULL,
                created_at REAL NOT NULL
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS blocks (
                block_id TEXT PRIMARY KEY,
                object_id TEXT NOT NULL,
                block_index INTEGER NOT NULL,
                size_bytes INTEGER NOT NULL,
                checksum TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY(object_id) REFERENCES objects(object_id) ON DELETE CASCADE
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS block_replicas (
                block_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                replica_status TEXT NOT NULL,
                created_at REAL NOT NULL,
                PRIMARY KEY (block_id, node_id),
                FOREIGN KEY (block_id) REFERENCES blocks(block_id) ON DELETE CASCADE,
                FOREIGN KEY (node_id) REFERENCES nodes(node_id) ON DELETE CASCADE
            )
        ''')
        
        await db.execute('''
            CREATE TABLE IF NOT EXISTS events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                details TEXT,
                created_at REAL NOT NULL
            )
        ''')

        await db.execute('''
            CREATE TABLE IF NOT EXISTS recovery_jobs (
                job_id TEXT PRIMARY KEY,
                block_id TEXT NOT NULL,
                source_node TEXT NOT NULL,
                destination_node TEXT NOT NULL,
                total_bytes INTEGER NOT NULL,
                transferred_bytes INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                started_at REAL NOT NULL,
                completed_at REAL,
                checksum_verified INTEGER DEFAULT 0
            )
        ''')
        
        # Ensure telemetry columns in nodes table if they don't exist
        for col_def in [
            ("block_count", "INTEGER DEFAULT 0"),
            ("stored_bytes", "INTEGER DEFAULT 0"),
            ("cpu_percent", "REAL DEFAULT 0"),
            ("memory_percent", "REAL DEFAULT 0"),
            ("disk_percent", "REAL DEFAULT 0"),
            ("network_rx_bytes", "REAL DEFAULT 0"),
            ("network_tx_bytes", "REAL DEFAULT 0")
        ]:
            try:
                await db.execute(f"ALTER TABLE nodes ADD COLUMN {col_def[0]} {col_def[1]}")
            except Exception:
                pass

        await db.commit()

async def get_db():
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    return db
