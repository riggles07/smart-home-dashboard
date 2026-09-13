/**
 * Integration Functions
 * API integration logic and utilities
 */
module.exports = function (RED) {
    "use strict";

    // Hubitat API integration
    const hubitatAPI = {
        BASE_URL: null,
        API_KEY: null,

        init(config) {
            this.BASE_URL = config.url || 'http://hubitat.local:8080';
            this.API_KEY = config.apiKey;
        },

        async getStatus() {
            try {
                const response = await fetch(`${this.BASE_URL}/api/v1/status`, {
                    headers: {
                        'Authorization': `Bearer ${this.API_KEY}`,
                        'Accept': 'application/json'
                    }
                });
                return await response.json();
            } catch (error) {
                throw new Error(`Hubitat status error: ${error.message}`);
            }
        },

        async getDevices() {
            try {
                const response = await fetch(`${this.BASE_URL}/api/v1/devices`, {
                    headers: {
                        'Authorization': `Bearer ${this.API_KEY}`,
                        'Accept': 'application/json'
                    }
                });
                return await response.json();
            } catch (error) {
                throw new Error(`Hubitat devices error: ${error.message}`);
            }
        },

        async getDevice(deviceId) {
            try {
                const response = await fetch(`${this.BASE_URL}/api/v1/devices/${deviceId}`, {
                    headers: {
                        'Authorization': `Bearer ${this.API_KEY}`,
                        'Accept': 'application/json'
                    }
                });
                return await response.json();
            } catch (error) {
                throw new Error(`Hubitat device error: ${error.message}`);
            }
        },

        async updateDevice(deviceId, data) {
            try {
                const response = await fetch(`${this.BASE_URL}/api/v1/devices/${deviceId}`, {
                    method: 'PUT',
                    headers: {
                        'Authorization': `Bearer ${this.API_KEY}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                return await response.json();
            } catch (error) {
                throw new Error(`Hubitat update error: ${error.message}`);
            }
        },

        async triggerAutomation(automationId) {
            try {
                const response = await fetch(`${this.BASE_URL}/api/v1/automations/${automationId}/trigger`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.API_KEY}`,
                        'Accept': 'application/json'
                    }
                });
                return await response.json();
            } catch (error) {
                throw new Error(`Hubitat automation trigger error: ${error.message}`);
            }
        }
    };

    // UniFi API integration
    const unifiAPI = {
        BASE_URL: null,
        USERNAME: null,
        PASSWORD: null,
        SESSION_TOKEN: null,

        init(config) {
            this.BASE_URL = config.url || 'https://unifi.local:8443';
            this.USERNAME = config.username;
            this.PASSWORD = config.password;
        },

        async authenticate() {
            try {
                const response = await fetch(`${this.BASE_URL}/api/login`, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: this.USERNAME,
                        password: this.PASSWORD
                    })
                });
                const data = await response.json();
                this.SESSION_TOKEN = data.token;
                return data;
            } catch (error) {
                throw new Error(`UniFi authentication error: ${error.message}`);
            }
        },

        async get(url) {
            try {
                const response = await fetch(`${this.BASE_URL}${url}`, {
                    headers: {
                        'Authorization': `Bearer ${this.SESSION_TOKEN}`,
                        'Content-Type': 'application/json'
                    }
                });
                return await response.json();
            } catch (error) {
                throw new Error(`UniFi API error: ${error.message}`);
            }
        },

        async post(url, data) {
            try {
                const response = await fetch(`${this.BASE_URL}${url}`, {
                    method: 'POST',
                    headers: {
                        'Authorization': `Bearer ${this.SESSION_TOKEN}`,
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(data)
                });
                return await response.json();
            } catch (error) {
                throw new Error(`UniFi API error: ${error.message}`);
            }
        },

        async getClients() {
            return this.get('/rest/smartapi/apis/smart/v2/ubnt/network/clients');
        },

        async getAccessPoints() {
            return this.get('/rest/proprietory/rest/cap/wlan');
        },

        async getNetworkTraffic() {
            return this.get('/rest/smartapi/apis/smart/v2/ubnt/network/traffic');
        }
    };

    // Node-RED HTTP integration helpers
    const httpHelper = {
        request: (options, callback) => {
            // Node-RED http request node wrapper
            const request = new RED.httpIn();
            request[options.method.toLowerCase()](options.url, (err, res) => {
                if (err) {
                    return callback(err);
                }
                res.on('data', callback);
            });
        },

        get: (url, callback) => httpHelper.request({ url: url, method: 'GET' }, callback),
        post: (url, data, callback) => httpHelper.request({ url: url, method: 'POST', body: data }, callback),
        put: (url, data, callback) => httpHelper.request({ url: url, method: 'PUT', body: data }, callback),
        delete: (url, callback) => httpHelper.request({ url: url, method: 'DELETE' }, callback)
    };

    // Utility functions
    const utils = {
        formatDate: (date) => {
            if (!date) return '';
            return new Date(date).toISOString();
        },

        parseJSON: (str) => {
            try {
                return JSON.parse(str);
            } catch (error) {
                return null;
            }
        },

        validateConfig: (config, requiredFields) => {
            const missing = requiredFields.filter(field => !config[field]);
            if (missing.length > 0) {
                throw new Error(`Missing required fields: ${missing.join(', ')}`);
            }
            return true;
        },

        debounce: (func, wait) => {
            let timeout;
            return function executedFunction(...args) {
                const later = () => {
                    clearTimeout(timeout);
                    func(...args);
                };
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            };
        },

        throttle: (func, limit) => {
            let inThrottle;
            return function(...args) {
                if (!inThrottle) {
                    func.apply(this, args);
                    inThrottle = true;
                    setTimeout(() => inThrottle = false, limit);
                }
            };
        }
    };

    return {
        hubitatAPI,
        unifiAPI,
        httpHelper,
        utils
    };
};
