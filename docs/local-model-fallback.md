# Local Coding Model Fallback Configuration

## Overview
Configured LM Studio as a local fallback provider for the litellm-gateway to prevent HTTP 429 rate limiting issues from ollama-cloud.

## Configuration Changes

### 1. Added LM Studio Provider
```yaml
providers:
  custom:lm-studio:
    api: http://100.106.222.89:1234/v1
    base_url: http://100.106.222.89:1234/v1
    api_key: ''  # Key injected by litellm-gateway
    api_mode: chat_completions
    models:
      - google/gemma-4-12b
    context_length: 131072
```

### 2. Reordered Fallback Providers
```yaml
fallback_providers:
  - provider: custom:lm-studio     # Local, higher priority
    model: google/gemma-4-12b
    priority: 1
  - provider: ollama-cloud         # Remote, lower priority  
    model: glm-5.3
```

### 3. Added Model to Gateway
- `gemma-4-12b` added to `custom:litellm-gateway` models list

## How It Works

1. **Primary Route**: `custom:litellm-gateway` handles requests
2. **Fallback Chain**: When gateway fails or returns 429:
   - First tries: `custom:lm-studio` (local, no rate limits)
   - Second tries: `ollama-cloud` (original fallback)

## Benefits

- ✅ **No rate limits**: LM Studio runs locally, no API quotas
- ✅ **Lower latency**: Local connection vs remote API
- ✅ **Reliability**: Works even when ollama-cloud is rate-limited
- ✅ **Transparent**: No code changes needed, handled by litellm-gateway

## Testing

The probe script confirms LM Studio availability:
```bash
python3 /root/.hermes/scripts/litellm/probe_backend_catalogs.py
```

Expected output shows:
```
== LM Studio (desktop/fast host) (http://100.106.222.89:1234) ==
  google/gemma-4-e4b                     ctx=131072 loaded 
  google/gemma-4-12b                     ctx=262144 not-loaded 
  ...
```

## Files Modified

- `/root/.hermes/config.yaml` - Added provider, reordered fallbacks
- `/root/.hermes/scripts/reorder_fallback.py` - Reordering utility

## Verification

Run the watchdog to verify healthy routing:
```bash
python3 /root/.hermes/scripts/watchdog/model_watchdog.py --offline
```

Expected:
```
PASS C1: gateway healthy
PASS C2: content='OK' finish=stop in X.Xs
...
{"healthy": true, "wakeAgent": false}
```
