/**
 * Dashboard Configuration Flow
 * Main UI structure for the Smart Home Dashboard
 */
module.exports = function (RED) {
    "use strict";

    // Dashboard configuration
    const dashboard = {
        name: "Smart Home Dashboard",
        version: "1.0.0",
        tabs: {
            dashboard: {
                label: "Dashboard",
                type: "ui_tab",
                order: 1,
                views: {
                    main: {
                        type: "page",
                        name: "Main View",
                        tabs: "row",
                        nodes: []
                    },
                    monitor: {
                        type: "page",
                        name: "Monitor View",
                        nodes: []
                    },
                    devices: {
                        type: "page",
                        name: "Devices",
                        nodes: []
                    },
                    settings: {
                        type: "page",
                        name: "Settings",
                        nodes: []
                    }
                }
            }
        },
        layout: "landscape",
        refresh: 5000,
        theme: "complete"
    };

    // Home Lab Monitor Node
    RED.nodes.addType("home-lab-monitor", {
        label: "Home Lab Monitor",
        type: "ui_gauge",
        common: {
            label: "Node Status",
            format: "%%",
            min: 0,
            max: 100
        }
    });

    // Hubitat Control Node
    RED.nodes.addType("hubitat-control", {
        label: "Hubitat Control",
        type: "hubitat-control",
        common: {
            label: "Device Control"
        }
    });

    // UniFi Monitor Node
    RED.nodes.addType("unifi-monitor", {
        label: "UniFi Monitor",
        type: "unifi-monitor",
        common: {
            label: "Network Monitor"
        }
    });

    // Kanban Card Node
    RED.nodes.addType("kanban-card", {
        label: "Kanban Card",
        type: "kanban-card",
        common: {
            label: "Task Card"
        }
    });

    return dashboard;
};
