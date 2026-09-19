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

    // Hubitat Control Node -- carries the device control surface the Devices
    // view renders. Each widget maps onto a Hubitat Maker API command; the UI
    // publishes {"deviceId","command","value"} on input_topic and results come
    // back on output_topic (see hubitat-integration.js controlDevice()).
    RED.nodes.addType("hubitat-control", {
        label: "Hubitat Control",
        type: "hubitat-control",
        common: {
            label: "Device Control",
            inputTopic: "hubitat/device/+/control",
            outputTopic: "hubitat/device/+/command",
            widgets: [
                { command: "on", capability: "switch", widget: "ui_switch" },
                { command: "off", capability: "switch", widget: "ui_switch" },
                { command: "setLevel", capability: "dimmer", widget: "ui_slider", args: ["level", "duration"] },
                { command: "setColor", capability: "color-bulb", widget: "ui_colour_picker", args: ["hue", "saturation", "level"] },
                { command: "setColorTemperature", capability: "color-bulb", widget: "ui_slider", args: ["temperature", "level"] },
                { command: "refresh", capability: "common", widget: "ui_button" }
            ]
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
