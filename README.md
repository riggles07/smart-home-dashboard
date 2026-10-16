# Smart Home Dashboard

A unified Node-RED dashboard for a homelab: **Home Assistant** device monitoring
and control, **UniFi** network status, **Proxmox** host metrics, a local task
board, and **Grafana/Prometheus** observability — all behind one `/ui` URL.

Seven dashboard tabs:

| # | Tab | What it shows |
|---|-----|---------------|
| 1 | **Home Lab** | Proxmox host CPU/memory gauges, status table, CPU history chart |
| 2 | **Devices** | Power switch + brightness slider → Hubitat Maker API |
| 3 | **Network** | UniFi client poll → online count + client table |
| 4 | **Kanban** | Local task board (add card → table) |
| 5 | **System Health** | Six embedded Grafana panels + native Prometheus summary stats |
| 6 | **Settings** | Deployment info panel |
| 7 | **Home Assistant** | WebSocket state sync + light control (REST service calls) |

A hidden `Theme` tab carries the mobile CSS; it is not meant to be navigated to.

> **Home Assistant is on the Home Assistant tab (7).** The Devices tab still
> speaks Hubitat — the migration is additive so far, not a replacement.

## Deployment

### Proxmox LXC container — the supported path

`deploy/setup.sh` is the only supported deployment. The old `proxmox/` tree was
**deleted** because it provisioned a runtime that cannot start (`User=node-red`
with no such account → `217/USER`; `MemoryDenyWriteExecute=true` → V8 JIT killed
with `SIGSYS`).

Full, step-by-step instructions — container creation, Node-RED install, the
systemd unit, `.env` handling, and verification — live in
**[`deploy/README.md`](deploy/README.md)**. That is the authoritative deployment
document; this file deliberately does not duplicate it.

Short version, **run inside the container** (not on the Proxmox host):

```bash
bash deploy/setup.sh
```

### Docker (alternative)

```bash
docker run -d -p 1880:1880 --name smarthome nodered/node-red
```

### Native install

For local development or a single-instance deployment only.

## Configuration

### Environment variables

Credentials are **never** hardcoded in the flows — function nodes read them with
`env.get()`. They live in `/root/.node-red/.env` on the container and must be in
the **process environment** of the running Node-RED (read at start, so a restart
is required after any change).

`deploy/.env.example` is the single source of truth and is guarded by
`tests/test_env_template.py`, which fails if a flow reads a variable the template
does not document. The groups:

```bash
# Home Assistant  (Home Assistant tab)
HA_URL=http://homeassistant.local:8123   # as reachable FROM the container
HA_TOKEN=<long-lived access token>
HA_ENTITY_ID=light.kitchen               # the entity the switch controls

# Hubitat  (Devices tab) — Maker API, not Basic auth
HUBITAT_URL=http://192.168.4.86
HUBITAT_API_KEY=...
HUBITAT_APP_ID=...
HUBITAT_ACCESS_TOKEN=...
HUBITAT_DEVICE_ID=...

# UniFi  (Network tab) — an API key avoids the login step entirely
UNIFI_URL=https://<host>/proxy/network   # see the UniFi section below
UNIFI_API_KEY=
UNIFI_USERNAME=
UNIFI_PASSWORD=
UNIFI_SITE=default

# Grafana / Prometheus  (System Health tab)
PROMETHEUS_URL=http://<monitoring-host>:9090
GRAFANA_URL=http://<monitoring-host>:3001
GRAFANA_DASH_UID=shd-system-health

# Proxmox  (Home Lab tab)
PROXMOX_URL=https://proxmox.local:8006
PROXMOX_NODE=pve
PROXMOX_TOKEN=...
```

Then lock it down and restart:

```bash
chmod 600 /root/.node-red/.env
systemctl restart node-red      # env is only read at startup
```

**Two settings bite silently and are worth reading before you start:**

- **`HA_URL` is not always port 8123.** Reverse proxies (Tailscale Serve
  included) commonly front Home Assistant on 80/443. Verify with
  `curl -i "$HA_URL/api/"` — it must return **401 Unauthorized**. A
  connection-refused means the wrong port; the WebSocket URL is derived from the
  same host and port, so a wrong port kills the handshake, not the HTTP call.
  See [`docs/HOME_ASSISTANT_INTEGRATION.md`](docs/HOME_ASSISTANT_INTEGRATION.md).
- **`UNIFI_URL` differs by product** — `https://<host>/proxy/network` for a
  UniFi OS console (UDM / Cloud Gateway), `https://<host>:8443` for a
  self-hosted controller. Get it wrong and the stat call 404s.

### Installing the flows

Flows are **generated** by `tools/gen_flows.py`, not hand-edited. To deploy the
current set to a running Node-RED over HTTP (no UI, no restart):

```bash
curl -s -X POST http://<host>:1880/flows \
  -H "Content-Type: application/json" \
  -H "Node-RED-Deployment-Type: full" \
  --data-binary @flows/all-flows.flow.json      # -> HTTP 204
```

> Do **not** add a `Node-RED-API-Version` header — v2 expects a different payload
> shape and fails with `Cannot read properties of undefined (reading 'forEach')`.

Or use the editor: **Import → select a file → `all-flows.flow.json` → Deploy**.
An import that is not followed by **Deploy** never reaches the runtime.

See [`flows/README.md`](flows/README.md) for the per-tab files and which host
each helper script belongs on.

### Node modules

```bash
npm install -g node-red node-red-dashboard
npm install -g node-red-contrib-hubitat node-red-contrib-unifi
```

The Home Assistant tab additionally uses the **`ws`** npm module via the function
node's `libs` config. It resolves out of the box under Node-RED's own dependency
tree; no separate install has been needed. The flows otherwise use only core
nodes plus `node-red-dashboard` (the **legacy** `ui_*` widgets — not Dashboard
2.0's hyphenated `ui-*` types).

## Features

### Home Lab
- Proxmox host CPU / memory gauges, kernel and CPU detail, swap, disk, uptime
- CPU history chart fed from the Proxmox API

### Devices (Hubitat)
- Power switch and brightness slider for a single configured device
- Maker API URL construction with structured error surfacing

### Network (UniFi)
- Client list poll → online count, hostname/IP/MAC table
- API-key **or** cookie-login auth paths, auto-derived login endpoint

### Kanban
- Local task board: add a card via a text input, rendered as a table

### System Health (Grafana + Prometheus)
- Six `d-solo` Grafana panels embedded as iframes (CPU, memory, I/O, health,
  latency, packet loss)
- Native Prometheus summary query for targets-up, CPU, memory and probe counts
- Requires Grafana to run with `allow_embedding=true` and anonymous Viewer
  access — see [`docs/GRAFANA_INTEGRATION.md`](docs/GRAFANA_INTEGRATION.md)

### Home Assistant
- **WebSocket state sync** — one authenticated connection, `get_states` plus
  `subscribe_events state_changed`, re-emitted as
  `ha/entity/<entity_id>/state`
- **REST control** — the dashboard switch becomes
  `POST /api/services/light/turn_on|turn_off` for `HA_ENTITY_ID`

## Security

Measured against the running container; see [`docs/SECURITY.md`](docs/SECURITY.md)
for the full statement.

- Never commit `.env`. Secrets live in `/root/.node-red/.env` on the container.
- **No TLS.** The dashboard serves plain HTTP on 1880.
- **No `adminAuth`** (measured 2026-10-16). Anyone who can reach port 1880 can
  read and edit the flows — and therefore read every credential they use. The
  Admin API is equally open, which is *why* flow deploys work over plain HTTP.
  If that matters on your network, enable `adminAuth` with a real bcrypt hash
  first, then add TLS via the `https` key in the userDir settings.
- **Node-RED runs as root**, userDir `/root/.node-red` — deliberate for a
  single-purpose LAN container, not a hardening claim.
- **Firewall: not verified.** ufw rules are referenced by some scripts but have
  not been confirmed applied on the container.
- Credential rotation: `./scripts/rotate-credentials.sh`
- Static checks: `./scripts/verify-security.sh` — checks **files**, not the
  running host, so a pass does not prove the properties above.

## Testing

```bash
python3 -m pytest -q                      # 382 tests (Python)
node tools/test_flow_functions.js         # 108 assertions, real func bodies
node tools/test_ha_functions.js           # 41 assertions, HA state + control paths
python3 tools/validate_flows.py flows/all-flows.flow.json
python3 tools/gen_flows.py && git diff --exit-code flows/   # drift check
```

The two Node harnesses extract `func` source **straight out of the flow JSON**
and run it against stubbed `env`/`node`/`context`/`ws` globals, so they exercise
the deployed logic rather than a copy. That is deliberate: structural checks once
passed while both Home Assistant nodes were entirely dead code.

CI runs all of the above on every push — see `.github/workflows/ci.yml`. The
separate `deploy.yml` is deliberately inert (documented in the file itself).

## Troubleshooting

### Node-RED won't start
- Node 18+ required; it runs on Node 24 in practice. Check
  `/root/.node-red/start.log` and `journalctl -u node-red`.
- An over-escaped function body cannot stop startup, but a `libs` module that
  fails to resolve can — check the editor for a red error badge.

### A tab renders but shows nothing
1. `python3 tools/validate_flows.py flows/all-flows.flow.json` — dangling wires
   and empty function bodies are caught here.
2. Confirm the tab's env vars reached the process:
   `tr '\0' '\n' < /proc/$(systemctl show node-red -p MainPID --value)/environ | grep -E '^(HA|HUBITAT|UNIFI|PROXMOX|GRAFANA|PROMETHEUS)_'`
3. `bash deploy/check-connectivity.sh` — every `!!` line is an item to fix.

### Home Assistant tab is inert
- No status on the node = the env vars are missing. Expected status texts are
  `no HA_TOKEN`, `no HA_ENTITY_ID`, `no HA_URL`, `read-only`.
- `WS error` / `auth failed` = reachable but rejected: check the token and port.
- Confirm the *host* reachability first with `curl -i "$HA_URL/api/"` (want 401).

### Devices tab shows no devices
- The Maker API token is not a Bearer token. The flow calls
  `GET <HUBITAT_URL>/apps/api/<app>/devices?access_token=<token>`; verify with
  that exact URL rather than an `Authorization:` header.

### UniFi connection issues
- UniFi OS returns **401 for every `/api/*` path**, including bogus ones — only a
  **404** proves a prefix is wrong.
- Self-signed certificates: the flows set `rejectUnauthorized=false`.
- Verify the controller is reachable on 443 (UniFi OS) or 8443 (self-hosted).

### Grafana panels are blank
- The server must have `allow_embedding=true` and anonymous Viewer access.
- Check the dashboard UID in `GRAFANA_DASH_UID` matches the real one.

## Maintenance

```bash
npm update -g node-red node-red-dashboard node-red-contrib-hubitat node-red-contrib-unifi
cp -r /root/.node-red/flows /root/.node-red/flows.backup
```

## Repository layout

| Path | What it is |
|------|------------|
| `tools/gen_flows.py` | **Generator** — the source of truth for every flow |
| `tools/validate_flows.py`, `tools/test_*.js` | Structure and function-body verification |
| `flows/*.flow.json` | Generated flows, one per tab, plus `all-flows.flow.json` |
| `flows/*.js`, `flows/*.py` | Custom node-type definitions and their Python mirrors — **not** flows; see `flows/README.md` |
| `deploy/` | The supported deployment path (`setup.sh`, env template, helpers) |
| `config/settings.js` | Node-RED settings |
| `css/`, `tests/`, `scripts/` | Theme CSS, test suite, ops scripts |
| `docs/` | Integration and operational documentation |

## Documentation

| Document | Covers |
|----------|--------|
| [`deploy/README.md`](deploy/README.md) | **Authoritative deployment guide** |
| [`flows/README.md`](flows/README.md) | Flow inventory, env vars, which host runs what |
| [`docs/HOME_ASSISTANT_INTEGRATION.md`](docs/HOME_ASSISTANT_INTEGRATION.md) | HA auth, ports, WebSocket + REST, troubleshooting |
| [`docs/GRAFANA_INTEGRATION.md`](docs/GRAFANA_INTEGRATION.md) | Grafana embeds, required server settings |
| [`docs/MOBILE_DEPLOYMENT.md`](docs/MOBILE_DEPLOYMENT.md) | Galaxy A7 Lite kiosk setup |
| [`docs/SECURITY.md`](docs/SECURITY.md) | Measured security posture |
| [`docs/REQUIREMENTS_V2.md`](docs/REQUIREMENTS_V2.md) | Requirements for the HA migration, Grafana, and theming work |

## References

See the [Smart Home Dashboard Setup Skill](skill://homelab:smart-home-dashboard-setup)
for additional setup guidance.
