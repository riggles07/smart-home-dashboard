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
                        // Device tiles are bound to the state node, so a tile
                        // re-renders on every published state snapshot.
                        nodes: [
                            {
                                type: "hubitat-device-state",
                                group: "Device Status",
                                width: 6,
                                order: 1
                            }
                        ]
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

    // Hubitat Device State Node
    // Renders live device attributes (switch/level/hue/temperature/battery/...)
    // as tiles. Fed by the hubitat-control node's state monitoring, which
    // subscribes to hub-pushed events and falls back to TTL-cached polling.
    RED.nodes.addType("hubitat-device-state", {
        label: "Device Status",
        type: "ui_template",
        tab: "dashboard",
        view: "devices",
        group: "Device Status",
        // Tile refresh is the dashboard's own UI refresh; the node's TTL cache
        // means N tiles cost one hub read per TTL window.
        refresh: 5000,
        ttl: 5,
        layout: "grid",
        attributes: [
            "switch",
            "level",
            "temperature",
            "humidity",
            "battery",
            "motion",
            "contact",
            "lock",
            "hue",
            "saturation",
            "colorTemperature"
        ]
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
