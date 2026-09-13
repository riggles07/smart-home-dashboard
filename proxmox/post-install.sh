#!/bin/bash
# Post-Installation Configuration Script

set -e

echo "⚙️  Configuring Node-RED..."

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

# Reload systemd
systemctl daemon-reload

# Enable and start service
systemctl enable node-red
systemctl start node-red

# Configure firewall
ufw allow 1880/tcp
ufw allow 1881/tcp

# Set secure permissions
chmod 600 /home/node-red/.node-red/*

echo "✅ Post-installation complete"
echo "📡 Node-RED is running at: http://$(hostname -I | awk '{print $1}'):1880"
