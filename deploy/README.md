# SmartHome Dashboard - LXC Deployment Guide

> Deploy the SmartHome Dashboard in a Proxmox LXC container with a single script.

This guide provides step-by-step instructions for deploying the SmartHome Dashboard (Node-RED based) in a Proxmox LXC container.

---

## 🚀 Quick Start

The LXC container must exist first. Creating it is a one-off Proxmox-host step;
this repo no longer ships overlapping container-creation scripts (they used the
wrong CLI — `qm`, which is for VMs). Create the container on the Proxmox host:

```bash
# On the Proxmox host. `pct` is the CONTAINER tool; `qm` is only for VMs.
pct create 101 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
    --cores 2 --memory 2048 --rootfs local-lvm:20 \
    --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100/24,gw=192.168.1.1" \
    --features nesting=1 --unprivileged 0 --start 1
```

Then deploy the dashboard into it with `deploy/setup.sh` (see below), which is
the supported path.

Access the dashboard at: `http://192.168.1.100:1880`

---

## 📋 Prerequisites

### On Proxmox Host
- Proxmox VE 7.0+ or 8.0+
- Root or sudo access to Proxmox
- VM bridge network `vmbr0` configured
- At least 4GB RAM and 2 cores available on Proxmox host

### On LXC Container
- Debian 12 (Bookworm) template (recommended)
- Network connectivity via bridge
- SSH access enabled

---

## 📦 Deployment

### The supported path: `deploy/setup.sh`

Run this inside the container. It installs Node.js and Node-RED, writes the
systemd unit, and provisions the runtime that is known to work:

```bash
# inside the container
bash deploy/setup.sh
```

It deliberately runs Node-RED **as root** with userDir `/root/.node-red` and
`MemoryDenyWriteExecute=false`. All three are required: a non-root `node-red`
account that does not exist produces `217/USER`, `/home/node-red` is never
created, and `MemoryDenyWriteExecute=true` kills V8's JIT (`SIGSYS`).

### Manual Step-by-Step

The manual path below is the same sequence `deploy/setup.sh` performs, kept for
reference and troubleshooting.

#### Step 1: Create the LXC Container

```bash
# On the Proxmox HOST. `pct` is the container tool (`qm` is for VMs).
# pct create <vmid> <ostemplate> [OPTIONS]
pct create 101 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
    --hostname smarthome-dashboard \
    --cores 2 \
    --memory 2048 \
    --rootfs local-lvm:20 \
    --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100/24,gw=192.168.1.1" \
    --features nesting=1 \
    --unprivileged 1

# Start the container
pct start 101
```

#### Step 2: SSH into Container

```bash
# Connect to container shell
pct enter 101
```

#### Step 3: Install Dependencies

Inside the container:

```bash
# Update system
apt-get update -y && apt-get upgrade -y

# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Install Node-RED globally
npm install -g node-red

# Install Node-RED modules (if needed)
npm install -g @flowfuse/node-red-dashboard
npm install -g node-red-contrib-hubitat
npm install -g node-red-contrib-unifi
npm install -g node-red-contrib-kanbanflow
```

#### Step 4: Configure systemd Service

```bash
# Create systemd service file
cat > /etc/systemd/system/node-red.service << 'EOF'
[Unit]
Description=Node-RED Dashboard Service
After=network.target

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/root/.node-red
ExecStart=/usr/bin/node-red
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start service
systemctl daemon-reload
systemctl enable node-red
systemctl start node-red
```

#### Step 5: Configure Firewall (OPTIONAL - not currently applied)

> This step is **not** part of the working deployment and has not been verified
> on the container. Port 1880 is reachable on the LAN and over the tailnet.
> There is no TLS listener, so the 1881 rule below is forward-looking only.

```bash
# OPTIONAL. Allow Node-RED from the local network only (default deny otherwise)
ufw allow from 192.168.1.0/24 to any port 1880 comment "Node-RED HTTP - LAN only"
# Only meaningful if you have added TLS via the 'https' key in
# /root/.node-red/settings.js -- nothing listens on 1881 by default.
# ufw allow from 192.168.1.0/24 to any port 1881 comment "Node-RED HTTPS - LAN only"

ufw --force enable
```

#### Step 6: Create Environment File

`deploy/.env.example` is the single source of truth for this file — it is
checked against the flows by `tests/test_env_template.py`, which fails if a flow
reads a name the template does not document. **Copy it and fill it in** rather
than writing one from memory:

```bash
cp deploy/.env.example /root/.node-red/.env
chmod 600 /root/.node-red/.env
chown root:root /root/.node-red/.env
```

The variables the flows actually read (grouped by tab):

```bash
# Home Assistant  (Home Assistant tab; inert until HA_TOKEN is set)
HA_URL=http://homeassistant.local:8123   # as reachable FROM this container
HA_TOKEN=<long-lived access token>       # HA → Profile → Long-lived access tokens
HA_ENTITY_ID=light.kitchen

# Hubitat  (Devices tab) — Maker API. There is no username/password path:
# HUBITAT_USERNAME / HUBITAT_PASSWORD are read by NO flow and were removed.
HUBITAT_URL=http://hubitat.local
HUBITAT_API_KEY=<maker api token>
HUBITAT_APP_ID=<app id from the Maker API URL>
HUBITAT_ACCESS_TOKEN=<same page>
HUBITAT_DEVICE_ID=<device the switch controls>

# UniFi  (Network tab). One variable, not host+port.
#   UniFi OS console  -> https://<host>/proxy/network
#   self-hosted       -> https://<host>:8443
UNIFI_URL=https://hubitat.local/proxy/network
UNIFI_API_KEY=                 # preferred; skips the login step entirely
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
PROXMOX_TOKEN=<user>@pam!<tokenid>=<secret>
```

> A variable that no flow reads is not harmless — it is a false sense of
> configuration. Only the names above reach `env.get()`.

---

#### Step 7: Configure Proxmox Firewall (Optional)

```bash
# Allow access from your network range
# Proxmox-level firewall rules are declared in /etc/pve/firewall/101.fw, or
# enabled per-interface with: pct set 101 --net0 "bridge=vmbr0,firewall=1,..."
pve-firewall status

# Allow from specific IP
# (Proxmox-level firewall rules are managed via pve-firewall / the web UI,
#  or per-container with: pct set 101 --net0 "bridge=vmbr0,firewall=1,...")
```

---

## ⚙️ Custom Resource Allocation

Modify the `--memory`, `--cores`, and `--rootfs` options as needed:

| Resource | Minimum | Recommended | Maximum |
|----------|---------|-------------|---------|
| RAM      | 1024MB  | 2048MB      | 4096MB  |
| CPU      | 1 core  | 2 cores     | 4 cores |
| Disk     | 10GB    | 20GB        | 50GB    |

Example for a larger container:

```bash
pct create 102 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
    --hostname smarthome-dashboard --cores 4 --memory 4096 \
    --rootfs local-lvm:50 \
    --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.105/24,gw=192.168.1.1"
```

---

## 🔧 Post-Deployment Configuration

### Import Dashboard Flows

Deploy the current flow set over the **Admin API** — no UI, no restart:

```bash
# from the dev machine, against the container
curl -s -X POST http://<container-ip>:1880/flows \
  -H "Content-Type: application/json" \
  -H "Node-RED-Deployment-Type: full" \
  --data-binary @flows/all-flows.flow.json     # -> HTTP 204
```

> **Do not send a `Node-RED-API-Version` header.** v2 expects an object payload,
> not a bare array, and fails with
> `Cannot read properties of undefined (reading 'forEach')`.

`deploy/setup.sh` does this for you and verifies the result. The editor route is
**Import → select a file → Deploy**; note that an import which is not followed by
**Deploy** never reaches the runtime, which is easy to mistake for a broken flow.

Copying the generated JSON into `/root/.node-red/flows/` also works — but the
flows are **generated** by `tools/gen_flows.py`, so prefer regenerating and
deploying over hand-editing anything under `flows/`.

### Node-RED settings

**Do not write a `settings.js` from scratch.** The repo ships the real one at
[`config/settings.js`](../config/settings.js) (with a
[`config/settings.js.example`](../config/settings.js.example) template).
`deploy/setup.sh` installs it. Overwriting it on the container is how the
admin/node roots drifted in the past — the live server reports
`httpAdminRoot: "/"` and `httpNodeRoot: "/"`, and a settings file claiming
`"admin"` / `"api"` moves both and breaks every documented URL.

If you do need to change it, edit the tracked file, then:

```bash
node --check config/settings.js          # must parse
node -e "require('./config/settings.js'); console.log('loads OK')"
cp config/settings.js /root/.node-red/settings.js
systemctl restart node-red
```

---

## 🌐 Network Configuration

### Using Different Bridge

If your Proxmox uses a different bridge (e.g., `vmbr1`):

```bash
pct create 101 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
    --hostname smarthome-dashboard --cores 2 --memory 2048 --rootfs local-lvm:20 \
    --net0 "bridge=vmbr1,firewall=1,ip=192.168.1.100/24,gw=192.168.1.1"
```

### Using DHCP

```bash
pct create 101 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
    --hostname smarthome-dashboard \
    --cores 2 \
    --memory 2048 \
    --rootfs local-lvm:20 \
    --net0 "bridge=vmbr0,firewall=1,ip=dhcp"
```

### Isolated Network

```bash
pct create 101 local:vztmpl/debian-12-standard_12.7-1_amd64.tar.zst \
    --hostname smarthome-dashboard \
    --cores 2 --memory 2048 --rootfs local-lvm:20 \
    --net0 "bridge=vmbr_isolated,firewall=1,ip=192.168.10.100/24"
```

---

## 🔒 Security Considerations

### 1. Firewall Rules

Only allow necessary ports from specific networks:

```bash
# Proxmox host
# Proxmox-level firewall rules are declared in /etc/pve/firewall/101.fw, or
# enabled per-interface with: pct set 101 --net0 "bridge=vmbr0,firewall=1,..."
pve-firewall status
pve-firewall status
```

### 2. Disable SSH (Optional)

```bash
# Disable SSH service in container
systemctl disable ssh
systemctl stop ssh
```

### 3. Enable Node-RED Authentication

Edit `/root/.node-red/settings.js`:

```javascript
users: [
  {
    username: "admin",
    password: "your_secure_password",
    roles: ["admin"]
  }
]
```

### 4. Use HTTPS in Production

Configure SSL certificates and enable in `settings.js`:

```javascript
https: {
  key: "/etc/ssl/private/nodered.key",
  cert: "/etc/ssl/certs/nodered.crt"
}
```

---

## 📊 Monitoring and Management

### Check Container Status

```bash
# List containers
pct list

# Check container status
pct status 101

# Get a shell inside it (`pct` is the CONTAINER tool; `qm` is for VMs only)
pct enter 101
```

### Monitor Node-RED

```bash
# Inside container
systemctl status node-red
journalctl -u node-red -f

# Check Node-RED is running (the Admin API root is "/", not "/api/")
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:1880/flows   # want 200

# Node-RED logs -- the launcher writes its own log here:
tail -f /root/.node-red/start.log
# ...and under systemd:
journalctl -u node-red -f
```

### Backup Container

```bash
# Create snapshot
# Create a snapshot (pct snapshot <vmid> <snapname>)
pct snapshot 101 "smarthome-backup-$(date +%Y%m%d)"

# Back up the container to a file
vzdump 101 --storage local --mode snapshot
```

### Restore from Snapshot

```bash
# List snapshots, then roll back to one
pct listsnapshot 101
pct rollback 101 smarthome-backup-20240115
```

---

## 🔧 Troubleshooting

### Container Won't Start

```bash
# Check logs
qm console 101

# Check status
pct status 101

# Try starting manually
pct start 101
```

### Node-RED Not Running

```bash
# Check service status
systemctl status node-red

# Check logs
journalctl -u node-red -n 50

# Try starting manually
node-red
```

### Port Not Accessible

```bash
# Check port is listening
netstat -tlnp | grep 1880

# Check firewall
ufw status

# Check Proxmox-level firewall status
pve-firewall status
```

### Network Issues

```bash
# Check the container's network config
pct config 101 | grep net0

# Test connectivity inside container
ping -c 4 192.168.1.1

# Check network interface inside container
ip addr show eth0
```

---

## 🔄 Updating the Dashboard

### Update Flows

```bash
# Inside container
cp -r /new/path/to/flows/* /root/.node-red/flows/
systemctl restart node-red
```

### Update Node-RED

```bash
# Update Node.js and Node-RED
apt-get update -y
apt-get install -y nodejs
npm update -g node-red
systemctl restart node-red
```

---

## 📝 Environment Variables Reference

**`deploy/.env.example` is the authoritative reference** — it is the copy you
install to `/root/.node-red/.env`, and `tests/test_env_template.py` fails if a
flow reads a variable it does not document. Do not maintain a second list here.

The variables that actually reach `env.get()`, by tab:

| Variable | Tab | Notes |
|----------|-----|-------|
| `PROXMOX_URL`, `PROXMOX_NODE`, `PROXMOX_TOKEN` | Home Lab | `PROXMOX_NODE` defaults to `pve` |
| `HUBITAT_URL`, `HUBITAT_API_KEY`, `HUBITAT_APP_ID`, `HUBITAT_ACCESS_TOKEN`, `HUBITAT_DEVICE_ID` | Devices | Maker API. **No username/password path exists.** |
| `UNIFI_URL`, `UNIFI_SITE`, `UNIFI_API_KEY`, `UNIFI_USERNAME`, `UNIFI_PASSWORD`, `UNIFI_LOGIN_URL` | Network | `UNIFI_URL` embeds host *and* port; see the UniFi section above |
| `PROMETHEUS_URL`, `GRAFANA_URL`, `GRAFANA_DASH_UID` | System Health | all three have working defaults |
| `HA_URL`, `HA_TOKEN`, `HA_ENTITY_ID` | Home Assistant | tab is inert until `HA_TOKEN` is set |

Three categories of "looks configured but isn't", worth keeping distinct:

| Names | Status |
|-------|--------|
| `HUBITAT_USERNAME`, `HUBITAT_PASSWORD`, `UNIFI_HOST`, `UNIFI_PORT` | read by **no flow** — the Maker API has no username/password path and `UNIFI_URL` carries host *and* port. Do not add these back; `deploy/setup.sh` used to emit them. |
| `NODE_RED_PORT`, `NODE_RED_USERDIR` | **not** flow variables, but genuinely read by `config/settings.js` (`uiPort`, `userDir`). Keep them. |
| `NODE_RED_USER`, `NODE_RED_PASS`, `NODE_RED_HOST`, `NODE_RED_SECURE` | read by nothing — `NODE_RED_USER`/`PASS` appear only inside a commented-out `adminAuth` example. |

> A variable nothing reads is worse than an absent one: it looks configured.
> Check with `grep -rn "env.get(" tools/gen_flows.py` before trusting any name.

---

## 📚 Additional Resources

- [Proxmox LXC Documentation](https://pve.proxmox.com/wiki/Linux_Virtual_Container_(LXC))
- [Node-RED Documentation](https://nodered.org/docs/)
- [SmartHome Dashboard Main README](../README.md)

---

## 🆘 Getting Help

1. Run `python3 tools/validate_flows.py flows/all-flows.flow.json` — catches
   dangling wires and empty function bodies before you blame the environment.
2. Confirm the env vars reached the **process**, not just the file (see above).
3. `bash deploy/check-connectivity.sh`, then work every `!!` line.
4. Check `journalctl -u node-red` / `/root/.node-red/start.log`.

---

**Last reviewed:** 2026-10-16 — verified against the running container
(node-red 5.0.7, Node 24, userDir `/root/.node-red`, `httpAdminRoot: "/"`).
