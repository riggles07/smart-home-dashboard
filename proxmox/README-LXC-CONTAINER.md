# SmartHome Dashboard - Proxmox LXC Deployment Guide (Container-Based)

This guide shows how to deploy the SmartHome Dashboard in a Proxmox LXC container using only commands available from **within your container**.

## Important: Container Context

You are running in: **LXC Container** → **Ubuntu VM** → **Proxmox Host**

The deployment scripts must run from the container side, not Proxmox host.

## Quick Start (From Container)

### Option 1: Proxmox VE Web UI (Recommended)

1. Log in to Proxmox Web UI (e.g., https://your-proxmox-host:8006)
2. Navigate to **Datacenter → Nodes → your-node → Containers**
3. Click **Create LXC Container**
4. Fill in:
   - **Container ID**: 101
   - **Template**: Debian 12 (bookworm) (64-bit)
   - **Memory**: 2048 MB
   - **CPU**: 2 cores
   - **Network**: Bridge (vmbr0), IP: 192.168.1.100
   - **Disk**: 20GB
5. Click **Create**

### Option 2: Proxmox CLI (From Container)

```bash
# Get Proxmox host details
PROXMOX_HOST="your-proxmox-host"
PROXMOX_USER="root@pam"
PROXMOX_PASS="your-password"

# Create container via API (from container)
curl -k -X POST \
  --user "${PROXMOX_USER}:${PROXMOX_PASS}" \
  "https://${PROXMOX_HOST}:8006/api2/json/nodes/your-node/lxc/create" \
  -d '{
    "vmid": 101,
    "template": "debian-12-standard",
    "cores": 2,
    "memory": 2048,
    "net0": "bridge=vmbr0,firewall=1,ip=192.168.1.100,type=veth",
    "name": "smarthome-dashboard",
    "disksize": 20
  }'
```

### Option 3: Copy Scripts to Container

If you want to run scripts from within the container:

```bash
# Copy scripts to container (from host)
scp -r /root/.hermes/projects/smart-home-dashboard/deploy/* root@<container-ip>:/root/

# Or SSH into container and run from there
ssh root@<container-ip>
cd /root
./deploy-lxc.sh --id 101 --ip 192.168.1.100
```

## Container Creation (Manual Method)

### Step 1: Create Container

```bash
# SSH to Proxmox host (from container)
ssh root@<proxmox-host>

# Create container
qm create 101 --template debian-12-standard --cores 2 --memory 2048 \
    --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100,type=veth" \
    --name "smarthome-dashboard"

# Start container
qm start 101
```

### Step 2: Configure Container

```bash
# Set static IP
qm set 101 --ip 192.168.1.100 --net0 "bridge=vmbr0,firewall=1,ip=192.168.1.100,type=veth"

# SSH into container
qm terminal 101
```

## Inside Container Setup

### Step 1: Update and Install Dependencies

```bash
# Inside container (101)
apt-get update && apt-get install -y nodejs npm wget curl git openssh-server

# Install Node-RED
npm install -g node-red

# Start Node-RED
node-red
```

### Step 2: Configure Node-RED

```bash
# Create systemd service
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

# Enable and start
systemctl daemon-reload
systemctl enable node-red
systemctl start node-red

# Configure firewall
ufw allow 1880/tcp
```

## Alternative: Use Docker-in-Docker

If Proxmox LXC access is problematic, run Docker inside your container:

```bash
# Install Docker
apt-get install -y docker.io

# Start Docker service
systemctl start docker
systemctl enable docker

# Run Node-RED in Docker
docker run -d -p 1880:1880 --name smarthome nodered/node-red
```

## Container Management Commands

| Command | Description |
|---------|-------------|
| `qm create 101 ...` | Create container |
| `qm start 101` | Start container |
| `qm stop 101` | Stop container |
| `qm restart 101` | Restart container |
| `qm terminal 101` | Open shell |
| `qm list` | List containers |
| `qm snapshot 101 "backup"` | Create snapshot |
| `qm export 101 /backup.tar.gz` | Export backup |
| `qm delete 101 --purge` | Delete container |

## Proxmox API Example (From Container)

Create `proxmox-api.sh` in container:

```bash
#!/bin/bash
# proxmox-api.sh - Manage containers via Proxmox API

PROXMOX_HOST="your-proxmox-host"
PROXMOX_USER="root@pam"
PROXMOX_PASS="password"
PROXMOX_TOKEN=$(echo -n "${PROXMOX_USER}:${PROXMOX_PASS}" | base64)

# Create container
create_container() {
    local id=$1 ip=$2
    curl -k -X POST \
        --user "${PROXMOX_USER}:${PROXMOX_PASS}" \
        "https://${PROXMOX_HOST}:8006/api2/json/nodes/your-node/lxc/create" \
        -H "Content-Type: application-x-www-form-urlencoded" \
        --data-urlencode "vmid=${id}" \
        --data-urlencode "template=debian-12-standard" \
        --data-urlencode "cores=2" \
        --data-urlencode "memory=2048" \
        --data-urlencode "net0=bridge=vmbr0,firewall=1,ip=${ip},type=veth" \
        --data-urlencode "disksize=20"
}

# List containers
list_containers() {
    curl -k -X GET \
        --user "${PROXMOX_USER}:${PROXMOX_PASS}" \
        "https://${PROXMOX_HOST}:8006/api2/json/access/ticket" \
        -H "Authorization: PVEAPITicket $(curl -k -X POST \
            --user "${PROXMOX_USER}:${PROXMOX_PASS}" \
            "https://${PROXMOX_HOST}:8006/api2/json/access/ticket" \
            -d "username=${PROXMOX_USER}&password=${PROXMOX_PASS}&otp=" | jq -r .data.ticket)" \
        "https://${PROXMOX_HOST}:8006/api2/json/nodes/your-node/lxc"
}
```

## Environment Variables

Create `.env` in container:

```bash
cat > /home/node-red/.env << EOF
# Dashboard Configuration
NODERED_CONFIG_OPTS=--userdir=/home/node-red/.node-red
EOF
```

## Troubleshooting

### Can't Access Proxmox Host from Container

```bash
# Check connectivity
ping <proxmox-host>

# If blocked, add rule in container firewall:
iptables -A OUTPUT -d <proxmox-host> -j ACCEPT
```

### Port Forwarding Through LXC

If container needs to expose ports to host network:

```bash
# On Proxmox host:
qm set 101 --nameserver 8.8.8.8 --ipconfig0 'ip=192.168.1.100,gw=192.168.1.1'
```

### Container Can't Reach Internet

```bash
# Set gateway in container:
qm set 101 --net0 "bridge=vmbr0,firewall=0,ip=192.168.1.100,gw=192.168.1.1,type=veth"
```

## Summary

Since you're in a container that can't access Proxmox host directories:

1. **Use Proxmox Web UI** to create containers (easiest)
2. **Use Proxmox API** via curl from container
3. **Run scripts inside container** (not on host)
4. **Alternative**: Use Docker-in-Docker for Node-RED

The container is your working environment - all operations should be performed from there.
