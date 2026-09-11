#!/bin/bash
# Node-RED Installation Script for LXC Container

set -e

echo "🔧 Installing Node-RED in LXC container..."

# Update system
apt-get update -y && apt-get upgrade -y

# Install Node.js 20.x LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Verify installation
node --version
npm --version

# Install Node-RED globally
npm install -g node-red

# Create user
useradd -m -s /bin/bash node-red

# Set up directories
mkdir -p /home/node-red/.node-red
chown -R node-red:node-red /home/node-red

# Install dashboard packages
npm install -g node-red-dashboard
npm install -g node-red-node-hubitat
npm install -g node-red-node-unifi

echo "✅ Node-RED installed successfully"
echo "📡 Start with: node-red"
