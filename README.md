# Smart Home Dashboard

A unified smart home dashboard built on Node-RED to monitor Hubitat smart home devices and UniFi network status.

## 📦 Deployment Options

### Proxmox LXC Container - **Recommended**

Deploy in a Proxmox LXC container for full Linux access with Node-RED isolation.

**Note:** All commands run **inside the container**, not on the Proxmox host.

**Quick Start:**
```bash
# Step 1: Create container via Proxmox Web UI
# Navigate to: Datacenter → Nodes → your-node → Containers → Create LXC
# Select: Debian 12 (bookworm), 2GB RAM, 2 cores, IP: 192.168.1.100/24

# Step 2: SSH into container
ct terminal 101

# Step 3: Run setup script (must be inside container)
cd /root
wget https://raw.githubusercontent.com/riggles07/smart-home-dashboard/main/proxmox/setup-smarthome.sh
chmod +x setup-smarthome.sh
./setup-smarthome.sh 101
```

### Docker (Alternative)

Run Node-RED in Docker if container access is limited:

```bash
docker run -d -p 1880:1880 --name smarthome nodered/node-red
```

### Native Installation

Install directly on your host system (for local development or single-instance deployments).

## Overview

- **Hubitat Integration**: Monitor smart home devices and automations
- **UniFi Integration**: Track network status, connected clients, and security events

## Quick Start

### Proxmox LXC Container Setup

1. **Create container via Proxmox Web UI:**
   - Navigate: Datacenter → Nodes → your-node → Containers → Create LXC
   - Template: Debian 12 (bookworm)
   - Resources: 2GB RAM, 2 cores
   - Network: `net0: bridge=vmbr0,firewall=1,ip=<your-ip>,type=veth`
   - Name: `smarthome-dashboard`

2. **Start container:**
   ```bash
   # From Proxmox host
   ct start 101
   ```

3. **SSH into container:**
   ```bash
   # From Proxmox host
   ct terminal 101
   ```

4. **Install Node-RED (inside container):**
   ```bash
   apt-get update && apt-get install -y nodejs npm wget curl
   npm install -g node-red
   node-red
   ```

Access at: http://<container-ip>:1880

## Configuration

### Environment Variables

Create a `.env` file (do NOT commit to git):

```bash
# Hubitat
HUBITAT_API_KEY="your-api-key"
HUBITAT_HOST="hubitat.local"
HUBITAT_PORT="8080"

# UniFi
UNIFI_HOST="unifi-controller.local"
UNIFI_PORT="8443"
UNIFI_USERNAME="your-username"
UNIFI_PASSWORD="your-password"
UNIFI_SITE="default"
```

Set secure permissions:
```bash
chmod 600 .env
```

### Flow Import

1. Navigate to Node-RED Palette Manager
2. Install required nodes:
   - `node-red-node-hubitat`
   - `node-red-node-unifi`
3. Import flow configuration from `flows/*.js`
4. Configure each node with your credentials

## Features

### Hubitat Monitoring
- Real-time device status
- Automation triggers
- Scene management

### UniFi Monitoring
- Network topology visualization
- Connected client list
- AP and switch status
- Security event alerts

## Security

**Actual posture** (measured against the running container on 2026-10-03; see
`docs/SECURITY.md` for the full statement):

- Never commit `.env` files to repositories. Secrets live in
  `/root/.node-red/.env` (the systemd unit's `EnvironmentFile`), not in the flows.
- **No TLS.** The dashboard serves plain HTTP on 1880. Nothing listens on 1881.
- **Firewall: not verified.** ufw rules are referenced by some scripts but have
  not been confirmed applied on the container.
- **Node-RED runs as root**, userDir `/root/.node-red`. This is deliberate for a
  single-purpose LAN container, not a hardening claim — a non-root `node-red`
  account was the original cause of the deployment failure (`217/USER`).
- Credential rotation tooling: `./scripts/rotate-credentials.sh`
- Static checks: `./scripts/verify-security.sh` (checks FILES, not the running
  host — a pass does not prove the properties above)
- ⚠️ Anyone who can reach port 1880 can read and edit the flows and therefore
  read the credentials they use. If that matters, enable `adminAuth` with a real
  bcrypt hash first, then add TLS via the `https` key in the userDir settings.
- CI: `.github/workflows/ci.yml` runs pytest + flow structure + settings syntax
  + theme wiring on every push.

## Troubleshooting

### Node-RED won't start
- Ensure Node.js version 18.x or 20.x (LTS)
- Check logs: `tail -f ~/.npm-debug.log`

### Dashboard not loading on mobile
- Use server IP, not localhost
- Verify firewall: `ufw status`
- Check port 1880 is open

### Hubitat API errors
- Verify API key is valid
- Test connection: `curl -H "Authorization: Bearer ***" https://hubitat.local/api/v1/status`

### UniFi connection issues
- SSL certificate verification may fail for self-signed certs
- For testing, disable certificate verification temporarily
- Verify UniFi controller is reachable on port 8443

## Maintenance

### Update Packages

```bash
npm update -g node-red node-red-node-hubitat node-red-node-unifi
```

### Backup Flows

```bash
cp -r ~/.node-red/flows ~/.node-red/flows.backup
```

## Support Files

- `flows/*.js` - Dashboard flows
- `config/settings.js` - Node-RED configuration
- `proxmox/` - Proxmox LXC deployment scripts
- `proxmox/README-LXC-CONTAINER.md` - Complete LXC guide

## References

See the [Smart Home Dashboard Setup Skill](skill://homelab:smart-home-dashboard-setup) for detailed setup instructions.
