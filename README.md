# Smart Home Dashboard

A unified smart home dashboard built on Node-RED to monitor Hubitat smart home devices and UniFi network status.

## Overview

This dashboard provides a mobile-responsive interface for:
- **Hubitat Integration**: Monitor smart home devices and automations
- **UniFi Integration**: Track network status, connected clients, and security events

## Quick Start

### Prerequisites

- Node.js 18.x or 20.x LTS
- Access to Hubitat hub and UniFi controller
- Mobile device (e.g., Samsung Galaxy A7 Lite) for viewing

### Installation

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

### Access the Dashboard

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
- Test connection: `curl -H "Authorization: Bearer YOUR_KEY" https://hubitat.local/api/v1/status`

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
- `scripts/deploy.sh` - Deployment automation

## References

See the [Smart Home Dashboard Setup Skill](skill://homelab:smart-home-dashboard-setup) for detailed setup instructions.
