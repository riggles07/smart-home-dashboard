# Smart Home Dashboard - Implementation Details

## Project Architecture

This project implements a comprehensive smart home monitoring dashboard with the following components:

### Core Modules

1. **Dashboard UI** - Main visualization interface
2. **Hubitat Integration** - Smart home device controls
3. **UniFi Integration** - Network monitoring
4. **Home Lab Monitor** - Proxmox & Docker status
5. **Kanban Board** - Project task tracking

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
├── proxmox/
│   ├── lxc-config.json              # LXC template
│   ├── setup-lxc.sh                 # LXC setup script
│   ├── setup-node-red.sh            # Node-RED install
│   ├── container.conf               # Container config
│   └── post-install.sh              # Post-install setup
├── scripts/
│   └── deploy.sh                    # Deployment automation
├── .github/
│   └── workflows/
│       ├── ci.yml                   # CI/CD pipeline
│       └── deploy.yml               # Deployment workflow
├── .env.example                     # Environment template
├── requirements.txt                 # Node-RED packages
├── PROJECT_SUMMARY.md               # This file
└── README.md                        # Project overview
```

## Deployment Options

### Option 1: Local Installation
```bash
cd /root/smart-home-dashboard
node-red
```

### Option 2: Proxmox LXC Deployment
```bash
./proxmox/setup-lxc.sh --container-id 101 --ip 192.168.1.100
ssh root@192.168.1.100
./proxmox/setup-node-red.sh
./proxmox/post-install.sh
```

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
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://hubitat.local/api/v1/status

# Test UniFi API
curl -u username:password \
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

1. ~~Complete Hubitat integration (Phase 3)~~ ✅ Done — Devices tab is live against the Maker API
2. ~~Implement UniFi monitoring (Phase 4)~~ ✅ Done — Network tab renders 63 clients
3. ~~Build mobile-responsive UI (Phase 5)~~ ✅ Done — theme inlined into a hidden
   `ui_template`; verified in-browser. See `css/dashboard.css`,
   `docs/MOBILE_DEPLOYMENT.md`, `tests/test_theme_wiring.py`
4. Security hardening — **partially done, and partly NOT DONE on purpose.**
   HTTPS and firewall are NOT deployed (verified: nothing listens on 1881).
   Non-root Node-RED is deliberately NOT used: running as root with userDir
   `/root/.node-red` is what fixed the deployment. Tooling exists
   (`scripts/verify-security.sh`, `scripts/rotate-credentials.sh`); the
   non-root/SSL assertions inside `verify-security.sh` check FILES, not the
   running host, so they can pass while asserting an architecture this project
   does not have. Reconcile before trusting that script's exit code.
5. Integration validation + production deployment (Phase 6 remainder)
