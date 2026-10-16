# Home Assistant Integration

This document describes the Home Assistant integration for the Smart Home Dashboard.

## Overview

The Smart Home Dashboard integrates with Home Assistant via WebSocket for real-time state synchronization and REST API for device control.

## Features

### WebSocket State Sync

- **Real-time updates**: Entity states sync every 60 seconds
- **Event-driven updates**: State changes trigger immediate dashboard updates
- **Read-only entities**: Sensors, binary sensors, and other read-only entities are monitored but not controlled

### REST Control

- **Service calls**: POST requests to `/api/services/<domain>/<service>` endpoints
- **Authentication**: Bearer token authentication via `HA_TOKEN`
- **Light Control**: Turn on/off with brightness control
- **Error handling**: Structured error responses on service call failures

## Architecture

### Components

1. **HA WebSocket Client** (`fn-ha-ws`)
   - WebSocket connection to `ws://<host>/api/websocket`
   - Auth frame: `{"type": "auth", "access_token": "<token>"}`
   - Subscribes to `state_changed` events
   - Publishes entity state to `ha/entity/<entity_id>/state` topic

2. **HA REST Controller** (`fn-ha-rest`)
   - Formats service call requests
   - Adds Bearer token to Authorization header
   - Sets Content-Type to `application/json`

3. **HTTP Request Node** (`http-ha`)
   - Sends POST requests to HA API
   - Returns structured response

## Environment Variables

```bash
# Home Assistant Configuration
HA_URL=http://homeassistant.local:8123
HA_TOKEN=<your-access-token>
HA_ENTITY_ID=light.kitchen
```

## Deployment

### 1. Configure Environment

Set the following variables in `/root/.node-red/.env`:

```bash
HA_URL=http://homeassistant.local:8123
HA_TOKEN=<your-actual-token>
HA_ENTITY_ID=light.kitchen
```

### 2. Import Flows

The HA tab and nodes are included in `flows/99-other.flow.json`. The flows are automatically imported when `deploy/setup.sh` runs.

### 3. Verify Connection

1. Navigate to the Home Assistant tab in the dashboard
2. Check the WebSocket connection status (green = connected)
3. Verify state sync is working (entities should appear)

## Authentication

### Obtaining Access Token

1. Open Home Assistant Settings
2. Go to Settings → Users → Your User → Access Tokens
3. Create a new token with `homeassistant` scope
4. Copy the token and set it in `HA_TOKEN`

### Auth Flow

```
1. WebSocket connects to ws://<host>/api/websocket
2. Server sends: {"type": "auth_required"}
3. Client responds: {"type": "auth", "access_token": "<token>"}
4. Server sends: {"type": "auth_ok"}
5. Client sends: {"type": "get_states"}
6. Server sends: list of all states
7. Client subscribes to: {"type": "subscribe_events", "event_type": "state_changed"}
```

## Service Calls

### Turn On Light

```bash
curl -X POST "http://homeassistant.local:8123/api/services/light/turn_on" \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"entity_id": "light.kitchen", "brightness_pct": 80}'
```

### Turn Off Light

```bash
curl -X POST "http://homeassistant.local:8123/api/services/light/turn_off" \
  -H "Authorization: Bearer <token>" \
  -d '{"entity_id": "light.bedroom"}'
```

## Troubleshooting

### WebSocket Not Connecting

- Check `HA_URL` format (must be `http://`, will be converted to `ws://`)
- Verify Home Assistant is running on the specified host
- Check firewall allows WebSocket connections on port 8123
- Review Node-RED logs: `tail -f /root/.node-red/start.log`

### Authentication Failed

- Verify `HA_TOKEN` is correct
- Check token has `homeassistant` scope
- Ensure token hasn't expired

### State Sync Not Working

- Check WebSocket is connected (green status indicator)
- Verify entity IDs match HA entity names
- Check `ha/state_count` debug output

### Service Calls Failing

- Verify `HA_URL` and `HA_TOKEN` are set
- Check service name is correct (e.g., `light/turn_on`, not `light.turn_on`)
- Review error messages in debug node

## Entity Mapping

The dashboard uses the following entity domains:

| Domain | Read-Only | Controllable |
|--------|-----------|--------------|
| light | ✗ | ✓ |
| switch | ✗ | ✓ |
| sensor | ✓ | ✗ |
| binary_sensor | ✓ | ✗ |
| weather | ✓ | ✗ |

## Testing

Run the HA integration tests:

```bash
cd /root/.hermes/projects/smart-home-dashboard
python3 -m pytest tests/test_ha_integration.py -v
```

## Security Considerations

- `HA_TOKEN` should be stored in `/root/.node-red/.env` (not committed to git)
- Dashboard is accessible via LAN only (no TLS by default)
- Consider enabling Node-RED adminAuth for additional security
- For production, enable TLS via `https` setting in `config/settings.js`

## References

- [Home Assistant WebSocket API](https://www.home-assistant.io/integrations/websocket/)
- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest/)
- [Node-RED WebSocket Node](https://nodered.org/docs/user-guide/modules/node-red-node-websocket/)
