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

Regenerate them with `/tmp/gen_flows.py` (deterministic IDs, palette-validated).

## Import

### Option A — Admin API (no UI needed)

```bash
curl -s -X POST http://<host>:1880/flows \
  -H "Content-Type: application/json" \
  -H "Node-RED-Deployment-Type: full" \
  --data-binary @flows/all-flows.flow.json
# -> HTTP 204; the canvas populates immediately
```

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

## Credentials — never hardcoded

Function nodes read connection details from **environment variables**:

| Variable | Used by |
|----------|---------|
| `PROXMOX_URL`, `PROXMOX_NODE`, `PROXMOX_TOKEN` | Home Lab tab |
| `HUBITAT_URL`, `HUBITAT_APP_ID`, `HUBITAT_ACCESS_TOKEN`, `HUBITAT_DEVICE_ID` | Devices tab |
| `UNIFI_URL` | Network tab |

Set these in the LXC before starting Node-RED (see `deploy/.env.example`).

**Until they are set**, the inject nodes fire and log expected failures
(e.g. `ENOTFOUND proxmox.local`) — that is the flows running correctly against
an unconfigured backend, not a fault.

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
