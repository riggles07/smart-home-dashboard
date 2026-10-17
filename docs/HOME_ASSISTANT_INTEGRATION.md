# Home Assistant Integration

The **Home Assistant** tab (tab 7) syncs entity state over the HA WebSocket API
and controls one configurable entity over the REST API.

## Credentials

The dashboard needs a **Long-Lived Access Token (LLAT)**. Create it in the HA UI:

1. Open Home Assistant: **`<HA_URL>/`** (see the port warning below)
2. Click your **username** at the bottom of the left sidebar → **Profile**
3. Scroll to **Long-lived access tokens** → **Create token**
4. Name it something recognisable, e.g. `smart-home-dashboard node-red`
5. **Copy it immediately** — HA shows it once, then only the last 4 characters

Verify it before wiring it in. Load the real values from the env file first —
`$HA_TOKEN` is a shell variable, so the command is paste-safe, unlike a
redaction placeholder:

```bash
set -a; . /root/.node-red/.env; set +a          # pulls in HA_URL + HA_TOKEN
curl -i -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/"
# want: 200 OK  {"message":"API running."}
```

> **Never paste a placeholder like `Bearer ***` into a shell.** It is sent
> literally and HA answers `401 Unauthorized`, whose body is the *plain text*
> `401: Unauthorized` — so piping it into `json.load` fails with the misleading
> `JSONDecodeError: Extra data: line 1 column 4 (char 3)` rather than saying
> "unauthorized". A `401` on `/api/` with a **correct** token means the token is
> wrong; a `401` from a pasted placeholder means nothing at all.

## ⚠️ `HA_URL` is not always port 8123

This is the failure that costs an hour. HA's native port is 8123, but a reverse
proxy — **Tailscale Serve included** — commonly fronts it on **80** or **443**.
Measured on this deployment: the tailnet address answers on **port 80** while
`:8123` returns `ECONNREFUSED`.

Because the flow derives the WebSocket URL from `HA_URL` by swapping
`http`→`ws`, a wrong port breaks the **handshake**, not the HTTP call — you get a
silently dead node.

Diagnose the three cases, which look similar but mean different things:

| symptom | meaning |
|---------|---------|
| `ECONNREFUSED` | host reachable, nothing listening on that port — wrong port, or the service is down |
| timeout | no route: peer offline, tailnet/ACL drop, firewall |
| `401` | **correct port, HA healthy**, token simply missing |

```bash
curl -i "$HA_URL/api/"          # 401 Unauthorized  == good port, HA up
curl -i "$HA_URL/manifest.json" # 200 application/manifest+json
```

## Configuration

Add to `/root/.node-red/.env` on the container (see `deploy/.env.example`):

```bash
HA_URL=http://homeassistant.local:8123   # as reachable FROM the container
HA_TOKEN=<the long-lived access token>
HA_ENTITY_ID=light.kitchen               # the entity the dashboard switch drives
```

`HA_URL` needs **no trailing slash** — the flow appends `/api/websocket` itself.
Environment variables are read at process start, so **restart Node-RED** after
changing them.

Pick a real entity id from the API — **the placeholders in this repo
(`light.kitchen`) are examples, not defaults; they will not exist on your
instance.** Measured 2026-10-17: `HA_ENTITY_ID=light.kitchen` against a real
install authenticated fine (289 entities) but no such entity existed, so the
dashboard switch had nothing to drive:

```bash
set -a; . /root/.node-red/.env; set +a
curl -s -H "Authorization: Bearer $HA_TOKEN" "$HA_URL/api/states" | \
  python3 -c "import sys,json; [print(s['entity_id'],'|',s['attributes'].get('friendly_name')) \
              for s in json.load(sys.stdin) if s['entity_id'].startswith(('light.','switch.'))]"
```

Check the chosen id is in that list, and that you can actually control it —
read-only domains (`sensor`, `binary_sensor`, `weather`, …) are refused by the
flow with a `read-only` status.

## Architecture

All of this is **generated** by `tools/gen_flows.py` into the Home Assistant tab
of `flows/99-other.flow.json` (and `all-flows.flow.json`). Editing
`flows/home-assistant-integration.js` does **not** change the dashboard — those
`.js`/`.py` files are custom node-type definitions kept as reference
implementations.

| Node | Type | Role |
|------|------|------|
| `HA WebSocket Client` | function | connects, authenticates, emits state; **out0 = control → REST, out1 = state → debug** |
| `HA REST Controller` | function | formats the service call, adds the bearer token |
| `HA REST API` | http request | performs the `POST` |
| `HA Response` | debug | REST replies |
| `Sync States` | inject | every 60 s: reconnects if the socket dropped. **Never actuates.** |
| `Light Control` | ui_switch | the dashboard switch → `turn_on` / `turn_off` |

### Authentication flow

HA sends `auth_required` **before** any credential is supplied, which is why the
path can be tested without a token:

```
connect  ws(s)://<HA_URL>/api/websocket
recv     {"type":"auth_required","ha_version":"2026.10.1"}
send     {"type":"auth","access_token":"<HA_TOKEN>"}
recv     {"type":"auth_ok"}
send     {"type":"get_states"}                                  -> out1 counts entities
send     {"type":"subscribe_events","event_type":"state_changed"} -> out1 per change
```

Verify the whole path with no credentials at all — a successful open plus
`auth_required` proves tailnet → proxy → HA → WebSocket upgrade:

```javascript
// temporary probe function node, libs: [{"var":"ws","module":"ws"}]
var s = new ws('ws://<host>/api/websocket', { handshakeTimeout: 6000 });
s.on('message', function (d) { node.warn(String(d)); s.close(); });
```

### Message contract

| topic | output | payload |
|-------|--------|---------|
| `ha/state_count` | 1 | number of entities loaded |
| `ha/entity/<entity_id>/state` | 1 | `{entityId, domain, state, friendlyName, isOn, brightnessPct}` |
| `ha/control` | 0 | `{url, method, body}` for the REST controller |

### Control path

The `ui_switch` sends a bare boolean. The client maps it to
`POST <HA_URL>/api/services/light/turn_on|turn_off` with
`{"entity_id": HA_ENTITY_ID}`. Read-only domains (`sensor`, `binary_sensor`,
`input_datetime`, `weather`, `zone`, `device_tracker`) are refused with a
`read-only` status.

> **Caveat:** `ui_switch` may emit its initial value when the dashboard page
> loads, which actuates once. Harmless for an already-off light; revisit if the
> controlled entity matters.

## Node-RED function-node constraints (measured, node-red 5.0.7)

Both nodes use the **classic** function-node style: the body runs once per
message, its **return value** is what gets emitted, async sends use
`node.send()`, and persistent state lives in `context`. These were measured on
the live runtime — do not "simplify" them away:

| expression | result |
|------------|--------|
| `typeof on` | `"undefined"` → `on('input', …)` throws `ReferenceError: on is not defined` |
| `node.on('input', …)` | throws `Cannot add listener to 'input' event within Function` |
| `send` / `done` | `"undefined"` — the async-callback signature is not provided |
| vars declared in the `initialize` tab | **not** in scope in the body |
| `context` | **does** persist across messages — the socket handle lives there |
| `require('ws')` | `undefined` unless the node declares `libs`; with `libs` the module arrives as an injected parameter, so **do not also** write `const ws = require('ws')` (redeclaration error) |

## Deployment

```bash
# from the dev machine
curl -s -X POST http://<container-ip>:1880/flows \
  -H "Content-Type: application/json" \
  -H "Node-RED-Deployment-Type: full" \
  --data-binary @flows/all-flows.flow.json     # -> HTTP 204
```

`deploy/setup.sh` performs this automatically. There is **no restart needed for
flows** — only for environment variables. An editor **Import** that is not
followed by **Deploy** never reaches the runtime.

## Verifying

```bash
python3 -m pytest tests/test_ha_integration.py -q     # 22 tests
node tools/test_ha_functions.js                       # 41 assertions
```

`tools/nodered_env_probe3.py` deploys a temporary probe node, reads the runtime's
own view of `HA_URL` / `HA_TOKEN` / `HA_ENTITY_ID` back through the Admin API, and
restores your flows. It reports presence and length only, never values.

On the canvas the node status tells you exactly where it stands:

| status | meaning |
|--------|---------|
| *(empty)* | the body never ran — check the wiring |
| `no HA_TOKEN` / `no HA_URL` / `no HA_ENTITY_ID` | env vars missing → restart needed |
| `connecting` → `connected` → `N entities` | working |
| `auth failed` | token rejected |
| `WS error` / `closed` | host reachable but the socket dropped — check the port |

## Troubleshooting

- **Tab is inert, no status anywhere.** The env vars are missing; restart
  Node-RED after setting them.
- **`no HA_TOKEN` persists after setting it.** The var is not in the *process*
  environment. Confirm against the running process, not the file:
  `tr '\0' '\n' < /proc/$(systemctl show node-red -p MainPID --value)/environ | grep ^HA_`
- **`auth failed`.** Re-create the token; check for a trailing newline when
  pasting into `.env`.
- **`read-only`.** `HA_ENTITY_ID` points at a read-only domain; the switch only
  drives controllable ones.
- **Nothing happens when toggling.** Check `HA_ENTITY_ID` is set and that the
  entity exists and is controllable.

## Security

- `HA_TOKEN` is a **full-access** credential for your HA instance. Keep it only
  in `/root/.node-red/.env` (`chmod 600`), never in the flows or the repo.
- The dashboard's Admin API is **unauthenticated**, and anyone who can reach
  port 1880 can read the flows and therefore the environment they use — see
  [`SECURITY.md`](SECURITY.md).
- Revoke a leaked token from the same HA Profile page that created it.

## References

- [HA WebSocket API](https://developers.home-assistant.io/docs/api/websocket/)
- [HA REST API](https://developers.home-assistant.io/docs/api/rest/)
- [Long-lived access tokens](https://www.home-assistant.io/docs/authentication/)
