# Home Assistant Integration (Phase 7)

Status: **module + tests landed and verified; the deployed-flow wiring is round 2.**

This note documents the Home Assistant (HA) integration for the Smart Home
Dashboard (`docs/REQUIREMENTS_V2.md` §1): the transport design, the auth
flow, the environment variables, and exactly what round 2 must do to wire
it into the deployed flows.

## What exists today

| Artifact | Role |
|---|---|
| `flows/home-assistant-integration.js` | Custom node-type definition module (`home-assistant-control`), the repo's `flows/*.js` pattern (see `flows/hubitat-integration.js`) |
| `flows/home_assistant_integration.py` | Python mirror (hyphen → underscore, per repo convention), importable as `from flows import home_assistant_integration` |
| `tests/test_home_assistant_integration.py` | WebSocket handshake, state sync, entity mapping, config/error paths |
| `tests/test_home_assistant_device_control.py` | Command mapping + every failure path (mirrors the Hubitat device-control suite) |

Both module files are unit-tested against a **protocol-faithful local mock**
(`FakeWebSocketServer` in the integration test) that enforces the real HA
frame sequence; **no live Home Assistant is required** (none was reachable
from the dev environment — `192.168.4.178:8123`, `192.168.4.86:8123`,
`homeassistant.local:8123`, `ha.local:8123` were all closed). Nothing in this
suite is marked skip.

## The transport split: WebSocket for state, REST for control

`REQUIREMENTS_V2.md` §1 says: *"Prefer WebSocket for real-time status; REST
for one-off commands."* The integration splits exactly that way:

- **State path (HA → dashboard), WebSocket**: one long-lived connection to
  `ws(s)://<host>/api/websocket` authenticates, then `get_states` snapshots
  every entity and `subscribe_events` (`state_changed`) pushes updates in
  real time. This is the HA → UI half of the bidirectional sync: a UI
  action fires a service call, HA emits `state_changed`, and the dashboard
  re-syncs the widget.
- **Control path (dashboard → HA), REST**: `POST /api/services/<domain>/<service>`
  with `Authorization: Bearer <LLAT>`. REST is preferred for one-off
  commands because every call is self-contained — no connection state, no
  frame-id bookkeeping, and an unreachable hub degrades to a structured
  `connection_error` result instead of a half-open socket.

## The LLAT auth flow (WebSocket)

Home Assistant's WebSocket API uses a three-message handshake
(developers.home-assistant.io/docs/api/websocket):

```
server -> {"type": "auth_required"}              # on connect
client -> {"type": "auth", "access_token": LLAT}  # Long-Lived Access Token
server -> {"type": "auth_ok"}                    # or {"type": "auth_invalid"}
```

Then the connection enters the command phase (`get_states`,
`subscribe_events`, `call_service`, ...), each client frame carrying a
monotonic `id` and each reply a `{"type": "result", "success": ...}` frame;
subscribed events arrive as `{"type": "event", "event": ...}` frames.

The node implements the handshake in `handleServerMessage()` /
`handle_server_message()`: `auth_required` → `auth`; `auth_ok` →
`get_states` + `subscribe_events(state_changed)`; `auth_invalid` → red
node status (never a crash). Tests assert this sequence frame-by-frame
against the mock server, which rejects a non-`auth` first frame exactly as
real HA closes the socket.

The LLAT itself is created in the HA UI under
**Profile → Security → Long-Lived Access Tokens**. The token is never
logged and never appears in any result payload (asserted by test).

## Environment variables — and why they are NOT in deploy/.env.example (yet)

The modules read three environment variables:

| Variable | Purpose | Example |
|---|---|---|
| `HA_URL` | HA base URL (scheme + host + port) | `http://192.168.4.178:8123` |
| `HA_TOKEN` | Long-Lived Access Token (LLAT) | `eyJhbGciOi...` |
| `HA_ENTITY_ID` | Entity the Devices-tab switch/slider targets | `light.kitchen` |

**They are deliberately absent from `deploy/.env.example` for now.**
`tests/test_env_template.py` is a drift gate: it derives the authoritative
variable list from every `env.get('NAME')` in the deployed flow function
nodes (`flows/all-flows.flow.json`) and fails if the template documents a
variable no flow reads. Because **round 2 wires the HA tab into
`tools/gen_flows.py`** (the current generator has no HA section and the
deployed flow JSON reads no `HA_*` variable), adding them to the template
today would fail the gate. This was verified empirically: adding
`HA_URL`/`HA_TOKEN` to `deploy/.env.example` makes
`test_template_does_not_document_unknown_variables` fail with
*"documents ['HA_TOKEN', 'HA_URL'], which no flow reads"*. The gate is
correct — the template and the code must not drift apart — so it stays
untouched and the variables are recorded here instead.

**Round 2 must add to `deploy/.env.example`** (at the same time as the
gen_flows wiring, so the gate passes in the same change):

```ini
# ============================================
# Home Assistant (read by the Home Assistant tab flow)
# ============================================
# HA base URL (scheme + host + port, no trailing slash)
HA_URL=http://192.168.4.178:8123

# Long-Lived Access Token: HA UI -> Profile -> Security -> Long-Lived
# Access Tokens -> Create Token. This token never expires unless revoked.
HA_TOKEN=your_long_lived_access_token

# Entity the Devices-tab power switch / brightness slider controls.
HA_ENTITY_ID=light.kitchen
```

### Where the variables live on the real deployment

The dashboard runs as a systemd service with `userDir /root/.node-red`, so
the env file **on the dashboard LXC** is:

```
/root/.node-red/.env          # the LXC's real runtime env file
```

That file is **not** part of this repo (and not present in this dev
container). The repo's template is `deploy/.env.example`; a deployment
copies it to `/root/.node-red/.env` on the LXC, fills in real values, and
restarts the service (see `deploy/` and the systemd unit's
`EnvironmentFile=-/root/.node-red/.env`). The template header documents
this path; the values above are what round 2's HA section must add.

## Why the WebSocket client must be a `function` node (design decision)

Node-RED's core `websocket-client` **config node passes its URL verbatim** —
it does **not** expand `${HA_URL}` (or any `${ENV_VAR}`) the way `http
request` nodes do. So an env-driven WS client cannot use the palette's
`websocket in`/`websocket out` pair with a templated URL.

The design that works (and what round 2 should generate in
`tools/gen_flows.py`):

- The WS client is a **`function` node** with
  `libs: [{var: "ws", module: "ws"}]`, which requires the `ws` npm package
  under Node-RED. `ws` is a transitive dependency of `@node-red/nodes`
  (via the websocket nodes), hoisted into Node-RED's `node_modules`, and
  `functionExternalModules` defaults to `true` in Node-RED 4.x/5.x — so
  `require('ws')` inside the function body works without adding a
  dependency to the dashboard's own `package.json`.
- The function body reads `env.get('HA_URL')`/`env.get('HA_TOKEN')` itself
  (this is what makes the drift gate pass once wired), derives
  `ws://…/api/websocket`, and runs the handshake + `get_states` +
  `subscribe_events(state_changed)` loop described above.
- Control commands follow the repo's existing REST pattern (the Proxmox
  and Hubitat tabs do exactly this): a **`function` node** reads
  `env.get('HA_URL')` / `env.get('HA_TOKEN')`, sets
  `msg.url = <base>/api/services/<domain>/<service>`,
  `msg.method = 'POST'` and
  `msg.headers = {Authorization: 'Bearer <LLAT>'}`, then an
  **`http request` node with `method: "use"`** executes the call. The
  `http request` palette node itself does not expand environment
  variables — the function node does the `env.get()` reads and hands the
  fully-formed request to it (the same reason the websocket-client node
  cannot be templated). The REST half therefore needs no custom code
  beyond the request-building function.

This split is why the module (node-type definition) is only half the story:
the deployed behavior lives in the generated flow JSON, which is round 2.

## What round 2 must do (the gen_flows wiring)

The modules are done and tested; the deployed flows do not use them yet.
Round 2 (a sibling change — the generator is owned elsewhere) must:

1. **Add an HA section to `tools/gen_flows.py`** emitting a new Home
   Assistant tab, with:
   - a `function` node implementing the WS client as above (state path);
   - `http request`-node service calls for `light.turn_on`,
     `light.turn_off`, `switch.turn_on`, `switch.turn_off` (control path),
     wired from the Devices-tab widgets' `ui_switch`/`ui_slider`;
   - the legacy Hubitat command mapping applied server-side so existing
     widgets keep working against HA entities.
2. **Regenerate** `flows/all-flows.flow.json` (and the per-tab JSONs) —
   this adds the `env.get('HA_URL')` / `env.get('HA_TOKEN')` /
   `env.get('HA_ENTITY_ID')` reads the drift gate needs.
3. **Add `HA_URL`, `HA_TOKEN`, `HA_ENTITY_ID` to `deploy/.env.example`**
   (exact block above) in the same change, so
   `tests/test_env_template.py` passes.
4. **Fill `/root/.node-red/.env` on the dashboard LXC** with the real
   values and restart the service.

Nothing in this round touches `tools/gen_flows.py` or the flow JSONs — a
concurrent sibling change owns them, and regenerating here would clobber
their in-flight edits.

## Hubitat compatibility (why the command map exists)

`REQUIREMENTS_V2.md` §1 requires existing device controls to keep working
against HA entities. `mapHubitatCommand()` / `map_hubitat_command()`
translate the legacy Hubitat Maker API commands onto HA service calls:

| Hubitat command | HA service call |
|---|---|
| `on` / `off` / `toggle` | `<domain>.turn_on` / `.turn_off` / `.toggle` |
| `setSwitch` | `.turn_on` or `.turn_off` from the `state` arg |
| `setLevel` | `.turn_on` + `brightness_pct` (0–100) |
| `setHue` / `setSaturation` | `.turn_on` + `hs_color` (hue 0–100 → 0–360, sat 0–100) |
| `setColor` | `.turn_on` + `hs_color` + optional `brightness_pct` |
| `setColorTemperature` | `.turn_on` + `kelvin` (1000–10000) |
| `setColorHex` | `.turn_on` + `rgb_color` (6-digit hex parsed) |
| `refresh` | `homeassistant.update_entity` |

Two mappings deserve a note because they were defects in the first draft,
now fixed and pinned by tests:

- **`refresh` → `homeassistant.update_entity`**, not
  `<entity-domain>.update_entity` — the per-domain form does not exist in
  HA and would 404. It is also valid for read-only domains (sensors), so
  the read-only rejection is applied after the re-route.
- **`setHue` converts the scale**: Hubitat hue is 0–100, HA `hs_color` hue
  is 0–360 (×3.6, e.g. 50 → 180).

The node also accepts the native HA shape
(`{entityId, domain, service, data}`) in `controlDevice()`, so new widgets
can use HA semantics directly while old ones keep the
`{deviceId, command, value}` shape.

## Verified behavior (what the tests pin)

- The auth handshake frame-for-frame (`auth_required` → `auth` with the
  LLAT → `auth_ok`; `auth_invalid` → red status, no crash).
- `get_states` snapshot + `subscribe_events(state_changed)` after
  `auth_ok`, with monotonic command ids.
- `call_service` frames carry the required `service` key (a frame without
  it is rejected by real HA — the first draft omitted it).
- Legacy command mapping incl. hue ×3.6 and the `refresh` re-route.
- Local `service_data` validation (`NUMERIC_RANGES` enforced, stray
  `entity_id` in service data rejected, unknown fields rejected).
- Every REST failure path: timeout, connection error, transport error,
  401/403 → `auth_error`, other non-2xx → `http_error`, 404 on
  `get_entity_state` → `unknown_entity`, missing token →
  `missing_configuration`.
- The LLAT never appears in any result payload or published message.