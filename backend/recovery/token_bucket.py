import time
import asyncio

class TokenBucket:
    def __init__(self, rate_mbps: float, burst_capacity_mb: float = 4.0):
        self.rate_bytes_per_sec = rate_mbps * 1024 * 1024
        self.capacity_bytes = burst_capacity_mb * 1024 * 1024
        self.tokens = self.capacity_bytes
        self.last_update = time.time()
        self.lock = asyncio.Lock()
        
    def set_rate(self, rate_mbps: float):
        self.rate_bytes_per_sec = rate_mbps * 1024 * 1024
        # We can dynamically adjust capacity to be roughly 2 seconds of burst or a minimum
        self.capacity_bytes = max(4.0 * 1024 * 1024, self.rate_bytes_per_sec * 0.5)

    def _refill(self):
        now = time.time()
        elapsed = now - self.last_update
        if elapsed > 0:
            new_tokens = elapsed * self.rate_bytes_per_sec
            self.tokens = min(self.capacity_bytes, self.tokens + new_tokens)
            self.last_update = now

    async def consume(self, num_bytes: int):
        while True:
            async with self.lock:
                self._refill()
                if self.tokens >= num_bytes:
                    self.tokens -= num_bytes
                    return
                
                # Not enough tokens, calculate wait time
                deficit = num_bytes - self.tokens
                wait_time = deficit / self.rate_bytes_per_sec if self.rate_bytes_per_sec > 0 else 0.1
                
            # Sleep outside the lock so other tasks could potentially refill/use if we had multiple consumers
            await asyncio.sleep(max(0.01, wait_time))
