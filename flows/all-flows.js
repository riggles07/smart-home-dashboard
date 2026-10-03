// Smart Home Dashboard - All Flows
// Consolidated flow file for Node-RED

module.exports = {
  "dashboard-configuration": require("./dashboard-configuration.js"),
  "home-lab-monitor": require("./home-lab-monitor.js"),
  "hubitat-integration": require("./hubitat-integration.js"),
  "integration-functions": require("./integration-functions.js"),
  "kanban-flow": require("./kanban-flow.js"),
  "unifi-network-monitor": require("./unifi-network-monitor.js")
};
