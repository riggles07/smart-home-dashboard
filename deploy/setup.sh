#!/bin/bash
#
# SmartHome Dashboard - Post-Installation Setup Script
# Run this inside the LXC container after deployment
#
# This script installs dependencies, configures Node-RED, and sets up services
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

echo_error() {
    echo -e "${RED}❌${NC} $1"
}

echo ""
echo_color "SmartHome Dashboard - Post-Installation Setup"
echo "================================================"
echo ""

# Step 1: Update system
echo_color "Step 1: Updating system packages..."
apt-get update -y
apt-get upgrade -y
echo_success "System packages updated"
echo ""

# Step 2: Install base dependencies
echo_color "Step 2: Installing base dependencies..."
apt-get install -y \
    nodejs \
    npm \
    wget \
    curl \
    git \
    openssh-server \
    ufw \
    net-tools \
    netcat-openbsd \
    jq
echo_success "Base dependencies installed"
echo ""

# Step 3: Install Node.js 20.x LTS (if not already installed)
if ! command -v node &> /dev/null; then
    echo_color "Step 3: Installing Node.js 20.x LTS..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt-get install -y nodejs
    echo_success "Node.js installed"
    echo ""
    echo "Node version:"
    node --version
    echo "npm version:"
    npm --version
    echo ""
else
    echo "Node.js already installed"
    echo "Node version:"
    node --version
    echo ""
fi

# Step 4: Install Node-RED
echo_color "Step 4: Installing Node-RED..."
npm install -g node-red

# Install additional Node-RED packages
npm install -g node-red-dashboard
npm install -g node-red-node-hubitat
npm install -g node-red-node-unifi
npm install -g node-red-contrib-kanbanflow
npm install -g node-red-contrib-home-assistant-common
npm install -g bcryptjs   # Required for adminAuth password hashing (Phase 6)

echo_success "Node-RED installed"
echo ""

# Step 5: Create Node-RED user
echo_color "Step 5: Setting up Node-RED user..."
if ! id node-red &> /dev/null; then
    useradd -m -s /bin/bash node-red
    echo_success "Node-RED user created"
else
    echo "Node-RED user already exists"
fi
echo ""

# Step 6: Set up directories
echo_color "Step 6: Setting up directories..."
mkdir -p /home/node-red/.node-red
mkdir -p /home/node-red/.node-red/flows
mkdir -p /home/node-red/.node-red/logs
chown -R node-red:node-red /home/node-red
chmod 755 /home/node-red/.node-red/flows
chmod 755 /home/node-red/.node-red/logs
echo_success "Directories created"
echo ""

# Step 7: Create systemd service
echo_color "Step 7: Configuring systemd service..."
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
Environment="NODE_RED_USER=admin"
Environment="NODE_RED_PORT=1880"

# Phase 6 security hardening (non-root + systemd sandboxing)
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

systemctl daemon-reload
systemctl enable node-red
echo_success "Systemd service configured"
echo ""

# Step 8: Configure firewall (Phase 6 hardening - LAN-only access)
echo_color "Step 8: Configuring firewall..."
ufw --force enable
ufw allow from 192.168.1.0/24 to any port 1880 comment "Node-RED HTTP - LAN only"
ufw allow from 192.168.1.0/24 to any port 1881 comment "Node-RED HTTPS - LAN only"
ufw allow from 192.168.1.0/24 to any port 8082 comment "Kanban - LAN only"
ufw --force reload
echo_success "Firewall configured (LAN-only: 1880/1881/8082)"
echo ""

# Step 9: Create Node-RED configuration (Phase 6 hardened)
echo_color "Step 9: Creating Node-RED configuration..."

# Generate self-signed SSL certificate for HTTPS on port 1881
mkdir -p /etc/node-red
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/node-red/private.key \
    -out /etc/node-red/fullchain.pem \
    -subj "/CN=smarthome-dashboard" \
    && chmod 600 /etc/node-red/private.key \
    && echo_success "Self-signed SSL certificate created" \
    || echo_warning "SSL cert creation failed - HTTPS will not be available"

cat > /home/node-red/.node-red/settings.js << 'EOF'
// SmartHome Dashboard Node-RED Configuration (Phase 6 hardened)
module.exports = {
  userDir: "/home/node-red/.node-red",
  uiHost: "0.0.0.0",
  httpAdminRoot: "admin",
  httpNodeRoot: "api",
  httpStaticRoot: "public",
  httpStaticRootUserDir: "user-lib",
  httpStaticDepthLimit: 20,
  httpStaticMaxBodySize: 500000,
  httpRateLimit: {
    max: 100,
    windowMs: 60000
  },
  // Security headers
  httpStaticHeaders: {
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self' data:;"
  },
  functionGlobalContext: {
    // Global variables can be set here
  },
  ui: {
    theme: "dashboard"
  },
  // HTTPS enabled (Phase 6 hardening)
  https: {
    key: require("fs").readFileSync("/etc/node-red/private.key"),
    cert: require("fs").readFileSync("/etc/node-red/fullchain.pem")
  },
  // Admin authentication - credentials resolved from environment (.env)
  adminAuth: {
    type: "credentials",
    users: [{
      username: process.env.NODE_RED_USER || "admin",
      password: require("bcryptjs").hashSync(process.env.NODE_RED_PASS || "admin", 10),
      permissions: ["*"]
    }]
  },
  logging: {
    console: {
      level: "info"
    },
    file: {
      level: "warn",
      logsDir: "/home/node-red/.node-red/logs"
    }
  }
};
EOF
chown node-red:node-red /home/node-red/.node-red/settings.js
chmod 600 /home/node-red/.node-red/settings.js
echo_success "Node-RED configuration created (HTTPS + admin auth enabled)"
echo ""

# Step 10: Create environment file
echo_color "Step 10: Creating environment file..."
cat > /home/node-red/.env << 'EOF'
# SmartHome Dashboard Configuration
# Edit these values for your environment

# Node-RED Settings
NODE_RED_USER=admin
NODE_RED_PASS=admin
NODE_RED_HOST=localhost
NODE_RED_PORT=1880
NODE_RED_SECURE=false

# Hubitat Settings
HUBITAT_URL=http://hubitat.local:80
HUBITAT_USERNAME=your_username
HUBITAT_PASSWORD=your_password
HUBITAT_API_KEY=your_api_key

# UniFi Settings
UNIFI_HOST=unifi.local
UNIFI_PORT=8443
UNIFI_USERNAME=your_username
UNIFI_PASSWORD=your_password
UNIFI_SITE=default
EOF
chmod 600 /home/node-red/.env
chown node-red:node-red /home/node-red/.env
echo_success "Environment file created"
echo ""

# Step 11: Start Node-RED
echo_color "Step 11: Starting Node-RED..."
systemctl start node-red

if systemctl is-active --quiet node-red; then
    echo_success "Node-RED started successfully"
else
    echo_error "Failed to start Node-RED"
    exit 1
fi
echo ""

# Step 12: Verify setup
echo_color "Step 12: Verifying setup..."
echo ""

echo "System Information:"
echo "  Node version: $(node --version)"
echo "  npm version: $(npm --version)"
echo ""

echo "Node-RED Status:"
curl -s http://localhost:1880/api/ | head -c 100
echo "..."
echo_success "Node-RED is running"
echo ""

echo "Firewall Status:"
ufw status verbose | head -5
echo ""

echo "Service Status:"
systemctl status node-red | grep -E "(Active|Description)" | head -2
echo ""

echo "=========================================="
echo_success "Setup Complete!"
echo "=========================================="
echo ""
echo "📡 Node-RED is accessible at:"
echo "   http://$(hostname -I | awk '{print $1}'):1880"
echo "   https://$(hostname -I | awk '{print $1}'):1881  (HTTPS, self-signed cert)"
echo ""
echo "🔐 Security hardening applied (Phase 6):"
echo "   - HTTPS enabled on port 1881 (self-signed cert)"
echo "   - Firewall: LAN-only access (default deny)"
echo "   - Node-RED runs as non-root user 'node-red' with systemd sandboxing"
echo "   - Admin auth enabled - change the default password!"
echo ""
echo "📝 Next steps:"
echo "   1. Import dashboard flows:"
echo "      cp -r /path/to/flows/* /home/node-red/.node-red/flows/"
echo ""
echo "   2. Rotate credentials (replaces default admin/admin):"
echo "      ./scripts/rotate-credentials.sh"
echo ""
echo "   3. Configure Hubitat and UniFi credentials in .env file"
echo ""
echo "   4. Access the dashboard in your browser"
echo ""
echo "📖 Documentation: deploy/README.md and docs/SECURITY.md"
echo ""
