#!/bin/bash
#
# SmartHome Dashboard - Container Management Script
# Manage multiple SmartHome Dashboard LXC containers
#
# Usage: ./manage.sh [COMMAND] [OPTIONS]
#
# Commands:
#   list              List all containers
#   create            Create a new container
#   delete            Delete a container
#   start             Start a container
#   stop              Stop a container
#   restart           Restart a container
#   status            Show container status
#   logs              Show container logs
#   ssh               SSH into container
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Default values
CONTAINER_ID="101"
TEMPLATE_ID="200"

# Commands
list() {
    echo_color "📋 SmartHome Dashboard Containers"
    echo "================================="
    echo ""
    printf "%-6s %-20s %-10s %-10s\n" "ID" "NAME" "STATUS" "IP"
    printf "%-6s %-20s %-10s %-10s\n" "----" "--------------------" "----------" "---"
    
    qm list | while read line; do
        id=$(echo "$line" | awk '{print $1}')
        name=$(echo "$line" | awk '{print $2}')
        status=$(echo "$line" | awk '{print $3}')
        # Extract IP if available
        ip=$(qm set "$id" --get ip 2>/dev/null || echo "N/A")
        
        # Filter for SmartHome containers
        if [[ "$name" == *"smarthome"* ]] || [[ "$name" == *"node-red"* ]] || [[ "$name" == *"dashboard"* ]]; then
            printf "%-6s %-20s %-10s %-10s\n" "$id" "$name" "$status" "$ip"
        fi
    done
    echo ""
}

create() {
    local id="${1:-$CONTAINER_ID}"
    local name="${2:-smarthome-dashboard}"
    local ip="${3:-192.168.1.100}"
    local bridge="${4:-vmbr0}"
    local ram="${5:-2048}"
    local cpus="${6:-2}"
    local disk="${7:-20}"

    echo_color "Creating container: ${id}"
    echo "  Name: ${name}"
    echo "  IP: ${ip}"
    echo "  Bridge: ${bridge}"
    echo "  RAM: ${ram}MB"
    echo "  CPU: ${cpus}"
    echo "  Disk: ${disk}GB"
    echo ""

    if ! qm list | grep -q "^${id}"; then
        qm create ${id} \
            --template ${TEMPLATE_ID} \
            --cores ${cpus} \
            --memory ${ram} \
            --disk0 "local:${disk},vmvolume=rootfs,writable=true" \
            --net0 "bridge=${bridge},firewall=1,ip=${ip},ipconfig0=none,type=veth" \
            --name ${name}
        echo_success "Container ${id} created"
        
        qm start ${id}
        echo_success "Container started"
        
        echo ""
        echo_color "📡 Dashboard at: http://${ip}:1880"
        echo "Next: qm terminal ${id} && ./setup.sh"
    else
        echo_warning "Container ${id} already exists"
    fi
}

delete() {
    local id="$1"
    
    echo_color "Deleting container: ${id}"
    read -p "Are you sure? (y/N): " confirm
    
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        qm delete ${id} --purge
        echo_success "Container ${id} deleted"
    else
        echo "Cancelled"
    fi
}

start() {
    local id="$1"
    
    echo_color "Starting container: ${id}"
    qm start ${id}
    
    if qm status ${id} | grep -q "running"; then
        echo_success "Container ${id} started"
    else
        echo_error "Failed to start container"
    fi
}

stop() {
    local id="$1"
    
    echo_color "Stopping container: ${id}"
    qm stop ${id}
    echo_success "Container ${id} stopped"
}

restart() {
    local id="$1"
    
    echo_color "Restarting container: ${id}"
    qm restart ${id}
    echo_success "Container ${id} restarted"
}

status() {
    local id="$1"
    
    echo_color "Container status: ${id}"
    qm status ${id}
    echo ""
    echo "Configuration:"
    qm set ${id} --format json | jq .
}

logs() {
    local id="$1"
    local lines="${2:-50}"
    
    echo_color "Container logs: ${id}"
    echo "Last ${lines} lines"
    echo "================"
    qm console ${id} | tail -n ${lines}
}

ssh() {
    local id="$1"
    
    echo_color "SSH into container: ${id}"
    echo "Press Ctrl+C to exit"
    echo ""
    qm terminal ${id}
}

# Main command handling
if [[ $# -eq 0 ]]; then
    echo "SmartHome Dashboard - Container Management"
    echo ""
    echo "Usage: $0 [COMMAND] [OPTIONS]"
    echo ""
    echo "Commands:"
    echo "  list              List all containers"
    echo "  create [id] [name] [ip] [bridge] [ram] [cpus] [disk]"
    echo "  delete <id>"
    echo "  start <id>"
    echo "  stop <id>"
    echo "  restart <id>"
    echo "  status <id>"
    echo "  logs <id> [lines]"
    echo "  ssh <id>"
    exit 0
fi

COMMAND="$1"
shift

case $COMMAND in
    list)
        list
        ;;
    create)
        create "$@"
        ;;
    delete)
        delete "$@"
        ;;
    start)
        start "$@"
        ;;
    stop)
        stop "$@"
        ;;
    restart)
        restart "$@"
        ;;
    status)
        status "$@"
        ;;
    logs)
        logs "$@"
        ;;
    ssh)
        ssh "$@"
        ;;
    *)
        echo_error "Unknown command: $COMMAND"
        exit 1
        ;;
esac
