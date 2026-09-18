# Hubitat Device State Monitoring

Live device state for the Smart Home Dashboard, implemented in
`flows/hubitat_integration.py` (`HubitatNode`) and surfaced as the
`hubitat-device-state` node in `flows/dashboard_configuration.py` /
`flows/dashboard-configuration.js`.

## What is read

Device attributes come from the Hubitat **Maker API**:

| Request | Purpose |
| --- | --- |
| `GET /apps/api/<app_id>/devices/all` | Every authorized device with its `attributes` in one request |
| `GET /apps/api/<app_id>/devices/<id>` | One device, same shape |

The attributes rendered on tiles are listed in `STATE_ATTRIBUTES` — switch,
level, hue, saturation, colour temperature, temperature, humidity, battery,
motion, contact, lock, presence, power/energy/voltage, illuminance and the
thermostat setpoints. `primary` picks the most meaningful one per device type
(switch > motion > contact > ... ) and `display` adds the unit from
`STATE_UNITS`.

## Refresh strategy: hybrid (push first, cached poll as fallback)

The repo has to work whether or not the hub can reach the dashboard, so the
strategy has two layers instead of committing to one.

**1. Push — hub event subscription (`subscribeStateEvents`)**

`POST`/`GET /postURL/<url>` registers the dashboard's HTTP endpoint with the
hub. Maker API then POSTs every device event
(`{"content": {"name": "switch", "value": "on", "deviceId": "101", ...}}`) to
the dashboard, and `handleDeviceEvent` / `onDeviceEvent` writes the attribute
straight through to the cache and publishes it on
`hubitat/device/<id>/state`. Tiles update the instant something changes and the
hub is not polled at all.

**2. Fallback — TTL-cached polling (`startStatePolling`)**

Push cannot be assumed: the hub is often LAN-only (no route back to the
dashboard), the POST URL is cleared when the dashboard moves to a new
address, and events raised while the dashboard restarts are lost. So:

* `startStatePolling()` refreshes all devices every `state_poll_interval` ms
  (default `60000`, matching the JS flow's `refresh || 60000`).
* Each read is served from a TTL cache (`state_ttl` seconds, default `5.0`,
  matching the dashboard's `5000` ms UI refresh). A 5-second tile refresh over
  N devices therefore costs **at most one `/devices/all` request per TTL
  window** rather than N requests — this is the caching that keeps the hub from
  being hammered.
* If `/devices/all` is unavailable, the poll degrades to per-device reads.

`stateRefreshStrategy()` reports the live posture (mode, primary, fallback,
poll interval, TTL, whether the subscription is enabled, whether the poller is
running) and the dashboard shows it via the status view.

### Tuning

| Setting | Config key | Env | Default |
| --- | --- | --- | --- |
| Cache TTL (s) | `stateTtl` | `HUBITAT_STATE_TTL` | `5.0` |
| Poll interval (ms) | `statePollInterval` | `HUBITAT_STATE_POLL_MS` | `60000` |
| HTTP timeout (s) | `stateTimeout` | `HUBITAT_STATE_TIMEOUT` | `10.0` |
| Subscription URL | `stateSubscriptionUrl` | `HUBITAT_STATE_SUBSCRIPTION_URL` | unset (poll only) |

`stateTtl = 0` disables caching (every read hits the hub). Non-positive or
unparseable tuning values fall back to the defaults.

## Dashboard wiring

* `getDeviceState(id)` — one device, cached.
* `getAllDeviceStates()` — all devices, one request, cached.
* `getStatusView()` / `refreshDeviceStates()` — fetch and build the tile view,
  publish `hubitat/device/<id>/state` per device, and set the node status
  indicator (green / yellow / red).
* `render_device_status(node)` in `flows/dashboard_configuration.py` maps that
  view onto the `hubitat-device-state` node for the dashboard's Devices page.
* `setupStateMonitoring()` — one call to subscribe (if configured), take the
  initial snapshot and start the poller.

## Failure behaviour

Every read degrades instead of raising:

* **Hub unreachable / timeout / non-2xx** → `DeviceState(ok=False, code=...)`.
* **Malformed payload** (`invalid_payload`) → reported; malformed *entries*
  inside a good `/devices/all` list are skipped and logged, not fatal.
* **Partial failure** → working devices stay usable; the broken ones keep their
  last known good values flagged `stale=True`, so a partially broken hub never
  blanks the dashboard.
* **Exponential back-off** (5s → 60s) after a failed poll so a dead hub is not
  hammered; the first success clears it.
* **Credentials** come from node config (`url` / `appId` / `accessToken` /
  `apiKey`) with `HUBITAT_*` env fallbacks. No token is ever logged or
  published to the dashboard.

## Tests

`tests/test_hubitat_integration.py` (`TestStateValueParsing`,
`TestDeviceStateSnapshot`, `TestStateCache`, `TestSingleDeviceState`,
`TestAllDeviceStates`, `TestDeviceEvents`, `TestStatePolling`,
`TestStateConfiguration`, `TestUrllibTransport`) and
`tests/test_device_state_view.py` cover single-device fetch, all-device fetch,
caching, event handling, polling/back-off, configuration and every failure
path — all with a mocked HTTP transport, so no live hub is required.
