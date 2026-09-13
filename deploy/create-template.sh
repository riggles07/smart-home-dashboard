#!/bin/bash
#
# SmartHome Dashboard - LXC Container Import Script
# Creates a deployable LXC container template for Proxmox
#
# Usage: ./create-template.sh [OPTIONS]
#
# This creates a template container that can be cloned to create
# additional SmartHome Dashboard containers quickly.
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo_color() {
    echo -e "${BLUE}📦${NC} $1"
}

echo_success() {
    echo -e "${GREEN}✅${NC} $1"
}

echo_warning() {
    echo -e "${YELLOW}⚠️${NC} $1"
}

# Default values
TEMPLATE_ID="200"
TEMPLATE_NAME="smarthome-dashboard-template"
BRIDGE="vmbr0"
MEMORY="2048"
CPUS="2"
DISK="20"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --id)
            TEMPLATE_ID="$2"
            shift 2
            ;;
        --name)
            TEMPLATE_NAME="$2"
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
        --help)
            echo "Create SmartHome Dashboard LXC Template"
            echo ""
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --id <int>       Template ID (default: 200)"
            echo "  --name <str>     Template name (default: smarthome-dashboard-template)"
            echo "  --bridge <str>   Network bridge (default: vmbr0)"
            echo "  --ram <int>      Memory in MB (default: 2048)"
            echo "  --cpus <int>     CPU cores (default: 2)"
            echo "  --disk <int>     Disk size in GB (default: 20)"
            echo "  --help           Show this help"
            exit 0
            ;;
        *)
            echo_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo_color "Creating SmartHome Dashboard Template"
echo "======================================"
echo "ID: ${TEMPLATE_ID}"
echo "Name: ${TEMPLATE_NAME}"
echo "Memory: ${MEMORY}MB"
echo "CPU: ${CPUS}"
echo "Disk: ${DISK}GB"
echo "Bridge: ${BRIDGE}"
echo ""

# Check if running as root
if [[ $EUID -ne 0 ]]; then
    echo_error "This script must be run as root"
    exit 1
fi

# Check if Proxmox is available
if ! command -v qm &> /dev/null; then
    echo_error "qm command not found. Please install Proxmox VE."
    exit 1
fi

# Check if template exists
if qm list | grep -q "^${TEMPLATE_ID}"; then
    echo_warning "Template ${TEMPLATE_ID} already exists"
    echo "Current status:"
    qm status ${TEMPLATE_ID}
    echo ""
    read -p "Do you want to delete it first? (y/N): " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        echo_error "Operation cancelled"
        exit 1
    fi
    echo_success "Deleting existing template..."
    qm delete ${TEMPLATE_ID} --purge
fi

# Create template
echo_color "Creating container..."
qm create ${TEMPLATE_ID} \
    --template debian-12-standard-1 \
    --cores ${CPUS} \
    --memory ${MEMORY} \
    --disk0 "local:${DISK},vmvolume=rootfs,writable=true" \
    --net0 "bridge=${BRIDGE},firewall=1,ip=dhcp,type=veth" \
    --name ${TEMPLATE_NAME}

echo_success "Container ${TEMPLATE_ID} created"

# Start container
echo_color "Starting container..."
qm start ${TEMPLATE_ID}

# Wait for container to initialize
echo "Waiting for container to initialize..."
sleep 10

# Verify container is running
if ! qm status ${TEMPLATE_ID} | grep -q "running"; then
    echo_error "Failed to start container"
    exit 1
fi

echo_success "Container is running"

# Convert to template
echo_color "Converting to template..."
qm set ${TEMPLATE_ID} --template 1

echo_success "Template created successfully!"
echo ""

# Show template details
echo_color "📋 Template Details:"
qm list ${TEMPLATE_ID}
echo ""

echo "=========================================="
echo_success "Template Ready for Cloning!"
echo "=========================================="
echo ""
echo "To create a new container from this template:"
echo ""
echo "  # Create container from template"
echo "  qm create <new_id> --template ${TEMPLATE_ID} \\"
echo "      --name smarthome-dashboard-1 \\"
echo "      --net0 bridge=vmbr0,firewall=1,ip=192.168.1.100,type=veth"
echo ""
echo "  # Start container"
echo "  qm start <new_id>"
echo ""
echo "  # SSH into container"
echo "  qm terminal <new_id>"
echo ""
echo "  # Run post-install setup"
echo "  ./setup.sh"
echo ""
