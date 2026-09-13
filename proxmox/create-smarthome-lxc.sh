#!/bin/bash
# create-smarthome-lxc.sh
# Quick script to create and configure SmartHome Dashboard LXC container

set -e

# Configuration
CONTAINER_ID="${1:-101}"
CONTAINER_NAME="smarthome-dashboard"
CONTAINER_IP="${2:-192.168.1.100}"
BRIDGE="${3:-vmbr0}"
MEMORY="${4:-2048}"
CPUS="${5:-2}"
DISK="${6:-20}"

echo "📦 Creating Proxmox LXC Container for SmartHome Dashboard"
echo "=========================================================="
echo "ID: ${CONTAINER_ID}"
echo "Name: ${CONTAINER_NAME}"
echo "IP: ${CONTAINER_IP}"
echo "Bridge: ${BRIDGE}"
echo "RAM: ${MEMORY}MB"
echo "CPU: ${CPUS} cores"
echo "Disk: ${DISK}GB"
echo ""

# Check if container exists
if qm list | grep -q "^${CONTAINER_ID}"; then
    echo "⚠️  Container ${CONTAINER_ID} already exists"
    read -p "Do you want to delete it first? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        qm delete ${CONTAINER_ID} --purge
    else
        echo "Cancelled"
        exit 1
    fi
fi

# Create container
echo "📦 Creating container..."
qm create ${CONTAINER_ID} \
    --template debian-12-standard-1 \
    --cores ${CPUS} \
    --memory ${MEMORY} \
    --disk0 "local:${DISK},vmvolume=rootfs,writable=true" \
    --net0 "bridge=${BRIDGE},firewall=1,ip=${CONTAINER_IP},ipconfig0=none,type=veth" \
    --name ${CONTAINER_NAME}

echo "✅ Container created"

# Start container
echo "▶️  Starting container..."
qm start ${CONTAINER_ID}

echo ""
echo "✅ Container ${CONTAINER_ID} created and started!"
echo ""
echo "📡 Access Node-RED at: http://${CONTAINER_IP}:1880"
echo ""
echo "📝 Next steps:"
echo "   1. SSH into container: qm terminal ${CONTAINER_ID}"
echo "   2. Install Node.js and Node-RED:"
echo "      apt-get update && apt-get install -y nodejs npm wget curl"
echo "      npm install -g node-red"
echo "   3. Start Node-RED: node-red"
echo "   4. Import dashboard flows"
echo ""
echo "📖 Full documentation: proxmox/README.md"
