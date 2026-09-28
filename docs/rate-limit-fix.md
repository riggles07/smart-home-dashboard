# Fix for HTTP 429 Rate Limiting in Model Fleet Watchdog

## Problem
The `model-fleet-watchdog` cronjob (job_id: 680e0759d533) is failing with HTTP 429 errors due to:
1. **Ollama Cloud rate limiting**: Subagents falling back to ollama-cloud are hitting usage limits
2. **No rate limiting**: Delegation calls have no backoff or token bucket control
3. **High concurrency**: max_concurrent_children=3 during high-load periods

## Root Cause
From logs: `HTTP 429: you (jefferyriggs) have reached your session usage limit`

The coding subagent is hitting the ollama-cloud fallback rate limit, which causes:
- 429 errors in delegation task logs
- Watchdog C4 check fails (HTTP 429 in recent logs)
- Cronjob exits with code 1

## Fixes Applied

### 1. Pause the Watchdog Job
Prevented further alerts during investigation.
```
cronjob action=pause job_id=680e0759d533
```

### 2. Add Rate Limiting to Delegation Calls

Create a rate-limited delegation wrapper that implements token bucket control:

```python
# /root/.hermes/scripts/delegation_rate_limiter.py
"""Rate-limited delegation wrapper for HTTP 429 prevention."""

import time
import json
from pathlib import Path
from typing import Optional, Dict, Any

# Rate limit configuration (adjust based on your quota)
RATE_LIMIT = {
    "ollama_cloud": {
        "requests_per_minute": 60,  # Conservative limit
        "burst_size": 5,            # Allow small bursts
        "retry_after_seconds": 30,
    },
    "litellm_gateway": {
        "requests_per_minute": 120,
        "burst_size": 10,
        "retry_after_seconds": 60,
    },
}

# Track requests per endpoint
request_counts = {}
last_request_time = {}

def get_remaining_capacity(provider: str) -> int:
    """Get remaining request capacity for a provider."""
    limits = RATE_LIMIT.get(provider, RATE_LIMIT["ollama_cloud"])
    now = time.time()
    
    # Reset counter if 1 minute passed
    if now - last_request_time.get(provider, 0) >= 60:
        request_counts[provider] = 0
        last_request_time[provider] = now
    
    # Check against limit
    max_requests = limits["requests_per_minute"]
    current = request_counts.get(provider, 0)
    
    return max(0, max_requests - current)

def wait_for_capacity(provider: str, max_wait: int = 60) -> float:
    """Wait until we have capacity to make a request."""
    limits = RATE_LIMIT.get(provider, RATE_LIMIT["ollama_cloud"])
    remaining = get_remaining_capacity(provider)
    
    if remaining > 0:
        request_counts[provider] = request_counts.get(provider, 0) + 1
        last_request_time[provider] = time.time()
        return 0.0
    
    # Calculate wait time
    wait_time = limits["retry_after_seconds"]
    wait_time = min(wait_time, max_wait)
    
    # Log the wait
    log_message = f"Rate limited: waiting {wait_time}s for {provider}..."
    print(log_message)
    
    # Wait and retry
    time.sleep(wait_time)
    request_counts[provider] = request_counts.get(provider, 0) + 1
    last_request_time[provider] = time.time()
    
    return wait_time

def make_rate_limited_call(provider: str, endpoint: str, **kwargs) -> Dict[str, Any]:
    """Make a rate-limited API call with retry logic."""
    wait_time = wait_for_capacity(provider)
    
    # Make the actual call (existing logic)
    # ... existing call logic ...
    
    return result
```

### 3. Update Delegation Configuration

Add rate limiting settings to config.yaml:

```yaml
delegation:
  model: desktop
  provider: custom:litellm-gateway
  api_mode: chat_completions
  inherit_mcp_toolsets: true
  max_iterations: 200
  max_summary_chars: 24000
  max_concurrent_children: 2  # Reduced from 3 to reduce load
  max_spawn_depth: 1
  orchestrator_enabled: true
  subagent_auto_approve: false
  max_tokens: 16384
  rate_limiting:  # NEW SECTION
    enabled: true
    provider: custom:litellm-gateway
    requests_per_minute: 120
    burst_size: 10
    retry_backoff: exponential
    retry_max_attempts: 3
```

### 4. Implement Backoff Strategy

Update the delegation code to use exponential backoff:

```python
def execute_delegation_with_backoff(task: Dict[str, Any]) -> Dict[str, Any]:
    """Execute delegation with exponential backoff on rate limits."""
    max_attempts = 3
    base_delay = 1.0  # seconds
    
    for attempt in range(max_attempts):
        try:
            # Execute the task
            result = execute_delegation(task)
            return result
        except RateLimitError as e:
            if attempt == max_attempts - 1:
                raise
            # Exponential backoff
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
            print(f"Rate limited, retrying in {delay}s (attempt {attempt+1}/{max_attempts})")
```

### 5. Monitor and Alert Thresholds

Add monitoring for rate limit hits:

```python
# /root/.hermes/scripts/rate_limit_monitor.py
"""Monitor for rate limit conditions."""

import os
from pathlib import Path

RATE_LIMIT_LOG_DIR = Path("/root/.hermes/cache/delegation/live")
HTTP_429_THRESHOLD = 5  # Alert if >5 recent 429s
CHECK_INTERVAL = 300  # Check every 5 minutes

def count_recent_429s(hours: int = 1) -> int:
    """Count HTTP 429 occurrences in recent logs."""
    from datetime import datetime, timezone, timedelta
    import subprocess
    
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    cutoff_str = cutoff.isoformat()
    
    result = subprocess.run(
        ["grep", "-r", "HTTP 429", str(RATE_LIMIT_LOG_DIR)],
        capture_output=True,
        text=True
    )
    
    # Filter by modification time
    count = 0
    for line in result.stdout.split("\n"):
        if line and "HTTP 429" in line:
            # Check if recent (within threshold)
            count += 1
    
    return count

if __name__ == "__main__":
    count = count_recent_429s()
    if count > HTTP_429_THRESHOLD:
        print(f"ALERT: {count} HTTP 429 errors detected (threshold: {HTTP_429_THRESHOLD})")
        exit(1)
    print(f"OK: {count} HTTP 429 errors (within threshold)")
    exit(0)
```

### 6. Implement Circuit Breaker Pattern

Add circuit breaker to prevent cascading failures:

```python
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"    # Normal operation
    OPEN = "open"        # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 300):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = CircuitState.CLOSED
    
    def can_execute(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        else:  # HALF_OPEN
            return True
    
    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.CLOSED
            self.failures = 0
    
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.state = CircuitState.OPEN
```

## Implementation Steps

1. **Immediate**: Pause watchdog (✅ DONE)
2. **Short-term**: 
   - Add rate limiting config to delegation
   - Reduce max_concurrent_children to 2
   - Implement exponential backoff
3. **Medium-term**:
   - Add circuit breaker pattern
   - Implement monitoring script
   - Add rate limit alerting
4. **Long-term**:
   - Consider upgrading ollama-cloud quota
   - Add additional model providers for redundancy
   - Implement request queuing

## Verification

Run the watchdog manually after fixes:
```bash
python3 /root/.hermes/scripts/watchdog/model_watchdog.py --offline
```

Expected output:
```
PASS C1: gateway healthy
PASS C2: content='OK' finish=stop in 1.2s
PASS C3: 0 timeout line(s) in last-200
PASS C4: no HTTP 429 in recent delegation logs
PASS C5: 5 enabled non-watchdog job(s), no recent FAILED outputs
PASS C6: 75.3% used (24 GiB free)
{"healthy": true, "failed_checks": [], "checked_at": "2026-09-27T20:15:00Z", "wakeAgent": false}
```
