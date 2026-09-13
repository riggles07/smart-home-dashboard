/**
 * Hubitat Integration Flow
 * Smart home device controls and automation
 */
module.exports = function (RED) {
    "use strict";

    class HubitatNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.apiKey = null;
            this.baseUrl = null;
            this.devices = [];
            this.activeAutomations = [];
        }

        init() {
            // Initialize API connection
            this.baseUrl = this.config.url || 'http://hubitat.local:8080';
            this.apiKey = this.config.apiKey;
            
            // Subscribe to device events
            this.on('subscribe', (event) => {
                if (event.type === 'device-state') {
                    this.updateDeviceState(event.deviceId);
                }
            });

            // Set up auto-refresh for device states
            this.setInterval(this.refreshDevices, this.config.refresh || 60000);
        }

        refreshDevices() {
            // Get all devices
            this.getDevices((err, devices) => {
                if (!err) {
                    this.devices = devices || [];
                    this.status({
                        fill: 'green',
                        shape: 'dot',
                        text: `${this.devices.length} devices`
                    });
                    this.send({ payload: this.devices });
                }
            });
        }

        getDevices(callback) {
            const url = `${this.baseUrl}/api/v1/devices`;
            this.sendRequest('GET', url, null, callback);
        }

        getDevice(deviceId, callback) {
            const url = `${this.baseUrl}/api/v1/devices/${deviceId}`;
            this.sendRequest('GET', url, null, callback);
        }

        updateDevice(deviceId, data, callback) {
            const url = `${this.baseUrl}/api/v1/devices/${deviceId}`;
            this.sendRequest('PUT', url, data, callback);
        }

        triggerAutomation(automationId, callback) {
            const url = `${this.baseUrl}/api/v1/automations/${automationId}/trigger`;
            this.sendRequest('POST', url, null, callback);
        }

        getAutomations(callback) {
            const url = `${this.baseUrl}/api/v1/automations`;
            this.sendRequest('GET', url, null, callback);
        }

        updateAutomation(automationId, data, callback) {
            const url = `${this.baseUrl}/api/v1/automations/${automationId}`;
            this.sendRequest('PUT', url, data, callback);
        }

        deleteAutomation(automationId, callback) {
            const url = `${this.baseUrl}/api/v1/automations/${automationId}`;
            this.sendRequest('DELETE', url, null, callback);
        }

        sendRequest(method, url, data, callback) {
            // Simulated HTTP request
            // In production, use node-red-contrib-http-request
            setTimeout(() => {
                const response = {
                    success: true,
                    data: data || {},
                    message: 'Hubitat request completed'
                };
                callback(null, response);
            }, 100);
        }

        updateDeviceState(deviceId) {
            this.getDevice(deviceId, (err, device) => {
                if (!err && device) {
                    this.send({
                        payload: device,
                        topic: `hubitat/device/${deviceId}/state`
                    });
                }
            });
        }

        getAutomationStatus(automationId, callback) {
            const url = `${this.baseUrl}/api/v1/automations/${automationId}/status`;
            this.sendRequest('GET', url, null, callback);
        }
    }

    RED.nodes.registerType("hubitat-control", HubitatNode);

    return HubitatNode;
};
