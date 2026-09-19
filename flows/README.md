# Smart Home Dashboard - Node-RED Flows

This directory contains the Node-RED flow configurations for the Smart Home Dashboard.

## Flow Files

- `dashboard-configuration.js` - Main dashboard UI structure
- `home-lab-monitor.js` - Proxmox & Docker monitoring
- `hubitat-integration.js` - Smart home device controls
- `unifi-network-monitor.js` - Network monitoring
- `kanban-flow.js` - Project task tracking
- `integration-functions.js` - API integration logic

## Installation

1. Install required packages:
   ```bash
   npm install -g node-red-dashboard node-red-node-hubitat node-red-node-unifi
   ```

2. Import flows:
   ```bash
   node-red -u flows/*.js
   ```

3. Configure credentials in `.env` file

## Features

- **Dashboard UI**: Mobile-responsive layout with 4 tabs
- **Home Lab Monitor**: Proxmox cluster, Docker containers, VM status
- **Hubitat**: Smart device controls and automation
- **Unifi**: Network monitoring and client tracking
- **Kanban**: Project task tracking

## Hubitat Device Controls

Device commands are sent through the hub's Maker API
(`GET /apps/api/<app_id>/devices/<device_id>/<command>[/<value>]?access_token=...`).
Credentials (`url`, `appId`, `accessToken`/`apiKey`) come from node config or
`HUBITAT_URL` / `HUBITAT_APP_ID` / `HUBITAT_ACCESS_TOKEN` env vars — never hard-coded.

Supported commands, by device capability:

- **Switch**: `on`, `off`, `toggle`, `setSwitch(state)` — switches, smart plugs, dimmers
- **Dimmer**: `setLevel(level, duration?)` — 0-100 % level, optional ramp seconds
- **Colour bulb**: `setHue(hue)`, `setSaturation(saturation)`,
  `setColor(hue, saturation, level?)` (HSB), `setColorHex(hex)`,
  `setColorTemperature(kelvin, level?)`
- **All devices**: `refresh` — ask a device to re-report its state

Every command returns a structured result
(`{ok, code, deviceId, command, value, statusCode, message, error}`), mapping
failures to `missing_configuration`, `invalid_device_id`, `unknown_command`,
`invalid_argument`, `invalid_payload`, `timeout`, `connection_error`,
`http_error`, or `unknown_device` — and publishes it on the node's output
(`hubitat/device/<id>/command`).

Verification (no live hub needed): `python3 -m pytest tests/` (unit tests mock
the HTTP layer) and `node scripts/check_hubitat_js.js` (JS harness).
