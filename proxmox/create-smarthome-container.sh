#!/bin/bash
# create-smarthome-container.sh
# Creates a SmartHome Dashboard LXC container via Proxmox API
#
# Usage: ./create-smarthome-container.sh <container-id> <container-ip> [proxmox-host]
#
# IMPORTANT: This script runs from WITHIN your container, not on the Proxmox host.
# It uses the Proxmox REST API to create containers.

set -e

# Default values
CONTAINER_ID="${1:-101}"
CONTAINER_IP="${2:-192.168.1.100}"
PROXMOX_HOST="${3:-proxmox}"  # Default to 'proxmox' if in same network
PROXMOX_USER="${PROXMOX_USER:-root@pam}"
PROXMOX_PASS="${PROXMOX_PASS:-change-me}"
NODE_NAME="${NODE_NAME:-your-node}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== SmartHome Dashboard Container Creator ===${NC}"
echo "Container ID: ${CONTAINER_ID}"
echo "Container IP: ${CONTAINER_IP}"
echo "Proxmox Host: ${PROXMOX_HOST}"
echo "Proxmox Node: ${NODE_NAME}"
echo ""

# Check if container already exists
echo -e "${YELLOW}Checking if container ${CONTAINER_ID} exists...${NC}"
EXISTING=$(curl -s -u "${PROXMOX_USER}:${PROXMOX_PASS}" \
    "https://${PROXMOX_HOST}:8006/api2/json/nodes/${NODE_NAME}/lxc" | \
    grep -o "\"vmid\": *[0-9]*" | grep -o "[0-9]*" || echo "")

if [ -n "$EXISTING" ] && [ "$EXISTING" = "$CONTAINER_ID" ]; then
    echo -e "${RED}⚠️  Container ${CONTAINER_ID} already exists!${NC}"
    read -p "Do you want to delete it first? (y/N): " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}Deleting existing container...${NC}"
        curl -s -X DELETE \
            -u "${PROXMOX_USER}:${PROXMOX_PASS}" \
            "https://${PROXMOX_HOST}:8006/api2/json/nodes/${NODE_NAME}/lxc/${CONTAINER_ID}" > /dev/null
        echo -e "${GREEN}✓ Deleted${NC}"
    else
        echo -e "${RED}Cancelled${NC}"
        exit 1
    fi
fi

# Create container
echo -e "${GREEN}Creating container...${NC}"
RESPONSE=$(curl -s -X POST \
    -u "${PROXMOX_USER}:${PROXMOX_PASS}" \
    "https://${PROXMOX_HOST}:8006/api2/json/nodes/${NODE_NAME}/lxc/create" \
    -H "Content-Type: application-x-www-form-urlencoded" \
    --data-urlencode "vmid=${CONTAINER_ID}" \
    --data-urlencode "template=debian-12-standard" \
    --data-urlencode "cores=2" \
    --data-urlencode "memory=2048" \
    --data-urlencode "net0=bridge=vmbr0,firewall=1,ip=${CONTAINER_IP},type=veth" \
    --data-urlencode "disksize=20" \
    --data-urlencode "name=smarthome-dashboard")

# Check response
if echo "$RESPONSE" | grep -q "data:.*task"; then
    TASK_ID=$(echo "$RESPONSE" | grep -o '"task":"[^"]*"' | cut -d'"' -f4)
    echo -e "${YELLOW}Task created: $TASK_ID${NC}"
    
    echo -e "${YELLOW}Waiting for task to complete...${NC}"
    sleep 10
    
    # Check task status
    STATUS=$(curl -s -u "${PROXMOX_USER}:${PROXMOX_PASS}" \
        "https://${PROXMOX_HOST}:8006/api2/json/tasks/${TASK_ID}")
    
    if echo "$STATUS" | grep -q "data:.*status:.*finished"; then
        echo -e "${GREEN}✓ Container ${CONTAINER_ID} created successfully!${NC}"
        echo ""
        echo -e "${GREEN}Access Node-RED at: http://${CONTAINER_IP}:1880${NC}"
        echo ""
        echo -e "${YELLOW}Next steps:${NC}"
        echo "  1. SSH into container: qm terminal ${CONTAINER_ID}"
        echo "  2. Install Node.js: apt-get update && apt-get install -y nodejs npm"
        echo "  3. Install Node-RED: npm install -g node-red"
        echo "  4. Start: node-red"
    else
        echo -e "${RED}✗ Container creation failed${NC}"
        echo "$STATUS"
        exit 1
    fi
else
    echo -e "${RED}✗ Failed to create container${NC}"
    echo "$RESPONSE"
    exit 1
fi
