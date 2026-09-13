/**
 * UniFi Network Monitor Flow
 * Network monitoring and client tracking
 */
module.exports = function (RED) {
    "use strict";

    class UniFiNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.baseUrl = null;
            this.username = null;
            this.password = null;
            this.clients = [];
            this.accessPoints = [];
            this.networkTraffic = {
                upload: 0,
                download: 0,
                total: 0
            };
            this.sessionToken = null;
        }

        init() {
            // Initialize UniFi connection
            this.baseUrl = this.config.url || 'https://unifi.local:8443';
            this.username = this.config.username;
            this.password = this.config.password;

            // Authenticate and get session token
            this.authenticate((err, token) => {
                if (!err) {
                    this.sessionToken = token;
                    this.status({
                        fill: 'green',
                        shape: 'dot',
                        text: 'connected'
                    });
                } else {
                    this.status({
                        fill: 'red',
                        shape: 'ring',
                        text: 'disconnected'
                    });
                }
            });

            // Subscribe to network events
            this.on('subscribe', (event) => {
                if (event.type === 'client-connected') {
                    this.updateClientList();
                } else if (event.type === 'ap-status') {
                    this.updateAPStatus();
                }
            });

            // Set up auto-refresh
            this.setInterval(this.refreshNetwork, this.config.refresh || 30000);
        }

        authenticate(callback) {
            const url = `${this.baseUrl}/api/login`;
            this.sendRequest('POST', url, {
                username: this.username,
                password: this.password
            }, (err, data) => {
                if (!err) {
                    this.sessionToken = data.token;
                    callback(null, data.token);
                } else {
                    callback(err, null);
                }
            });
        }

        refreshNetwork() {
            // Get WiFi clients
            this.updateClientList();
            // Get AP status
            this.updateAPStatus();
            // Get network traffic
            this.updateNetworkTraffic();
        }

        updateClientList() {
            this.get('/rest/smartapi/apis/smart/v2/ubnt/network/clients', (err, data) => {
                if (!err) {
                    this.clients = data.clients || [];
                    this.status({
                        fill: 'blue',
                        shape: 'dot',
                        text: `${this.clients.length} clients`
                    });
                    this.send({ payload: this.clients });
                }
            });
        }

        getClientDetails(clientId, callback) {
            this.get(`/rest/smartapi/apis/smart/v2/ubnt/network/clients/${clientId}`, callback);
        }

        getAPList() {
            this.get('/rest/proprietory/rest/cap/wlan', (err, data) => {
                if (!err) {
                    this.accessPoints = data.accessPoints || [];
                    this.status({
                        fill: 'green',
                        shape: 'dot',
                        text: `${this.accessPoints.length} APs`
                    });
                    this.send({ payload: this.accessPoints });
                }
            });
        }

        getAPDetails(apId, callback) {
            this.get(`/rest/proprietory/rest/cap/wlan/${apId}`, callback);
        }

        updateNetworkTraffic() {
            this.get('/rest/smartapi/apis/smart/v2/ubnt/network/traffic', (err, data) => {
                if (!err) {
                    const traffic = data.traffic || {};
                    this.networkTraffic.upload = traffic.up || 0;
                    this.networkTraffic.download = traffic.down || 0;
                    this.networkTraffic.total = (traffic.up || 0) + (traffic.down || 0);
                    this.send({ payload: this.networkTraffic });
                }
            });
        }

        getNetworkStats(callback) {
            this.get('/rest/smartapi/apis/smart/v2/ubnt/network/stats', callback);
        }

        getDeviceList() {
            this.get('/rest/smartapi/apis/smart/v2/ubnt/devices', (err, data) => {
                if (!err) {
                    this.send({ payload: data.devices || [] });
                }
            });
        }

        sendRequest(method, url, data, callback) {
            // Simulated HTTP request
            // In production, use node-red-contrib-unifi or custom HTTP node
            setTimeout(() => {
                const response = {
                    success: true,
                    data: data || {},
                    message: 'UniFi request completed'
                };
                callback(null, response);
            }, 100);
        }

        get(path, callback) {
            this.sendRequest('GET', `${this.baseUrl}${path}`, null, callback);
        }

        post(path, data, callback) {
            this.sendRequest('POST', `${this.baseUrl}${path}`, data, callback);
        }

        put(path, data, callback) {
            this.sendRequest('PUT', `${this.baseUrl}${path}`, data, callback);
        }

        delete(path, callback) {
            this.sendRequest('DELETE', `${this.baseUrl}${path}`, null, callback);
        }
    }

    RED.nodes.registerType("unifi-monitor", UniFiNode);

    return UniFiNode;
};
