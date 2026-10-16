# Smart Home Dashboard — Implementation Details

A single Node-RED instance serving a 7-tab dashboard for a homelab, deployed as
an LXC container on Proxmox.

## Project architecture

Everything the dashboard renders comes from **generated** flows.
`tools/gen_flows.py` is the source of truth: it emits one
`flows/<NN>-<name>.flow.json` per tab plus a combined `flows/all-flows.flow.json`.
Nothing under `flows/` should be hand-edited.

| Component | Where | Notes |
|-----------|-------|-------|
| Home Lab monitor | `flows/01-home-lab-monitor.flow.json` | Proxmox API → gauges, status table, CPU chart |
| Devices (Hubitat) | `flows/02-hubitat-devices.flow.json` | Maker API → power switch + brightness slider |
| Network (UniFi) | `flows/03-unifi-network.flow.json` | client poll → count + table |
| Kanban board | `flows/04-kanban-board.flow.json` | local task board |
| System Health | `flows/05-system-health.flow.json` | 6 Grafana `d-solo` iframes + Prometheus summary |
| Settings | `flows/06-settings.flow.json` | deployment info panel |
| Home Assistant | `flows/99-other.flow.json` | WebSocket state sync + REST light control |
| Theme | inside `01-…` | hidden `ui_tab` (order 99) carrying `css/dashboard.css` |

The `flows/*.js` files and their `*.py` mirrors are **custom node-type
definitions** (`RED.nodes.registerType(...)`) retained as reference
implementations — they contain no node graph and are not what runs. See
`flows/README.md`.

## Implementation status

### Phase 1 — Setup & architecture ✅
Node-RED installed in an LXC, project structure, env handling, base dashboard.

### Phase 2 — Home Lab monitoring ✅
Proxmox host CPU/memory gauges, kernel/CPU detail, swap, disk, uptime, CPU
history chart.

### Phase 3 — Hubitat integration ✅
Implemented, not pending. Power switch and brightness slider drive the Maker
API; URL construction and error surfacing are covered by
`tests/test_hubitat_device_control.py` and `tools/test_flow_functions.js`.

### Phase 4 — UniFi network monitoring ✅
Client list poll → online count and hostname/IP/MAC table. Both auth paths
implemented (API key, or cookie login with an auto-derived login endpoint).

### Phase 5 — Dashboard UI & display ✅
Mobile-responsive theme in `css/dashboard.css` via `--shd-*` custom properties,
44px touch targets, deployed for the Galaxy A7 Lite (`docs/MOBILE_DEPLOYMENT.md`).

### Phase 6 — Testing & deployment ✅ / ⚠️
- [x] CI: pytest + flow-structure + settings-syntax + theme-wiring gates
      (`.github/workflows/ci.yml`, green on push)
- [x] Flow-function harnesses that run the **real** `func` bodies
      (`tools/test_flow_functions.js`, `tools/test_ha_functions.js`)
- [x] Credential rotation (`scripts/rotate-credentials.sh`)
- [x] Security verification tooling (`scripts/verify-security.sh`)
      — **checks files, not the running host**; a pass does not prove the
      properties in `docs/SECURITY.md`
- [ ] HTTPS/TLS — **not deployed.** Plain HTTP on 1880. `config/settings.js` is
      not read by the runtime (Node-RED reads settings from its userDir), so
      setting `server.ssl` there has no effect even if a key existed.
- [ ] Firewall — **not verified.** No ufw rules are known to be applied on the
      container.
- [ ] Non-root Node-RED — **not deployed, deliberately.** Runs as root with
      userDir `/root/.node-red`; a non-root `node-red` account was the original
      cause of the deployment failure (`217/USER`).
- [ ] HA credentials in the runtime env — the Home Assistant nodes are correct
      but inert until `HA_URL`/`HA_TOKEN`/`HA_ENTITY_ID` are set and Node-RED is
      restarted.

### Phase 7 — Home Assistant migration ⚠️ partial
- [x] WebSocket client: auth handshake, `get_states`, `subscribe_events
      state_changed`, normalised entity events
- [x] REST control: dashboard switch → `light.turn_on` / `light.turn_off`
- [x] Env handling via LLAT in `.env`
- [ ] **Hubitat has not been replaced.** HA shipped as an additional tab; the
      Devices tab still speaks Maker API.
- [ ] Entity mapping is a single configured entity (`HA_ENTITY_ID`), not a
      migrated device set.

### Phase 8 — Grafana integration ✅
Six `d-solo` panels embedded with `kiosk` + `theme(dark)` + self-refresh, plus a
native Prometheus summary query feeding the header stats. Requires
`allow_embedding=true` and anonymous Viewer on the Grafana side
(`docs/GRAFANA_INTEGRATION.md`).

### Phase 9 — UI/UX modernization ⚠️ partial
- [x] CSS custom-property theming, contrast guard, 44px targets
- [ ] Dynamic backgrounds (time-of-day / weather / state)
- [ ] Multiple selectable palettes — one dark theme only
- [ ] Motion / haptic-style command feedback

### Phase 10 — WallPanel / Magic Mirror ❌ not started
Tracked as kanban cards (WallPanel PRO kiosk, MQTT remote control), not built.

## Repository layout

```
smart-home-dashboard/
├── config/            settings.js (+ .example) — the real Node-RED settings
├── css/               dashboard.css — themed, responsive
├── deploy/            THE supported deployment path
│   ├── setup.sh         provisions the working runtime
│   ├── .env.example     the ONLY env template (checked against the flows)
│   ├── node-red-start.sh, check-connectivity.sh, repair-settings.sh, …
│   └── README.md        authoritative deployment guide
├── docs/              HOME_ASSISTANT_INTEGRATION, GRAFANA_INTEGRATION,
│                      MOBILE_DEPLOYMENT, SECURITY, REQUIREMENTS_V2
├── flows/             generated *.flow.json + *.js/*.py node-type definitions
├── scripts/           verify-security.sh, rotate-credentials.sh, JS checkers
├── tests/             pytest suite (382 tests)
├── tools/             gen_flows.py (generator) + validators + JS harnesses
└── .github/workflows/ ci.yml (active); deploy.yml (inert, by design)
```

## Integrations — real endpoints

| Service | Call | Auth |
|---------|------|------|
| Proxmox | `GET <PROXMOX_URL>/api2/json/nodes/<PROXMOX_NODE>/status` | `Authorization: PVEAPIToken=<token>` |
| Hubitat | `GET <HUBITAT_URL>/apps/api/<APP_ID>/devices?access_token=<tok>` | query token (**no** Bearer, no `/api/v1/…`) |
| Hubitat command | `GET …/devices/<DEVICE_ID>/<cmd>/<value>?access_token=<tok>` | query token |
| UniFi (API key) | `GET <UNIFI_URL>/api/s/<site>/stat/sta` | `X-API-KEY: <key>` |
| UniFi (login) | self-hosted `<UNIFI_URL>/api/login`; UniFi OS `https://<host>/api/auth/login` | session cookie |
| Home Assistant | WS `<HA_URL>/api/websocket`; REST `POST <HA_URL>/api/services/<domain>/<service>` | `Authorization: Bearer <HA_TOKEN>` |
| Prometheus | `GET <PROMETHEUS_URL>/api/v1/query?query=…` | none (LAN) |
| Grafana embed | `<GRAFANA_URL>/d-solo/<uid>/<slug>?orgId=1&panelId=N&kiosk&theme=dark` | anonymous viewer |

`UNIFI_URL` embeds host **and** port (UniFi OS: `/proxy/network` on 443;
self-hosted: `:8443`). Get it wrong and the stat call 404s.

## Testing

```bash
python3 -m pytest -q                                       # 382 tests
node tools/test_flow_functions.js                          # 108 assertions
node tools/test_ha_functions.js                            # 41 assertions
python3 tools/validate_flows.py flows/all-flows.flow.json  # structure/wires
python3 tools/gen_flows.py && git diff --exit-code flows/  # generated-file drift
```

The two Node harnesses extract `func` bodies from the flow JSON and execute them
against stubbed globals, so they test what is actually deployed. That matters
here: both Home Assistant nodes once shipped as dead code — a literal `\n` turned
each body into a single `//` comment — while the whole Python suite stayed green.
`tests/test_flow_newline_guard.py` now guards that class of defect.

## Security

The honest statement is in [`docs/SECURITY.md`](docs/SECURITY.md). Summary:

- [x] Secrets in `/root/.node-red/.env`, `chmod 600`, never in the flows
- [x] `.env` git-ignored
- [ ] **HTTPS — not enabled.** Plain HTTP on 1880.
- [ ] **Firewall — not verified** on the container.
- [ ] **Non-root — not in use.** Node-RED runs as root, by design.
- [ ] **`adminAuth` — not enabled.** Anyone reaching 1880 can read/edit flows
      and therefore the credentials they use. This is also why the Admin API
      accepts unauthenticated flow deploys.
- [x] Credential rotation tooling available

> An earlier revision of this file claimed HTTPS, firewall and non-root were all
> in place. They were not. Treat any ✅ in a checklist without a matching test or
> command as unverified.

## Next steps

1. Set `HA_URL` / `HA_TOKEN` / `HA_ENTITY_ID` on the container and restart
   Node-RED — the only thing standing between the current code and a working HA
   integration (`docs/HOME_ASSISTANT_INTEGRATION.md`).
2. Decide whether Hubitat is actually being retired; until then the dashboard
   speaks two device protocols.
3. Phase 9 remainder (dynamic backgrounds, palettes, feedback) or explicitly drop
   it.
4. Phase 10 (WallPanel kiosk, MQTT control) if the Magic Mirror direction is
   still wanted.
