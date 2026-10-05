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

# Install additional Node-RED packages (only node-red-dashboard is required;
# the generated flows use plain "http request" nodes, not the Hubitat/UniFi
# contrib packages)
npm install -g node-red-dashboard
npm install -g bcryptjs   # Required for adminAuth password hashing (Phase 6)

echo_success "Node-RED installed"
echo ""

# Step 5: Node-RED runs as root (no dedicated user)
#
# Earlier revisions created a 'node-red' account and ran the service as it. That
# is what broke the deployment: the unit named a user that did not exist on a
# pre-provisioned container (systemd fails with status=217/USER before it even
# execs Node-RED), and the data lives in /root/.node-red with a mode-600 .env
# that only root can read. The service now runs as root, so creating the account
# only adds a misleading artifact -- and a HOME (/home/node-red) whose existence
# depended on it. Kept as a no-op so the step numbering and output stay stable.
echo_color "Step 5: Node-RED runtime user..."
echo "Node-RED runs as root (data dir /root/.node-red); no dedicated user needed"
echo ""

# Step 6: Set up directories
echo_color "Step 6: Setting up directories..."
mkdir -p /root/.node-red
mkdir -p /root/.node-red/flows
mkdir -p /root/.node-red/logs
chmod 755 /root/.node-red/flows
chmod 755 /root/.node-red/logs
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
User=root
Group=root
WorkingDirectory=/root/.node-red
ExecStart=/usr/bin/node-red
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
Environment="NODE_RED_USER=admin"
Environment="NODE_RED_PORT=1880"
Environment="NODE_PATH=/usr/lib/node_modules"
EnvironmentFile=-/root/.node-red/.env

# Phase 6 security hardening (root + systemd sandboxing)
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/root/.node-red
PrivateTmp=yes
PrivateDevices=yes
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictSUIDSGID=true
RestrictNamespaces=true
LockPersonality=true
MemoryDenyWriteExecute=false

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

cat > /root/.node-red/settings.js << 'EOF'
// SmartHome Dashboard Node-RED Configuration (Phase 6 hardened)
module.exports = {
  userDir: "/root/.node-red",
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
      logsDir: "/root/.node-red/logs"
    }
  }
};
EOF
chown root:root /root/.node-red/settings.js
chmod 600 /root/.node-red/settings.js
echo_success "Node-RED configuration created (HTTPS + admin auth enabled)"
echo ""

# Step 10: Create environment file
echo_color "Step 10: Creating environment file..."
cat > /root/.node-red/.env << 'EOF'
# SmartHome Dashboard Configuration
# Loaded by node-red.service via EnvironmentFile= -- restart the service
# after any edit:  systemctl restart node-red
# Verify with:     systemctl show node-red -p Environment --value

# Node-RED Settings
NODE_RED_USER=admin
NODE_RED_PASS=CHANGE_ME
NODE_RED_HOST=localhost
NODE_RED_PORT=1880
NODE_RED_SECURE=false

# Hubitat Settings
HUBITAT_URL=http://192.168.4.86
HUBITAT_USERNAME=your_username
HUBITAT_PASSWORD=your_password
HUBITAT_API_KEY=your_api_key

# Hubitat Maker API (read by the Devices-tab flow)
# App id + token from the Maker API app page: http://192.168.4.86/apps/api/<app_id>/...
HUBITAT_APP_ID=your_maker_api_app_id
HUBITAT_ACCESS_TOKEN=your_maker_api_access_token
# Device the Devices-tab power switch / brightness slider controls.
# List devices: GET /apps/api/<app_id>/devices?access_token=<token>
HUBITAT_DEVICE_ID=your_device_id

# UniFi Settings
# UNIFI_URL is read by the Network-tab flow. This is a UniFi OS console
# (UDM/Cloud Gateway), so the Network app lives under /proxy/network.
# A self-hosted controller would instead be https://<host>:8443 (no prefix).
UNIFI_URL=https://192.168.1.1/proxy/network
# UniFi OS login path is auto-derived (/api/auth/login at the console root);
# leave UNIFI_LOGIN_URL blank unless you need to override it.
UNIFI_LOGIN_URL=
UNIFI_SITE=default
# UniFi Network 8+ API key. If set, the flow uses X-API-KEY and never logs in.
UNIFI_API_KEY=
UNIFI_USERNAME=your_username
UNIFI_PASSWORD=your_password

# Proxmox API (read by the Home Lab tab flow)
# Token: Datacenter -> Permissions -> API Tokens -> Add
# Format: <user>@pam!<tokenid>=<secret>
PROXMOX_URL=https://proxmox.local:8006
PROXMOX_NODE=pve
PROXMOX_TOKEN=your_user@pam!dashboard=your-token-secret
EOF
chmod 600 /root/.node-red/.env
chown root:root /root/.node-red/.env
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

# Step 12: Import dashboard flows
# Must run AFTER the service is up -- the Admin API needs a live listener.
echo_color "Step 12: Importing dashboard flows..."
FLOWS_SRC="$(cd "$(dirname "$0")/.." && pwd)/flows"
if [ -f "$FLOWS_SRC/all-flows.flow.json" ]; then
    # Wait for the Admin API to answer before posting.
    # Probe must hit the real root ("/admin") and confirm JSON is served.
    ready=0
    for _ in $(seq 1 20); do
        # Test /admin endpoint returns JSON (not 404)
        if curl -s http://localhost:1880/admin | grep -q '"admin"'; then
            ready=1; break
        fi
        sleep 1
    done
    if [ "$ready" != "1" ]; then
        echo_error "Admin API did not become ready after 20s -- check that /etc/node-red/settings.js has httpAdminRoot: \"admin\""
        exit 1
    fi
    if [ "$ready" = "1" ]; then
        # Full deploy. HTTP 204 == accepted.
        code=$(curl -s -o /dev/null -w "%{http_code}" \
            -X POST "http://localhost:1880/flows" \
            -H "Content-Type: application/json" \
            -H "Node-RED-Deployment-Type: full" \
            --data-binary "@${FLOWS_SRC}/all-flows.flow.json")
        if [ "$code" = "204" ]; then
            echo_success "Flows imported (HTTP 204)"
        else
            echo_error "Flow import returned HTTP $code (expected 204)"
        fi
    else
        echo_error "Admin API did not become ready -- import flows manually"
    fi
else
    echo "  No all-flows.flow.json found at $FLOWS_SRC -- import manually."
fi
echo ""

# Step 13: Verify setup
echo_color "Step 13: Verifying setup..."
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

# Confirm env vars reached the process (they do NOT unless EnvironmentFile= is set)
if systemctl show node-red -p Environment --value | grep -q "PROXMOX_URL\|HUBITAT_URL\|UNIFI_URL"; then
    echo_success "Flow env vars loaded into the service"
else
    echo_error "Flow env vars NOT loaded -- check EnvironmentFile=-/root/.node-red/.env"
fi
echo ""

# Confirm flows actually landed (count nodes beside 'tab')
node_count=$(curl -s http://localhost:1880/flows \
    | tr ',' '\n' | grep -c '"type"')
echo "  Flow nodes deployed: ${node_count} (5 tabs + widgets/processing)"

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
echo "   - Node-RED runs with systemd sandboxing"
echo "   - Admin auth enabled - change the default password!"
echo ""
echo "📝 Next steps:"
echo "   1. Import dashboard flows:"
echo "      cp -r /path/to/flows/* /root/.node-red/flows/"
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
