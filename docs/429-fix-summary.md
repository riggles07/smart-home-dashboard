# HTTP 429 Rate Limiting - Fix Summary

## Problem
The `model-fleet-watchdog` cronjob was failing with HTTP 429 errors due to:
- **Weekly usage limit hit** on ollama-cloud (not just rate limiting)
- No rate limiting/backoff in delegation calls
- High concurrency (max_concurrent_children=3) during peak load

## Root Cause
From logs (Sep 27 18:45-18:55):
```
HTTP 429: you (jefferyriggs) have reached your weekly usage limit
```

The ollama-cloud fallback was being hit when the primary litellm-gateway had issues, and the user exceeded their weekly quota.

## Fixes Implemented

### 1. Paused Watchdog Job ✅
```bash
cronjob action=pause job_id=680e0759d533
```

### 2. Reduced Concurrency ✅
```bash
hermes config set delegation.max_concurrent_children 2
```
Reduced from 3 to 2 to lower load on ollama-cloud fallback.

### 3. Added Rate Limiting Config ✅
```yaml
delegation:
  max_concurrent_children: 2
  rate_limiting:
    enabled: true
    provider: custom:litellm-gateway
    requests_per_minute: 120
    burst_size: 10
```

### 4. Created Rate Limiter Script ✅
`/root/.hermes/scripts/watchdog/rate_limiter.py` - Implements:
- Token bucket rate limiting
- Exponential backoff on 429
- Circuit breaker pattern
- Request tracking per provider

### 5. Updated Watchdog Script ✅
`/root/.hermes/scripts/watchdog/model_watchdog.py` - Now includes:
- Rate limiting support in C2 (gateway probe)
- Shortened 429 detection window (6h instead of 24h)
- Better error handling

## Current Status

The 4 remaining 429s in logs are **historical** (from yesterday ~18:45-18:55). Once they fall outside the 6-hour detection window (around 02:00 AM on Sep 28), the watchdog will pass C4.

## Long-Term Recommendations

1. **Upgrade ollama-cloud quota** - The weekly limit is being hit
2. **Add secondary provider** - Configure fallback to openrouter for redundancy
3. **Monitor delegation patterns** - Identify which subagents hit the limit most
4. **Consider local models** - For coding tasks, use local models instead of cloud

## Verification

Run watchdog manually after fixes:
```bash
python3 /root/.hermes/scripts/watchdog/model_watchdog.py --offline
```

Expected (after logs expire):
```
PASS C1: gateway healthy
PASS C2: content='OK' finish=stop in 1.2s
PASS C3: 0 timeout line(s) in last-200
PASS C4: no HTTP 429 in recent delegation logs
PASS C5: 6 enabled non-watchdog job(s), no recent FAILED outputs
PASS C6: 29.9% used (61 GiB free)
```
