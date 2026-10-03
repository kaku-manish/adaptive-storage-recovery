import asyncio
import time
import os
import httpx
from recovery.chunk_transfer import stream_transfer
from recovery.token_bucket import TokenBucket

DEFAULT_RECOVERY_RATE_MBPS = float(os.getenv("DEFAULT_RECOVERY_RATE_MBPS", "50"))
MIN_RECOVERY_RATE_MBPS = float(os.getenv("MIN_RECOVERY_RATE_MBPS", "5"))
MAX_RECOVERY_RATE_MBPS = float(os.getenv("MAX_RECOVERY_RATE_MBPS", "100"))

class RecoveryWorker:
    def __init__(self, db_getter):
        self.get_db = db_getter
        self.status = "IDLE"
        self.is_running = False
        self.task = None
        
        self.rate_mbps = DEFAULT_RECOVERY_RATE_MBPS
        self.token_bucket = TokenBucket(self.rate_mbps)
        
        # Stats
        self.total_blocks = 0
        self.completed_blocks = 0
        self.remaining_blocks = 0
        self.total_bytes = 0
        self.completed_bytes = 0
        self.remaining_bytes = 0
        self.start_time = 0
        self.current_rate_mbps = 0.0
        self.mode = "ADAPTIVE"
        self.active_jobs = set() # Block-level locking

    def set_rate(self, rate_mbps: float, mode: str = None):
        rate_mbps = max(MIN_RECOVERY_RATE_MBPS, min(MAX_RECOVERY_RATE_MBPS, rate_mbps))
        self.rate_mbps = rate_mbps
        if mode:
            self.mode = mode
        self.token_bucket.set_rate(self.rate_mbps)

    async def start(self, mode: str = "ADAPTIVE"):
        if self.is_running:
            return
        self.mode = mode
        self.is_running = True
        self.status = "STARTING"
        self.start_time = time.time()
        self.task = asyncio.create_task(self._run_recovery_loop())

    async def stop(self):
        self.is_running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.status = "IDLE"
        self.active_jobs.clear()

    def get_status(self):
        elapsed = time.time() - self.start_time if self.start_time > 0 and self.status in ["RUNNING", "THROTTLED", "STARTING"] else 0
        
        if elapsed > 0:
            self.current_rate_mbps = (self.completed_bytes / (1024*1024)) / elapsed
            
        percentage = 0
        if self.total_blocks > 0:
            percentage = (self.completed_blocks / self.total_blocks) * 100
            
        estimated_remaining = 0
        if self.current_rate_mbps > 0 and self.remaining_bytes > 0:
            estimated_remaining = (self.remaining_bytes / (1024*1024)) / self.current_rate_mbps

        display_status = self.status
        if self.status == "RUNNING" and self.rate_mbps <= 15.0:
            display_status = "THROTTLED"

        is_active = self.is_running and (self.remaining_blocks > 0 or self.status in ["RUNNING", "THROTTLED", "STARTING"])

        return {
            "running": is_active,
            "status": display_status if is_active else "IDLE",
            "mode": self.mode if is_active else None,
            "total_blocks": self.total_blocks if is_active else 0,
            "completed_blocks": self.completed_blocks if is_active else 0,
            "remaining_blocks": self.remaining_blocks if is_active else 0,
            "total_bytes": self.total_bytes if is_active else 0,
            "completed_bytes": self.completed_bytes if is_active else 0,
            "remaining_bytes": self.remaining_bytes if is_active else 0,
            "progress_percent": round(percentage, 2) if is_active else None,
            "configured_rate_mbps": round(self.rate_mbps, 2) if is_active else None,
            "actual_rate_mbps": round(self.current_rate_mbps, 2) if is_active else None,
            "elapsed_seconds": round(elapsed, 2) if is_active else None,
            "eta_seconds": round(estimated_remaining, 2) if is_active else None
        }

    async def _run_recovery_loop(self):
        self.status = "RUNNING"
        while self.is_running:
            try:
                await self._process_next_batch()
            except Exception as e:
                print(f"Recovery loop error: {e}")
            
            await asyncio.sleep(2)
            
        self.status = "COMPLETED" if self.remaining_blocks == 0 else "IDLE"

    async def _process_next_batch(self):
        db = await self.get_db()
        try:
            query = '''
                SELECT b.block_id, b.size_bytes, b.checksum, COUNT(r.node_id) as healthy_replicas
                FROM blocks b
                LEFT JOIN block_replicas r ON b.block_id = r.block_id AND r.replica_status = 'STORED'
                LEFT JOIN nodes n ON r.node_id = n.node_id AND n.status = 'HEALTHY'
                GROUP BY b.block_id
                HAVING healthy_replicas < 3
            '''
            async with db.execute(query) as cur:
                under_replicated = [dict(r) for r in await cur.fetchall()]
                
            if not under_replicated:
                self.remaining_blocks = 0
                self.remaining_bytes = 0
                self.status = "IDLE"
                return
                
            self.status = "RUNNING"
            self.remaining_blocks = len(under_replicated)
            self.remaining_bytes = sum(b['size_bytes'] for b in under_replicated)
            self.total_blocks = self.completed_blocks + self.remaining_blocks
            
            # Filter out blocks already being recovered
            available_blocks = [b for b in under_replicated if b["block_id"] not in self.active_jobs]
            if not available_blocks:
                return

            block = available_blocks[0]
            block_id = block["block_id"]
            expected_checksum = block["checksum"]
            self.active_jobs.add(block_id)
            
            job_id = f"rec-{int(time.time()*1000)}-{block_id}"
            now = time.time()
            
            try:
                async with db.execute('''
                    SELECT n.url FROM block_replicas r
                    JOIN nodes n ON r.node_id = n.node_id
                    WHERE r.block_id = ? AND r.replica_status = 'STORED' AND n.status = 'HEALTHY'
                    LIMIT 1
                ''', (block_id,)) as cur:
                    source = await cur.fetchone()
                    
                if not source:
                    return
                    
                source_url = source["url"]
                
                async with db.execute('''
                    SELECT n.node_id, n.url FROM nodes n
                    WHERE n.status = 'HEALTHY' AND n.node_id NOT IN (
                        SELECT node_id FROM block_replicas WHERE block_id = ?
                    )
                    LIMIT 1
                ''', (block_id,)) as cur:
                    dest = await cur.fetchone()
                    
                if not dest:
                    return
                    
                dest_node_id = dest["node_id"]
                dest_url = dest["url"]
                
                await db.execute('''
                    INSERT INTO recovery_jobs (job_id, block_id, source_node, destination_node, total_bytes, transferred_bytes, status, started_at, completed_at, checksum_verified)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (job_id, block_id, source_url, dest_node_id, block["size_bytes"], 0, "RUNNING", now, None, 0))
                await db.commit()
                
                retries = 3
                for attempt in range(retries):
                    try:
                        transferred_size, calculated_checksum = await stream_transfer(
                            source_url, dest_url, block_id, self.token_bucket, chunk_size=1024*1024
                        )
                        
                        if calculated_checksum != expected_checksum:
                            if attempt == retries - 1:
                                raise Exception(f"Checksum verification failed: expected {expected_checksum}, got {calculated_checksum}")
                            continue
                            
                        comp_time = time.time()
                        await db.execute('''
                            INSERT INTO block_replicas (block_id, node_id, replica_status, created_at)
                            VALUES (?, ?, ?, ?)
                            ON CONFLICT(block_id, node_id) DO UPDATE SET replica_status='STORED'
                        ''', (block_id, dest_node_id, "STORED", comp_time))
                        
                        await db.execute('''
                            UPDATE recovery_jobs 
                            SET transferred_bytes=?, status='COMPLETED', completed_at=?, checksum_verified=1
                            WHERE job_id=?
                        ''', (transferred_size, comp_time, job_id))
                        
                        await db.execute('''
                            INSERT INTO events (event_type, details, created_at)
                            VALUES (?, ?, ?)
                        ''', ("BLOCK_RECOVERED", f'{{"block_id": "{block_id}", "node_id": "{dest_node_id}"}}', comp_time))
                        
                        self.completed_blocks += 1
                        self.completed_bytes += transferred_size
                        self.remaining_blocks = max(0, self.remaining_blocks - 1)
                        self.remaining_bytes = max(0, self.remaining_bytes - transferred_size)
                        
                        if self.remaining_blocks == 0:
                            await db.execute('''
                                INSERT INTO events (event_type, details, created_at)
                                VALUES (?, ?, ?)
                            ''', ("FULL_REDUNDANCY_RESTORED", '{"status": "3/3 Replicas Restored"}', comp_time))
                            
                        await db.commit()
                        break
                    except Exception as e:
                        if attempt == retries - 1:
                            await db.execute('''
                                UPDATE recovery_jobs SET status='FAILED', completed_at=? WHERE job_id=?
                            ''', (time.time(), job_id))
                            await db.commit()
                            raise
            except Exception as e:
                print(f"Failed to recover {block_id}: {e}")
            finally:
                self.active_jobs.discard(block_id)
        finally:
            await db.close()
