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
User=node-red
Group=node-red
WorkingDirectory=/home/node-red
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

```bash
# Create .env file for Node-RED
cat > /home/node-red/.env << 'EOF'
# Dashboard Configuration
NODE_RED_USER=admin
NODE_RED_PASS=admin
NODE_RED_HOST=localhost
NODE_RED_PORT=1880
NODE_RED_SECURE=false

# Hubitat Settings (update with your credentials)
HUBITAT_URL=http://hubitat.local:80
HUBITAT_USERNAME=your_username
HUBITAT_PASSWORD=your_password
HUBITAT_API_KEY=your_api_key

# UniFi Settings (update with your credentials)
UNIFI_HOST=unifi.local
UNIFI_PORT=8443
UNIFI_USERNAME=your_username
UNIFI_PASSWORD=your_password
UNIFI_SITE=default
EOF

# Set secure permissions
chmod 600 /home/node-red/.env
chown -R node-red:node-red /home/node-red
```

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

Copy the dashboard flows into the container:

```bash
# Inside container (via pct enter)
scp /path/to/smart-home-dashboard/flows/* root@192.168.1.100:/home/node-red/.node-red/flows/
```

Or manually on the container:

```bash
# Create flows directory
mkdir -p /home/node-red/.node-red/flows

# Copy flow files
cp -r /path/to/smart-home-dashboard/flows/* /home/node-red/.node-red/flows/
```

### Configure Node-RED Options

```bash
# Create Node-RED configuration options
cat > /home/node-red/.node-red/settings.js << 'EOF'
// Node-RED configuration
module.exports = {
  userDir: "/home/node-red/.node-red",
  httpAdminRoot: "admin",
  httpNodeRoot: "api",
  httpStaticRoot: "public",
  httpStaticRootUserDir: "user-lib",
  httpStaticDepthLimit: 20,
  httpStaticMaxBodySize: 500000,
  httpRateLimit: {
    max: 100,
    windowMs: 60000
  },
  functionGlobalContext: {
    // Add global variables here
  },
  ui: {
    theme: "dashboard"
  },
  // Enable SSL (uncomment for production)
  // https: {
  //   key: "/etc/ssl/private/nodered.pem",
  //   cert: "/etc/ssl/certs/nodered.pem"
  // },
  // Enable authentication (uncomment for production)
  // users: [
  //   {
  //     username: "admin",
  //     password: "admin",
  //     roles: ["admin"]
  //   }
  // ],
  logging: {
    console: {
      level: "info"
    },
    file: {
      level: "warn",
      logsDir: "/home/node-red/.node-red/logs"
    }
  }
};
EOF
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

Edit `/home/node-red/.node-red/settings.js`:

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

# View container logs
qm console 101
```

### Monitor Node-RED

```bash
# Inside container
systemctl status node-red
journalctl -u node-red -f

# Check Node-RED is running
curl http://localhost:1880/api/

# View Node-RED logs
tail -f /home/node-red/.node-red/logs/*.log
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
cp -r /new/path/to/flows/* /home/node-red/.node-red/flows/
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

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| NODE_RED_USER | Default admin username | admin | No |
| NODE_RED_PASS | Default admin password | admin | No |
| NODE_RED_HOST | Hostname | localhost | No |
| NODE_RED_PORT | Node-RED port | 1880 | No |
| NODE_RED_SECURE | Enable HTTPS | false | No |
| HUBITAT_URL | Hubitat API URL | http://hubitat.local:80 | Yes |
| HUBITAT_USERNAME | Hubitat username | - | Yes |
| HUBITAT_PASSWORD | Hubitat password | - | Yes |
| HUBITAT_API_KEY | Hubitat API key | - | Yes |
| UNIFI_HOST | UniFi controller hostname | unifi.local | Yes |
| UNIFI_PORT | UniFi controller port | 8443 | Yes |
| UNIFI_USERNAME | UniFi username | - | Yes |
| UNIFI_PASSWORD | UniFi password | - | Yes |
| UNIFI_SITE | UniFi site name | default | Yes |

---

## 📚 Additional Resources

- [Proxmox LXC Documentation](https://pve.proxmox.com/wiki/Linux_Virtual_Container_(LXC))
- [Node-RED Documentation](https://nodered.org/docs/)
- [SmartHome Dashboard Main README](../README.md)

---

## 🆘 Getting Help

1. Check the troubleshooting section above
2. Review Proxmox documentation
3. Check Node-RED logs
4. Create an issue on the project repository

---

**Last Updated:** January 2024
