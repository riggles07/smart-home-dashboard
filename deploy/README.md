# SmartHome Dashboard - LXC Deployment Guide

> Deploy the SmartHome Dashboard in a Proxmox LXC container with a single script.

This guide provides step-by-step instructions for deploying the SmartHome Dashboard (Node-RED based) in a Proxmox LXC container.

---

## 🚀 Quick Start (5 Minutes)

For a fast deployment, use this one-command solution:

```bash
# Run the automated deployment script
./deploy-lxc.sh --id 101 --ip 192.168.1.100
```

This will:
1. Create the LXC container (2GB RAM, 2 cores, 20GB disk)
2. Start the container
3. Install Node.js 20.x and Node-RED
4. Configure systemd service
5. Start Node-RED automatically

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

## 📦 Deployment Options

### Option 1: Automated Deployment (Recommended)

```bash
# From Proxmox host, copy deploy-lxc.sh to /root
# Make it executable
chmod +x deploy-lxc.sh

# Run with defaults (container ID 101, IP 192.168.1.100)
./deploy-lxc.sh

# Or specify custom values
./deploy-lxc.sh --id 102 --ip 192.168.1.105 --ram 4096 --cpus 2 --disk 50
```

### Option 2: Manual Step-by-Step

#### Step 1: Create the LXC Container

```bash
# Create container with template (2GB RAM, 2 cores, 20GB disk)
qm create 101 \
    --template debian-12-standard-1 \
    --cores 2 \
    --memory 2048 \
    --disk0 "local:20,vmvolume=rootfs,writable=true" \
    --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100,ipconfig0=none,type=veth" \
    --name "smarthome-dashboard"

# Start the container
qm start 101
```

#### Step 2: SSH into Container

```bash
# Connect to container shell
qm terminal 101
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
npm install -g node-red-dashboard
npm install -g node-red-node-hubitat
npm install -g node-red-node-unifi
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

#### Step 5: Configure Firewall (Phase 6 hardening - LAN-only access)

```bash
# Allow Node-RED ports from the local network only (default deny otherwise)
ufw allow from 192.168.1.0/24 to any port 1880 comment "Node-RED HTTP - LAN only"
ufw allow from 192.168.1.0/24 to any port 1881 comment "Node-RED HTTPS - LAN only"

# Enable UFW (default-deny incoming)
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
qm firewall set 101 rule add family=inet protocol=tcp destination=192.168.1.0/24 destination-port=1880

# Allow from specific IP
# qm firewall set 101 rule add family=inet protocol=tcp destination=192.168.1.100 destination-port=1880
```

---

## ⚙️ Custom Resource Allocation

Modify the `--memory`, `--cores`, and `--disk` parameters as needed:

| Resource | Minimum | Recommended | Maximum |
|----------|---------|-------------|---------|
| RAM      | 1024MB  | 2048MB      | 4096MB  |
| CPU      | 1 core  | 2 cores     | 4 cores |
| Disk     | 10GB    | 20GB        | 50GB    |

Example for larger container:

```bash
./deploy-lxc.sh --id 102 --ip 192.168.1.105 --ram 4096 --cpus 4 --disk 50
```

---

## 🔧 Post-Deployment Configuration

### Import Dashboard Flows

Copy the dashboard flows into the container:

```bash
# Inside container (via qm terminal)
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
./deploy-lxc.sh --id 101 --ip 192.168.1.100 --bridge vmbr1
```

### Using DHCP

```bash
# Create container without static IP
qm create 101 \
    --template debian-12-standard-1 \
    --cores 2 \
    --memory 2048 \
    --net0 "bridge=vmbr0,firewall=1,ip=dhcp,type=veth" \
    --name "smarthome-dashboard"
```

### Isolated Network

```bash
./deploy-lxc.sh --id 101 --ip 192.168.10.100 --bridge vmbr_isolated
```

---

## 🔒 Security Considerations

### 1. Firewall Rules

Only allow necessary ports from specific networks:

```bash
# Proxmox host
qm firewall set 101 rule add family=inet protocol=tcp destination=192.168.1.0/24 destination-port=1880
qm firewall set 101 rule add family=inet protocol=tcp destination=192.168.1.0/24 destination-port=8082
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
qm list

# Check container status
qm status 101

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
qm snapshot 101 "smarthome-backup-$(date +%Y%m%d)"

# Export to file
qm export 101 /root/smashome-dashboard-backup.tar.gz
```

### Restore from Snapshot

```bash
qm set 101 --snapshot smarthome-backup-20240115
```

---

## 🔧 Troubleshooting

### Container Won't Start

```bash
# Check logs
qm console 101

# Check status
qm status 101

# Try starting manually
qm start 101
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

# Check Proxmox firewall
qm firewall list 101
```

### Network Issues

```bash
# Check container IP
qm set 101 --ip-config

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
- [Container Config Template](../lxc/container.config)

---

## 🆘 Getting Help

1. Check the troubleshooting section above
2. Review Proxmox documentation
3. Check Node-RED logs
4. Create an issue on the project repository

---

**Last Updated:** January 2024
