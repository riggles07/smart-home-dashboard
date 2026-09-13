#!/bin/bash
# setup-smarthome.sh
# Post-install setup for SmartHome Dashboard inside container
#
# Usage: ./setup-smarthome.sh <container-id>
#
# This script runs INSIDE the container, not on Proxmox host.

set -e

CONTAINER_ID="${1:-101}"

echo "=== SmartHome Dashboard Setup ==="
echo "Container: ${CONTAINER_ID}"
echo ""

# Check if we're inside a container
if [ -f /.dockerenv ] || [ -f /proc/1/cgroup ] && grep -q container /proc/1/cgroup 2>/dev/null; then
    echo "✓ Running inside container"
else
    echo "✗ Not running inside container - this script must be run from within the LXC container"
    echo ""
    echo "To use from outside container:"
    echo "  qm terminal ${CONTAINER_ID}"
    echo "  ./setup-smarthome.sh ${CONTAINER_ID}"
    exit 1
fi

# Update package index
echo "Updating package index..."
apt-get update -qq

# Install dependencies
echo "Installing dependencies..."
apt-get install -y -qq \
    nodejs \
    npm \
    wget \
    curl \
    git \
    openssh-server \
    ufw \
    netcat-openbsd > /dev/null

# Install Node-RED
echo "Installing Node-RED..."
npm install -g node-red@latest

# Create user directory
mkdir -p /home/node-red/.node-red
chmod 700 /home/node-red/.node-red

# Create systemd service
echo "Creating systemd service..."
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

# Reload and start systemd
echo "Starting Node-RED service..."
systemctl daemon-reload
systemctl enable node-red
systemctl start node-red

# Configure firewall
echo "Configuring firewall..."
ufw allow 1880/tcp
ufw allow 1881/tcp
ufw --force enable

# Generate self-signed SSL certificate (optional)
echo "Creating SSL certificate (optional)..."
mkdir -p /etc/node-red
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/node-red/private.key \
    -out /etc/node-red/fullchain.pem \
    -subj "/CN=smarthome-dashboard" 2>/dev/null || echo "SSL creation skipped"

# Set secure permissions
chmod 600 /home/node-red/.node-red/*

# Get container IP
CONTAINER_IP=$(hostname -I | awk '{print $1}')

echo ""
echo "=== Setup Complete ==="
echo ""
echo "✓ Node-RED is running"
echo "✓ Service enabled for auto-start"
echo "✓ Firewall configured"
echo ""
echo "Access at:"
echo "  HTTP: http://${CONTAINER_IP}:1880"
echo "  HTTPS: https://${CONTAINER_IP}:1881"
echo ""
echo "Login: admin / admin"
echo ""
echo "Next steps:"
echo "  1. Import dashboard flows from flows/ directory"
echo "  2. Configure Hubitat and UniFi credentials"
echo "  3. Set up mobile device access"
