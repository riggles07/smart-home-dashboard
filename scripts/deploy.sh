#!/bin/bash
# Smart Home Dashboard Deployment Script

set -e

NODE_RED_HOST="${NODE_RED_HOST:-localhost}"
NODE_RED_PORT="${NODE_RED_PORT:-1880}"
DASHBOARD_PATH="/root/smart-home-dashboard"

echo "🚀 Deploying Smart Home Dashboard..."
echo "Target: ${NODE_RED_HOST}:${NODE_RED_PORT}"

# Verify Node-RED is running
echo "📡 Checking Node-RED status..."
curl -f "http://${NODE_RED_HOST}:${NODE_RED_PORT}/api/" || {
    echo "❌ Node-RED is not running. Please start it with: node-red"
    exit 1
}

echo "✅ Node-RED is running at http://${NODE_RED_HOST}:${NODE_RED_PORT}"

# Import flows
echo "📤 Importing dashboard flows..."
node-red -u "${DASHBOARD_PATH}/flows/dashboard-configuration.js"

echo "✅ Dashboard deployed successfully!"
echo "📱 Access at: http://${NODE_RED_HOST}:${NODE_RED_PORT}"
