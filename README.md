# Smart Home Dashboard

A unified smart home dashboard built on Node-RED to monitor Hubitat smart home devices and UniFi network status.

## 📦 Deployment Options

### Proxmox LXC Container - **Recommended**

Deploy in a Proxmox LXC container for full Linux access with Node-RED isolation.

**Note:** All commands run **inside the container**, not on the Proxmox host.

## Overview

- **Hubitat Integration**: Monitor smart home devices and automations

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

