#!/bin/bash
# Proxmox LXC Container Setup Script

set -e

CONTAINER_ID="${1:-101}"
CONTAINER_IP="${2:-192.168.1.100}"
NETWORK="${3:-vmbr0}"

echo "📦 Creating Proxmox LXC container..."
echo "ID: ${CONTAINER_ID}"
echo "IP: ${CONTAINER_IP}"
echo "Network: ${NETWORK}"

# Create container
qm create ${CONTAINER_ID} --template debian-12-standard --cores 2 --memory 2048 \
    --net0 "bridge=${NETWORK},firewall=1,ip=dhcp,type=veth" \
    --name "node-red-dashboard"

# Configure networking
qm set ${CONTAINER_ID} --ip ${CONTAINER_IP} --net0 "bridge=${NETWORK},firewall=1,ip=${CONTAINER_IP},type=veth"

# Start container
qm start ${CONTAINER_ID}

echo "✅ Container ${CONTAINER_ID} created and started"
echo "📡 Access at: http://${CONTAINER_IP}:1880"
echo ""
echo "Note: Configure firewall rules after container setup:"
echo "  qm firewall set ${CONTAINER_ID} rule add family=inet protocol=tcp destination=192.168.1.0/24 destination-port=1880"
echo "  qm firewall set ${CONTAINER_ID} rule add family=inet protocol=tcp destination=192.168.1.0/24 destination-port=1881"
