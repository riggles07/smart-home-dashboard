#!/bin/bash
#
# SmartHome Dashboard - LXC Deployment Script
# Quick automated deployment for Proxmox LXC containers
#
# Usage: ./deploy-lxc.sh [OPTIONS]
#
# Options:
#   --id <int>      Container ID (default: 101)
#   --ip <string>   Container IP address (default: 192.168.1.100)
#   --bridge <string> Network bridge (default: vmbr0)
#   --ram <int>     Memory in MB (default: 2048)
#   --cpus <int>    CPU cores (default: 2)
#   --disk <int>    Disk size in GB (default: 20)
#   --name <string> Container name (default: smarthome-dashboard)
#   --template <string> LXC template (default: debian-12-standard-1)
#   --help          Show this help message
#

set -e

# Default values
CONTAINER_ID="101"
CONTAINER_IP="192.168.1.100"
CONTAINER_NAME="smarthome-dashboard"
BRIDGE="vmbr0"
MEMORY="2048"
CPUS="2"
DISK="20"
TEMPLATE="debian-12-standard-1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
echo_color() {
    echo -e "${BLUE}📦${NC} $1"
}

echo_success() {
    echo -e "${GREEN}✅${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

echo_error() {
    echo -e "${RED}❌${NC} $1"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --id)
            CONTAINER_ID="$2"
            shift 2
            ;;
        --ip)
            CONTAINER_IP="$2"
            shift 2
            ;;
        --bridge)
            BRIDGE="$2"
            shift 2
            ;;
        --ram)
            MEMORY="$2"
            shift 2
            ;;
        --cpus)
            CPUS="$2"
            shift 2
            ;;
        --disk)
            DISK="$2"
            shift 2
            ;;
        --name)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        --template)
            TEMPLATE="$2"
            shift 2
            ;;
        --help)
            echo "SmartHome Dashboard - LXC Deployment Script"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --id <int>        Container ID (default: 101)"
            echo "  --ip <string>     Container IP (default: 192.168.1.100)"
            echo "  --bridge <string> Network bridge (default: vmbr0)"
            echo "  --ram <int>       Memory in MB (default: 2048)"
            echo "  --cpus <int>      CPU cores (default: 2)"
            echo "  --disk <int>      Disk size in GB (default: 20)"
            echo "  --name <string>   Container name (default: smarthome-dashboard)"
            echo "  --template <str>  LXC template (default: debian-12-standard-1)"
            echo "  --help            Show this help message"
            exit 0
            ;;
        *)
            echo_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo_error "This script must be run as root"
    exit 1
fi

# Check if Proxmox VE is available
if ! command -v qm &> /dev/null; then
    echo_error "qm command not found. Please install Proxmox VE."
    exit 1
fi

echo ""
echo_color "SmartHome Dashboard - LXC Container Deployment"
echo "================================================"
echo "Container ID: ${CONTAINER_ID}"
echo "Container Name: ${CONTAINER_NAME}"
echo "IP Address: ${CONTAINER_IP}"
echo "Network Bridge: ${BRIDGE}"
echo "Memory: ${MEMORY}MB"
echo "CPU Cores: ${CPUS}"
echo "Disk: ${DISK}GB"
echo "Template: ${TEMPLATE}"
echo ""

# Check if container exists
if qm list | grep -q "^${CONTAINER_ID}"; then
    echo_warning "Container ${CONTAINER_ID} already exists"
    echo "Current container status:"
    qm status ${CONTAINER_ID}
    echo ""
    read -p "Do you want to delete it first? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo_error "Deployment cancelled"
        exit 1
    fi
    echo_success "Deleting existing container..."
    qm delete ${CONTAINER_ID} --purge
fi

# Create container
echo_color "Creating LXC container..."
echo "  Template: ${TEMPLATE}"
echo "  Cores: ${CPUS}"
echo "  Memory: ${MEMORY}MB"
echo "  Disk: ${DISK}GB"
echo "  Network: ${BRIDGE}"
echo "  IP: ${CONTAINER_IP}"
echo ""

qm create ${CONTAINER_ID} \
    --template ${TEMPLATE} \
    --cores ${CPUS} \
    --memory ${MEMORY} \
    --disk0 "local:${DISK},vmvolume=rootfs,writable=true" \
    --net0 "bridge=${BRIDGE},firewall=1,ip=${CONTAINER_IP},ipconfig0=none,type=veth" \
    --name ${CONTAINER_NAME}

echo_success "Container ${CONTAINER_ID} created"

# Start container
echo_color "Starting container..."
qm start ${CONTAINER_ID}
echo_success "Container started"

# Wait for container to be ready
echo "Waiting for container to initialize..."
sleep 5

# Verify container is running
if ! qm status ${CONTAINER_ID} | grep -q "running"; then
    echo_error "Failed to start container. Check Proxmox logs for details."
    exit 1
fi

echo_success "Container ${CONTAINER_ID} is running!"
echo ""

# Get container IP
CONTAINER_IP=$(qm set ${CONTAINER_ID} --get ip)
echo_color "📡 Dashboard will be accessible at:"
echo "   http://${CONTAINER_IP}:1880"
echo ""
echo "📝 Next steps:"
echo "   1. SSH into container: qm terminal ${CONTAINER_ID}"
echo "   2. Install Node.js and Node-RED (run setup.sh inside container):"
echo "      apt-get update && apt-get install -y nodejs npm wget curl"
echo "      npm install -g node-red"
echo "   3. Start Node-RED: node-red"
echo "   4. Import dashboard flows from flows/ directory"
echo "   5. Configure Hubitat and UniFi credentials"
echo ""
echo "📖 Full documentation: deploy/README.md"
echo ""

# Show container details
echo_color "📋 Container Details:"
qm list ${CONTAINER_ID}
echo ""

echo "✅ Deployment complete!"
echo "   Run 'qm terminal ${CONTAINER_ID}' to start setup"
echo ""
