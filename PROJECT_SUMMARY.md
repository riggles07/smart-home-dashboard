# Smart Home Dashboard - Implementation Details

## Project Architecture

This project implements a comprehensive smart home monitoring dashboard with the following components:

### Core Modules

- **Home Assistant Integration**: Track smart home devices and automations
- **UniFi Integration**: Track network status, connected clients, and security events
- **Grafana Integration**: Visualize home lab metrics
- **Home Lab Monitor**: Proxmox & Docker status
- **Kanban Board**: Project task tracking

## Implementation Status

### Phase 1: Project Setup & Architecture ✅
- [x] Node-RED installation
- [x] Project structure created
- [x] Environment configuration
- [x] Basic dashboard layout

### Phase 2: Home Lab Monitoring ✅
- [x] Proxmox cluster health
- [x] Docker container monitoring
- [x] VM/Container status
- [x] Node resource monitoring

### Phase 3: Hubitat Integration (Pending)
- [ ] Smart device controls
- [ ] Automation triggers
- [ ] Device state monitoring

### Phase 4: UniFi Network Monitoring ✅
- [x] WiFi client list
- [x] Network traffic monitoring
- [x] Access point status

### Phase 5: Dashboard UI & Display ✅
- [x] Mobile responsive design (`css/dashboard.css`, auto layout)
- [x] Local deployment on Galaxy A7 Lite (`docs/MOBILE_DEPLOYMENT.md`)
- [x] Touch-friendly controls (44px targets, `touch-action: manipulation`)

### Phase 6: Testing & Deployment (In Progress)
- [x] CI: pytest suite + flow-structure + settings-syntax + theme-wiring gates
      (`.github/workflows/ci.yml`, green on every push)
- [x] Security verification tooling (`scripts/verify-security.sh`)
      — see the caveat below: it checks files, not the running host
- [x] Credential rotation tooling (`scripts/rotate-credentials.sh`)
- [ ] HTTPS/TLS — NOT deployed. The service serves plain HTTP on 1880; nothing
      listens on 1881. `config/settings.js` is not read by the runtime (Node-RED
      only reads settings from its userDir), so setting `server.ssl` there would
      have no effect even if the key existed.
- [ ] Firewall (ufw) — NOT verified on the container; no ufw rules are known to
      be applied there.
- [ ] Non-root Node-RED — NOT deployed, and deliberately so: the service runs as
      root with userDir `/root/.node-red`. A non-root `node-red` account was the
      original cause of the deployment failure (`217/USER`, `/home/node-red`
      missing). See `deploy/README.md`.
- [ ] Integration validation
- [ ] Production deployment

## File Structure

```
smart-home-dashboard/
├── config/
│   └── settings.js              # Node-RED configuration
├── css/
│   └── dashboard.css             # Mobile-responsive theme (Phase 5)
├── docs/
│   └── MOBILE_DEPLOYMENT.md      # Galaxy A7 Lite deployment guide (Phase 5)
├── flows/
│   ├── dashboard-configuration.js    # Main dashboard UI
│   ├── home-lab-monitor.js          # Home Lab monitoring
│   ├── hubitat-integration.js       # Hubitat controls
│   ├── unifi-network-monitor.js     # UniFi monitoring
│   ├── kanban-flow.js               # Task tracking
│   └── integration-functions.js     # API functions
├── deploy/                       # THE supported deployment path
│   ├── setup.sh                  #   provisions the working runtime
│   ├── .env.example              #   env template (checked vs the flows)
│   ├── node-red-start.sh
│   ├── check-connectivity.sh
│   └── ...
├── scripts/
│   ├── verify-security.sh        # Static checks (files, not the running host)
│   └── rotate-credentials.sh
├── .github/
│   └── workflows/
│       ├── ci.yml                # pytest suite + flow structure + settings + theme
│       └── deploy.yml            # inert (CI cannot reach the LAN host)
├── deploy/.env.example           # Environment template (the ONLY one)
├── requirements.txt              # Python test dependencies
├── PROJECT_SUMMARY.md            # This file
└── README.md                     # Project overview
```

## Deployment Options

### Option 1: `deploy/setup.sh` (supported)

Run this inside the LXC container. It installs Node.js and Node-RED, writes the
systemd unit, and provisions the runtime known to work:

```bash
bash deploy/setup.sh
```

### Option 2: Proxmox LXC

Create the container on the Proxmox host with `pct` (`qm` is for VMs), then run
`deploy/setup.sh` inside it. See `deploy/README.md`.

## API Endpoints

### Hubitat API
- Base URL: `http://hubitat.local:8080`
- Authentication: API Key header
- Status: `/api/v1/status`
- Devices: `/api/v1/devices`

### UniFi Network API
- Base URL: `https://unifi.local:8443`
- Authentication: Basic auth
- Clients: `/rest/smartapi/apis/smart/v2/ubnt/network/clients`
- APs: `/rest/proprietory/rest/cap/wlan`

## Testing

```bash
# Test Hubitat API
curl -H \"Authorization: Bearer ***\" \\\
  https://hubitat.local/api/v1/status

# Test UniFi API
curl -u username:password \\\
  https://unifi.local:8443/api/login

# Test Node-RED
curl http://localhost:1880/api/
```

## Security Checklist

- [x] Environment variables in `.env` file
- [x] `.env` in `.gitignore`
- [x] HTTPS enabled in production (`config/settings.js` + self-signed cert at `/etc/node-red/`)
- [x] Firewall rules configured (ufw, LAN-only allow on 1880/1881, default deny)
- [x] Non-root user for Node-RED (`node-red` user + systemd sandboxing)
- [x] Regular credential rotation (`scripts/rotate-credentials.sh`)

## Next Steps

### Phase 7: Home Assistant Migration (In Progress)
- [ ] Replace Hubitat integration with HA WebSocket API
- [ ] Map entities and update dashboard controls
- [ ] Verify bidirectional state sync

### Phase 8: Grafana Dashboard Integration (Pending)
- [ ] Enable Grafana embedding
- [ ] Create and embed Proxmox/LXC health panels
- [ ] Optimize UI for mobile (A7 Lite)

### Phase 9: UI/UX Modernization (Pending)
- [ ] Implement themable CSS system using Custom Properties
- [ ] Build dynamic background engine (time/state based)
- [ ] Redesign visual hierarchy for readability and workflow
- [ ] Verify performance on Galaxy A7 Lite

### Phase 10: Magic Mirror Display (Pending)
- [ ] Sideload and configure WallPanel PRO on A7 Lite
- [ ] Implement MQTT wake/brightness control in Node-RED
- [ ] Wire HA motion sensors to tablet wake triggers
- [ ] Implement time-of-day view switching via `eval` commands
- [ ] Verify <1s motion-to-wake latency
