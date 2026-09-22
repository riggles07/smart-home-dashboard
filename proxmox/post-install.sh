#!/bin/bash
# Post-Installation Configuration Script

set -e

echo "⚙️  Configuring Node-RED..."

# Ensure non-root node-red user exists
if id "node-red" &>/dev/null; then
    echo "User node-red already exists"
else
    echo "Creating non-root node-red user..."
    useradd -m -s /bin/bash node-red
    mkdir -p /home/node-red/.node-red
    chown -R node-red:node-red /home/node-red
    chmod 700 /home/node-red/.node-red
fi

# Create systemd service with security hardening
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

# Security hardening for non-root Node-RED service
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/home/node-red
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=true

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd
systemctl daemon-reload

# Enable and start service
systemctl enable node-red
systemctl start node-red

# Configure firewall
ufw allow 1880/tcp  # HTTP (fallback)
ufw allow 1881/tcp  # HTTPS
ufw allow from 192.168.1.0/24 to any port 1880 comment "Allow local network HTTP access"
ufw allow from 192.168.1.0/24 to any port 1881 comment "Allow local network HTTPS access"
ufw --force enable

echo "✅ Firewall configured - local network access only"

# Set secure permissions
chmod 600 /home/node-red/.node-red/*

echo "✅ Post-installation complete"
echo "📡 Node-RED is running at: http://$(hostname -I | awk '{print $1}'):1880"
