# SmartHome Dashboard - Proxmox LXC Deployment Guide

This guide shows how to deploy the SmartHome Dashboard (Node-RED based) in a Proxmox LXC container.

## Quick Start (5 Minutes)

### Prerequisites
- Proxmox VE 7.0+ or 8.0+
- Root or sudo access
- VM bridge network `vmbr0` configured

### 1. Create the LXC Container

```bash
# Create container (ID 101, 2GB RAM, 2 cores)
qm create 101 --template debian-12-standard --cores 2 --memory 2048 \
    --net0 "bridge=vmbr0,firewall=1,ip=dhcp,type=veth" \
    --name "smarthome-dashboard"

# Set static IP
qm set 101 --ip 192.168.1.100 --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100,ipconfig0=none,type=veth"

# Start container
qm start 101
```

### 2. Install Dependencies

```bash
# SSH into container
qm terminal 101

# Inside container:
apt-get update
apt-get install -y nodejs npm wget curl git openssh-server

# Install Node-RED
npm install -g node-red
```

### 3. Configure and Start

```bash
# Copy flow files (if available)
cp /path/to/dashboard.zip /home/node-red/

# Start Node-RED
node-red

# Access at: http://192.168.1.100:1880
```

## Complete Setup (Recommended)

### Step 1: Create Container with Proper Configuration

```bash
#!/bin/bash
# create-smarthome-lxc.sh

CONTAINER_ID=101
CONTAINER_NAME="smarthome-dashboard"
CONTAINER_IP="192.168.1.100"
BRIDGE="vmbr0"

# Create container (2GB RAM, 2 cores, 20GB disk)
qm create ${CONTAINER_ID} \
    --template debian-12-standard-1 \
    --cores 2 \
    --memory 2048 \
    --disk0 "local:20,vmvolume=rootfs,writable=true" \
    --net0 "bridge=${BRIDGE},firewall=1,ip=${CONTAINER_IP},ipconfig0=none,type=veth" \
    --name ${CONTAINER_NAME}

# Start container
qm start ${CONTAINER_ID}

echo "✅ Container ${CONTAINER_ID} created"
echo "📡 Access at: http://${CONTAINER_IP}:1880"
```

### Step 2: Post-Installation Setup

```bash
# Configure Node-RED with systemd
node-red-config.sh ${CONTAINER_IP}
```

### Step 3: Configure Firewall

```bash
# On Proxmox host
qm set 101 --name "smarthome-dashboard" --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100,type=veth"
qm firewall set 101 rule add family=inet protocol=tcp destination=192.168.1.0/24 destination-port=1880
```

## Configuration Files

### LXC Config Template (`lxc-config.json`)
```json
{
  "lxc": {
    "lxc.arch": "amd64",
    "lxc.utsname": "debian",
    "lxc.rootfs.path": "/var/lib/lxc/101/rootfs",
    "lxc.id": "101",
    "lxc.description": "SmartHome Dashboard",
    "lxc.network.type": "veth",
    "lxc.network.link": "vmbr0",
    "lxc.network.ip4": "192.168.1.100",
    "lxc.apparmor.profile": "unconfined",
    "lxc.cap.drop": "",
    "lxc.mount.auto": "proc:rw sys:rw"
  }
}
```

### Systemd Service (`node-red.service`)
```ini
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

[Install]
WantedBy=multi-user.target
```

## Advanced Configuration

### Custom Resource Allocation

Edit the container creation command:
- **RAM**: Increase `--memory` parameter (e.g., `--memory 4096` for 4GB)
- **CPU**: Increase `--cores` parameter (e.g., `--cores 4` for more processing)
- **Disk**: Add `--disk0 "local:50,vmvolume=rootfs,writable=true"` for 50GB

### Network Configuration

For isolated network access:
```bash
qm set 101 --net0 "bridge=vmbr1,firewall=1,ip=192.168.10.100,type=veth"
# where vmbr1 is your isolated bridge
```

### Persistence and Backups

```bash
# Create LXC snapshot
qm snapshot 101 "smarthome-backup"

# Backup rootfs to ISO
qm export 101 /root/smashome-dashboard-backup.tar.gz
```

## Troubleshooting

### Container Won't Start
```bash
# Check logs
qm list
qm status 101
qm stop 101
qm start 101
```

### Node-RED Not Running
```bash
# Inside container
systemctl status node-red
journalctl -u node-red -f

# Restart
systemctl restart node-red
```

### Network Issues
```bash
# Check container IP
qm set 101 --ip-config

# Test connectivity
ping -c 4 192.168.1.1
```

## Container Management Commands

| Command | Description |
|---------|-------------|
| `qm create 101 ...` | Create container |
| `qm start 101` | Start container |
| `qm stop 101` | Stop container |
| `qm restart 101` | Restart container |
| `qm suspend 101` | Suspend container |
| `qm resume 101` | Resume suspended container |
| `qm delete 101 --purge` | Delete container |
| `qm set 101 --memory 4096` | Change resources |
| `qm terminal 101` | Open shell |
| `qm snapshot 101 "name"` | Create snapshot |
| `qm export 101 /path.tar.gz` | Export backup |
| `qm importcontainer /path.tar.gz 102` | Import backup |

## Environment Variables

Create `.env` in container:
```bash
cat > /home/node-red/.env << EOF
# Dashboard Configuration
NODERED_CONFIG_OPTS=--userdir=/home/node-red/.node-red
EOF
```

## Security Considerations

1. **Firewall Rules**: Only allow necessary ports from specific networks
2. **SSH Access**: Disable SSH for the container or use key-based auth only
3. **Network Isolation**: Use isolated bridge for IoT devices
4. **Regular Updates**: `apt-get update && apt-get upgrade`

## Next Steps

1. Import dashboard flows from `flows/` directory
2. Configure Hubitat and UniFi credentials
3. Set up mobile device access
4. Enable HTTPS with reverse proxy (nginx/traefik)

---

**See also:**
- [Main Project README](../README.md)
- [Node-RED Documentation](https://nodered.org/docs/)
- [Proxmox LXC Documentation](https://pve.proxmox.com/wiki/Linux_Virtual_Container_(LXC))
