from pydantic import BaseModel

class ControllerConfig(BaseModel):
    latency_limit_ms: float = 200.0
    throughput_floor_percent: float = 80.0
    sample_interval_seconds: float = 2.0
    starting_rate_mbps: float = 50.0
    min_rate_mbps: float = 5.0
    max_rate_mbps: float = 100.0
    critical_multiplier: float = 0.70
    recovery_multiplier: float = 1.15
    cooldown_seconds: float = 5.0
