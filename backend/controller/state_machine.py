import time

class AdaptiveStateMachine:
    def __init__(self, config):
        self.config = config
        self.state = "NORMAL"
        self.current_rate = config.starting_rate_mbps
        self.bad_samples = 0
        self.good_samples = 0
        self.last_change_time = 0
        self.history = []

    def evaluate(self, current_p99, current_throughput, baseline_p99, baseline_throughput, 
                 disk_percent=0.0, network_percent=0.0, is_recovery_running=True):
        now = time.time()
        
        if not is_recovery_running:
            self.state = "IDLE"
            self.bad_samples = 0
            self.good_samples = 0
            return self.state, self.current_rate, False
            
        throughput_ratio = (current_throughput / baseline_throughput) if baseline_throughput > 0 else 1.0
        
        # Check critical conditions
        crit_reasons = []
        if current_p99 > self.config.latency_limit_ms:
            crit_reasons.append(f"p99 ({current_p99:.1f}ms) > limit ({self.config.latency_limit_ms:.1f}ms)")
        if throughput_ratio < 0.80:
            crit_reasons.append(f"throughput drop ({(1-throughput_ratio)*100:.1f}%) > 20%")
        if disk_percent > 92.0:
            crit_reasons.append(f"disk saturation ({disk_percent:.1f}%) > 92%")
        if network_percent > 92.0:
            crit_reasons.append(f"network saturation ({network_percent:.1f}%) > 92%")
            
        is_bad = len(crit_reasons) > 0
        
        # Check normal conditions
        is_good = (
            current_p99 < (self.config.latency_limit_ms * 0.80) and
            throughput_ratio >= 0.90 and
            disk_percent < 80.0 and
            network_percent < 80.0
        )
        
        if is_bad:
            self.bad_samples += 1
            self.good_samples = 0
        elif is_good:
            self.good_samples += 1
            self.bad_samples = 0
        else:
            self.bad_samples = 0
            self.good_samples = 0

        old_state = self.state
        old_rate = self.current_rate
        new_rate = self.current_rate
        reason = "Stable"
        
        if self.bad_samples >= 3:
            self.state = "CRITICAL"
            new_rate = self.current_rate * 0.70
            reason = f"CRITICAL: {'; '.join(crit_reasons)}"
        elif self.good_samples >= 3:
            self.state = "RECOVERING" if self.state != "NORMAL" else "NORMAL"
            new_rate = self.current_rate * 1.15
            reason = "NORMAL: Headroom available; accelerating recovery"
        elif is_bad and self.state != "CRITICAL":
            self.state = "WARNING"
            reason = f"WARNING: Approaching limits: {'; '.join(crit_reasons)}"
        elif 0.80 <= throughput_ratio < 0.90 or current_p99 >= (self.config.latency_limit_ms * 0.80):
            self.state = "WARNING"
            reason = "WARNING: Moderate load detected; holding rate"

        # Apply bounds
        new_rate = max(self.config.min_rate_mbps, min(self.config.max_rate_mbps, new_rate))
        
        changed = False
        if new_rate != old_rate:
            if now - self.last_change_time < self.config.cooldown_seconds:
                new_rate = old_rate
            else:
                self.current_rate = new_rate
                self.last_change_time = now
                changed = True
        elif self.state != old_state:
            self.last_change_time = now
            changed = True
            
        if changed:
            decision = {
                "timestamp": now,
                "state_before": old_state,
                "state_after": self.state,
                "p99_ms": round(current_p99, 2),
                "baseline_p99_ms": round(baseline_p99, 2),
                "throughput_mbps": round(current_throughput, 2),
                "baseline_throughput_mbps": round(baseline_throughput, 2),
                "throughput_ratio": round(throughput_ratio, 2),
                "disk_percent": round(disk_percent, 2),
                "network_percent": round(network_percent, 2),
                "old_rate_mbps": round(old_rate, 2),
                "new_rate_mbps": round(new_rate, 2),
                "trigger_reason": reason,
                # Backwards compatible aliases
                "old_rate": round(old_rate, 2),
                "new_rate": round(new_rate, 2),
                "p99": round(current_p99, 2),
                "throughput": round(current_throughput, 2),
                "reason": reason
            }
            self.history.append(decision)
            if len(self.history) > 100:
                self.history.pop(0)
            
        return self.state, new_rate, changed
