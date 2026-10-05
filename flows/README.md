# Smart Home Dashboard - Node-RED Flows

This directory contains the **real Node-RED flows** (node graphs) for the Smart
Home Dashboard — tabs, dashboard widgets, and processing nodes wired together.

## What's here

| File | Contents |
|------|----------|
| `01-home-lab-monitor.flow.json` | Proxmox host CPU/mem gauges, status, CPU history chart |
| `02-hubitat-devices.flow.json`   | Power switch + brightness slider → Hubitat Maker API |
| `03-unifi-network.flow.json`     | UniFi client poll → count + client table |
| `04-kanban-board.flow.json`      | Local task board (add card → table) |
| `05-settings.flow.json`          | Deployment info panel |
| `all-flows.flow.json`            | All 5 tabs combined (single-shot import) |

Every file is a JSON array of node **instances** (`tab`, `ui_*` widgets,
`inject`, `function`, `http request`, `json`, `debug`) — the format Node-RED's
Import dialog expects.

Regenerate them with `tools/gen_flows.py` (deterministic IDs, palette-validated).

## Which host runs what

Confusing these wastes a round trip. The scripts are **not** all meant for the LXC.

| Tool | Run on | Why |
|------|--------|-----|
| `deploy/repair-settings.sh` | **Node-RED LXC** | edits `/root/.node-red/settings.js` |
| `deploy/fix-node-red-service.sh` | **Node-RED LXC** | installs a systemd drop-in |
| `deploy/node-red-start.sh` | **Node-RED LXC** | launcher (only if not using systemd) |
| `deploy/check-connectivity.sh` | **Node-RED LXC** | reads the LXC's env file and probes from there |
| `deploy/.env.example` | reference | copy values into the LXC's `.env` |
| `tools/probe_runtime_env.py` | **anywhere** | talks to the Admin API over HTTP |
| `tools/gen_flows.py`, `validate_flows.py`, `test_flow_functions.js` | **dev machine** | build/verify flow JSON before deploy |

`probe_runtime_env.py` needs no local files — it deploys a temporary probe tab,
triggers it, reads the result back, and restores your flows. Point it at the host:

```bash
python3 tools/probe_runtime_env.py http://sh-dashboard:1880
```

There is nothing to download to the LXC for it. If you tried
`/tmp/shd/probe_runtime_env.py` there, that path never existed — the file is in
`tools/`, not `deploy/`.

## Credentials — never hardcoded

Function nodes read connection details from **environment variables**. In the
LXC these live in `/root/.node-red/.env` and must be present in the **process
environment** of the running Node-RED:

| Variable | Used by |
|----------|---------|
| `PROXMOX_URL`, `PROXMOX_NODE`, `PROXMOX_TOKEN` | Home Lab tab |
| `HUBITAT_URL`, `HUBITAT_APP_ID`, `HUBITAT_ACCESS_TOKEN`, `HUBITAT_DEVICE_ID` | Devices tab |
| `UNIFI_URL`, `UNIFI_SITE`, `UNIFI_API_KEY` *or* `UNIFI_USERNAME`+`UNIFI_PASSWORD`, `UNIFI_LOGIN_URL` | Network tab |

### UniFi: get the URL form right

This is the one setting that silently 404s. UniFi serves its Network API at a
different path depending on the product:

| Product | Port | `UNIFI_URL` |
|---------|------|-------------|
| UniFi OS console (UDM, Cloud Gateway, Dream Router) | 443 | `https://<host>/proxy/network` |
| Self-hosted Network controller | 8443 | `https://<host>:8443` |

Check which one you have — a UniFi OS console answers with
`<title>UniFi OS</title>` at the host root:

```bash
curl -sk https://<host>/ | grep -o '<title>[^<]*</title>'
```

If you use username/password on a UniFi OS console, also set the login path,
which differs from the legacy one:

```
UNIFI_LOGIN_URL=https://<host>/api/auth/login
```

An API key avoids the login entirely and is the better option if your UniFi
version supports it (Network 8+: *Settings → Control Plane → Integrations*).

**Diagnostic caveat:** UniFi OS returns **401 for every `/api/*` path**,
including bogus ones. So a 401 proves nothing about whether a path is correct —
only a **404** proves a prefix is wrong. Don't conclude the URL is right just
because it 401s.

### Setup

```bash
# on the Node-RED LXC
sudoedit /root/.node-red/.env          # fill in the values
systemctl restart node-red            # env is only read at start
```

#### First: prove the vars actually reach the process

If `systemctl show node-red -p Environment --value | tr ' ' '\n' | grep HUBITAT`
prints **nothing**, `.env` is being ignored — no matter what is in the file. The
unit shipped without `EnvironmentFile=`, so the file was written and chmod'd but
never read. Fix it:

```bash
bash deploy/fix-env-loading.sh    # idempotent; installs a drop-in
```

> In an LXC you are usually already root and `sudo` may not even be installed —
> run it without `sudo`.

Then verify against the **running process**, which is the only ground truth:

```bash
pid=$(systemctl show node-red -p MainPID --value)
sudo tr '\0' '\n' < /proc/$pid/environ | grep -E '^(HUBITAT|UNIFI|PROXMOX)_'
```

> `systemctl show -p Environment` is **not** reliable for values sourced from
> `EnvironmentFile=` — it can read empty on a working setup. Always confirm via
> `/proc/<pid>/environ`.

Then check the services are genuinely reachable with the same vars the flows use:

```bash
bash deploy/check-connectivity.sh
```

Every `!!` line is an item to fix. A `DNS: ... does NOT resolve` line means the
hostname needs adding to the LXC's DNS or replacing with an IP in `.env`.

**Until credentials are set**, inject nodes still fire and log expected failures
(e.g. `ENOTFOUND proxmox.local`). That is the flows running correctly against an
unconfigured backend, not a fault.

## Testing

```bash
node tools/test_flow_functions.js     # 34 assertions against real func bodies
python3 tools/validate_flows.py flows/all-flows.flow.json   # structure/wire integrity
```

`test_flow_functions.js` extracts the `func` source straight out of the flow
JSON and runs it against stubbed `env`/`node`/`flow` globals, so it tests the
deployed logic rather than a copy. It covers the UniFi API-key path, the legacy
login path, the missing-credentials path, cookie capture, Proxmox metric maths,
Hubitat URL construction, error formatting, and the Kanban store.

`validate_flows.py` catches dangling wires, orphaned `z`/`group`/`tab` refs, and
empty function bodies — run it before importing.

## Import

### Option A — Admin API (no UI needed)

```bash
curl -s -X POST http://<host>:1880/flows \
  -H "Content-Type: application/json" \
  -H "Node-RED-Deployment-Type: full" \
  --data-binary @flows/all-flows.flow.json
# -> HTTP 204; the canvas populates immediately
```

`deploy/setup.sh` runs this automatically (Step 11) and verifies it.

### Option B — Web UI

1. Open `http://<host>:1880`
2. **Import** → *select a file to import* → pick `all-flows.flow.json`
3. **Deploy**

## Required node modules

The flows use only nodes already in the palette. Install with:

```bash
npm install -g node-red node-red-dashboard
```

| Node type used | Provided by |
|----------------|-------------|
| `ui_tab`, `ui_group`, `ui_gauge`, `ui_text`, `ui_chart`, `ui_switch`, `ui_slider`, `ui_button`, `ui_text_input`, `ui_template` | `node-red-dashboard` (legacy) |
| `inject`, `function`, `http request`, `json`, `debug` | core (`node-red`) |

## Legacy vs Dashboard 2.0

This project targets the **legacy `node-red-dashboard`** (`ui_*` snake_case
types, URL path `/ui`). Dashboard 2.0 (`@flowfuse/node-red-dashboard`,
`ui-page` / `ui-gauge` hyphenated types, URL path `/dashboard`) is also
installed in the LXC but these flows do not use it.

## Note on the old `flows/*.js` files

The `*.js` files here (and their `*.py` mirrors) are **custom node-type
definitions** (`module.exports = function (RED) { RED.nodes.registerType(...) }`)
— the plugin half of a node package, not flows. They never contained a node
graph, which is why importing them produced empty canvases. They are retained
as reference implementations for the Python side; the flows above supersede
them for the dashboard.
