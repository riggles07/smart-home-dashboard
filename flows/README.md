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
