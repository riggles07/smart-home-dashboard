# Smart Home Dashboard

A unified smart home dashboard built on Node-RED to monitor Hubitat smart home devices and UniFi network status.

## 📦 Deployment Options

### LXC Container (Proxmox) - **Recommended**

Deploy in a Proxmox LXC container for isolation and easy management.

**Note:** Scripts run from **within the container**, not the Proxmox host.

**Quick Start:**
```bash
# Step 1: Create container via Proxmox Web UI
# Navigate to: Datacenter → Nodes → your-node → Containers → Create LXC
# Select: Debian 12 (bookworm), 2GB RAM, 2 cores, IP: 192.168.1.100

# Step 2: SSH into container
qm terminal 101

# Step 3: Run setup script (must be inside container)
cd /root
wget https://raw.githubusercontent.com/your-repo/smarthome-dashboard/main/proxmox/setup-smarthome.sh
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

This dashboard provides a mobile-responsive interface for:
- **Hubitat Integration**: Monitor smart home devices and automations
- **UniFi Integration**: Track network status, connected clients, and security events

## Quick Start

### LXC Deployment (Proxmox)

```bash
# Create container via Proxmox Web UI (easiest)
# Or use Proxmox CLI:
qm create 101 --template debian-12-standard --cores 2 --memory 2048 \
    --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100,type=veth" \
    --name "smarthome-dashboard"
qm start 101

# SSH into container
qm terminal 101

# Install Node-RED
apt-get update && apt-get install -y nodejs npm wget curl
npm install -g node-red
node-red
```

Access at: http://192.168.1.100:1880

### Docker Deployment

```bash
docker run -d -p 1880:1880 --name smarthome nodered/node-red
```

Access at: http://localhost:1880

### Native Installation

**Prerequisites**

- Node.js 18.x or 20.x LTS
- Access to Hubitat hub and UniFi controller
- Mobile device (e.g., Samsung Galaxy A7 Lite) for viewing

**Installation**

```bash
# Install Node.js
curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo bash -
sudo apt-get install -y nodejs npm

# Install Node-RED
npm install -g node-red

# Install integration packages
npm install -g node-red-node-hubitat node-red-node-unifi

# Start Node-RED
node-red
```

**Access the Dashboard**

1. Open browser: http://localhost:1880
2. Import flow: Menu > Import > Paste/Import > Import JSON
3. Configure credentials (see Configuration below)
4. Access from mobile: http://<server-ip>:1880

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

- Never commit `.env` files to repositories
- Use HTTPS for production deployments
- Restrict Node-RED access to local network
- Regular credential rotation

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
