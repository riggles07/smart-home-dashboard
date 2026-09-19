/**
 * Hubitat Integration Flow
 * Smart home device controls and automation
 *
 * Device commands go through the hub's Maker API:
 *   GET /apps/api/[app_id]/devices/[device_id]/[command][/[value]]?access_token=[token]
 * Credentials come from the node config (url/appId/accessToken) -- never hard-coded.
 *
 * Every command calls back with `(err, result)` where `result` is a structured
 * object ({ok, code, deviceId, command, value, statusCode, message, error}),
 * so an unreachable hub degrades gracefully instead of throwing.
 */
module.exports = function (RED) {
    "use strict";

    // Device commands exposed to the dashboard, keyed by Maker API command name.
    const SUPPORTED_COMMANDS = {
        on: { capability: "switch", args: [], required: [], description: "Turn a switch or dimmer on." },
        off: { capability: "switch", args: [], required: [], description: "Turn a switch or dimmer off." },
        toggle: { capability: "switch", args: [], required: [], description: "Toggle a switch or dimmer." },
        refresh: { capability: "common", args: [], required: [], description: "Ask the device to re-read its state." },
        setSwitch: { capability: "switch", args: ["state"], required: ["state"], description: "Set switch state explicitly ('on'/'off')." },
        setLevel: { capability: "dimmer", args: ["level", "duration"], required: ["level"], description: "Set dimmer level 0-100%, optional ramp duration in seconds." },
        setHue: { capability: "color-bulb", args: ["hue"], required: ["hue"], description: "Set colour hue 0-100." },
        setSaturation: { capability: "color-bulb", args: ["saturation"], required: ["saturation"], description: "Set colour saturation 0-100." },
        setColor: { capability: "color-bulb", args: ["hue", "saturation", "level"], required: ["hue", "saturation"], description: "Set HSB colour (hue, saturation, optional level)." },
        setColorHex: { capability: "color-bulb", args: ["hex"], required: ["hex"], description: "Set colour from an RGB hex string, e.g. 'FF0400'." },
        setColorTemperature: { capability: "color-bulb", args: ["temperature", "level"], required: ["temperature"], description: "Set colour temperature in Kelvin, optional level 0-100." }
    };

    const NUMERIC_RANGES = {
        level: [0, 100],
        hue: [0, 100],
        saturation: [0, 100],
        duration: [0, 3600],
        temperature: [1000, 10000]
    };

    class HubitatNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.timeout = this.config.timeout || 10000;
            this.devices = [];
            this.activeAutomations = [];
            // Resolve credentials up front (same as the Python mirror), so a
            // command sent before init() fails with missing_configuration
            // rather than a null dereference.
            this.baseUrl = this.config.url || process.env.HUBITAT_URL || 'http://hubitat.local:8080';
            this.apiKey = this.config.apiKey || process.env.HUBITAT_API_KEY || null;
            this.appId = this.config.appId || process.env.HUBITAT_APP_ID || null;
            this.accessToken = this.config.accessToken || this.config.token ||
                process.env.HUBITAT_ACCESS_TOKEN || this.apiKey || null;
        }

        init() {
            // Re-read the connection settings, then wire up subscriptions.
            this.baseUrl = this.config.url || process.env.HUBITAT_URL || 'http://hubitat.local:8080';
            this.apiKey = this.config.apiKey || process.env.HUBITAT_API_KEY || null;
            this.appId = this.config.appId || process.env.HUBITAT_APP_ID || null;
            this.accessToken = this.config.accessToken || this.config.token ||
                process.env.HUBITAT_ACCESS_TOKEN || this.apiKey || null;

            // Subscribe to device events
            this.on('subscribe', (event) => {
                if (event.type === 'device-state') {
                    this.updateDeviceState(event.deviceId);
                }
            });

            // Set up auto-refresh for device states
            this.setInterval(this.refreshDevices, this.config.refresh || 60000);
        }

        // -- Maker API ---------------------------------------------------------

        supportedCommands() {
            return JSON.parse(JSON.stringify(SUPPORTED_COMMANDS));
        }

        makerApiUrl(path, value) {
            if (!this.baseUrl) { throw new Error('Hubitat base URL is not configured'); }
            if (!this.appId) { throw new Error('Hubitat Maker API app id is not configured'); }
            if (!this.accessToken) { throw new Error('Hubitat Maker API access token is not configured'); }
            const segments = String(path).replace(/^\/+|\/+$/g, '').split('/')
                .filter((s) => s !== '').map(encodeURIComponent);
            if (value !== undefined && value !== null) { segments.push(encodeURIComponent(value)); }
            return `${this.baseUrl.replace(/\/+$/, '')}/apps/api/${encodeURIComponent(this.appId)}/${segments.join('/')}?access_token=${encodeURIComponent(this.accessToken)}`;
        }

        fail(code, message, extra) {
            const result = Object.assign({
                ok: false,
                code: code,
                deviceId: null,
                command: null,
                value: null,
                statusCode: null,
                message: message,
                error: message
            }, extra || {});
            if (this.log) { this.log(`Hubitat ${result.command || '-'} failed (${code}): ${message}`); }
            return result;
        }

        normalizeArguments(command, args) {
            const spec = SUPPORTED_COMMANDS[command];
            const names = spec.args;
            const required = spec.required;
            let values = Array.prototype.slice.call(args || []);

            if (values.length === 1 && values[0] && typeof values[0] === 'object' && !Array.isArray(values[0])) {
                const mapping = values[0];
                const unexpected = Object.keys(mapping).filter((k) => names.indexOf(k) === -1);
                if (unexpected.length) {
                    return { error: `${command} received unsupported argument(s): ${unexpected.join(', ')}` };
                }
                const missing = required.filter((name) => mapping[name] === undefined || mapping[name] === null);
                if (missing.length) { return { error: `${command} requires argument(s): ${missing.join(', ')}` }; }
                values = names.filter((name) => mapping[name] !== undefined && mapping[name] !== null)
                    .map((name) => mapping[name]);
            }

            if (values.length > names.length) {
                return { error: `${command} takes at most ${names.length} argument(s), got ${values.length}` };
            }
            if (values.length < required.length) {
                return { error: `${command} requires argument(s): ${required.join(', ')}` };
            }

            const normalized = [];
            for (let i = 0; i < values.length; i++) {
                const name = names[i];
                let value = values[i];
                if (value === undefined || value === null) {
                    if (required.indexOf(name) !== -1) {
                        return { error: `${command} requires argument(s): ${required.join(', ')}` };
                    }
                    continue;
                }
                if (name === 'state') {
                    value = String(value).trim().toLowerCase();
                    if (value !== 'on' && value !== 'off') {
                        return { error: `${command} argument 'state' must be 'on' or 'off'` };
                    }
                    normalized.push(value);
                    continue;
                }
                if (name === 'hex') {
                    value = String(value).trim().replace(/^#/, '');
                    if (!/^[0-9A-Fa-f]{6}$/.test(value)) {
                        return { error: `${command} argument 'hex' must be a 6-digit hex colour` };
                    }
                    normalized.push(value.toUpperCase());
                    continue;
                }
                const number = Number(value);
                if (value === '' || isNaN(number)) {
                    return { error: `${command} argument '${name}' must be a number` };
                }
                const range = NUMERIC_RANGES[name];
                if (range && (number < range[0] || number > range[1])) {
                    return { error: `${command} argument '${name}' must be between ${range[0]} and ${range[1]}` };
                }
                normalized.push(number);
            }
            return { values: normalized };
        }

        serializeCommandValue(command, values) {
            if (!values || !values.length) { return null; }
            if (command === 'setColor') {
                const mapping = {};
                ['hue', 'saturation', 'level'].forEach((name, index) => {
                    if (values[index] !== undefined) { mapping[name] = values[index]; }
                });
                return JSON.stringify(mapping);
            }
            if (command === 'setColorHex') { return JSON.stringify({ hex: values[0] }); }
            return values.join(',');
        }

        /**
         * Run one Maker API request and map every failure mode onto a
         * structured result. `meta` carries {deviceId, command, value} for the
         * result object. Never throws.
         */
        makerApiRequest(url, meta, callback) {
            const info = meta || {};
            const done = (result) => { if (callback) { callback(result.ok ? null : result.error, result); } return result; };
            try {
                return this.sendRequest('GET', url, null, (err, response) => {
                    const status = response && response.statusCode;
                    if (err) {
                        const text = String((err && err.message) || err);
                        const timedOut = err.code === 'ETIMEDOUT' || err.code === 'ESOCKETTIMEDOUT' || /timeout/i.test(text);
                        done(this.fail(timedOut ? 'timeout' : 'connection_error',
                            timedOut ? 'Hubitat hub did not respond in time' : 'Hubitat hub is unreachable',
                            Object.assign({}, info, { error: text })));
                        return;
                    }
                    if (typeof status === 'number' && (status < 200 || status >= 300)) {
                        const payload = response && (response.body !== undefined ? response.body : response.data);
                        done(this.fail('http_error', `Hubitat returned HTTP ${status}`,
                            Object.assign({}, info, { statusCode: status, payload: payload })));
                        return;
                    }
                    const payload = response && (response.body !== undefined ? response.body : response.data);
                    if (this.isUnknownDevice(payload)) {
                        done(this.fail('unknown_device',
                            `Hubitat does not expose device '${info.deviceId}' through this Maker API app`,
                            Object.assign({}, info, { statusCode: status, payload: payload })));
                        return;
                    }
                    done(Object.assign({
                        ok: true,
                        code: 'ok',
                        statusCode: typeof status === 'number' ? status : null,
                        message: 'ok',
                        error: null,
                        payload: payload
                    }, info));
                });
            } catch (error) {
                // A transport that throws synchronously (bad config, DNS failure
                // in a misbehaving client) must not take the flow down.
                const text = String((error && error.message) || error);
                return done(this.fail('connection_error', 'Hubitat hub is unreachable',
                    Object.assign({}, info, { error: text })));
            }
        }

        isUnknownDevice(payload) {
            if (!payload || typeof payload !== 'object' || typeof payload.error !== 'string') { return false; }
            return /device/i.test(payload.error) && /(not found|unknown|invalid|missing)/i.test(payload.error);
        }

        sendDeviceCommand(deviceId, command, ...args) {
            let callback = null;
            if (typeof args[args.length - 1] === 'function') { callback = args.pop(); }
            // Trailing `undefined` means "optional argument omitted", not a value.
            while (args.length && args[args.length - 1] === undefined) { args.pop(); }

            const done = (result) => { if (callback) { callback(result.ok ? null : result.error, result); } return result; };

            if (deviceId === undefined || deviceId === null || String(deviceId).trim() === '') {
                return done(this.fail('invalid_device_id', `device id must be a non-empty string or integer`, { deviceId: deviceId, command: command }));
            }
            if (typeof command !== 'string' || !SUPPORTED_COMMANDS[command]) {
                return done(this.fail('unknown_command', `unsupported device command '${command}'; supported: ${Object.keys(SUPPORTED_COMMANDS).sort().join(', ')}`, { deviceId: deviceId, command: command }));
            }

            const normalized = this.normalizeArguments(command, args);
            if (normalized.error) {
                return done(this.fail('invalid_argument', normalized.error, { deviceId: deviceId, command: command }));
            }
            const value = this.serializeCommandValue(command, normalized.values);

            let url;
            try {
                url = this.makerApiUrl(`devices/${deviceId}/${command}`, value);
            } catch (error) {
                return done(this.fail('missing_configuration', error.message, { deviceId: deviceId, command: command, value: value }));
            }

            return this.makerApiRequest(url, { deviceId: deviceId, command: command, value: value }, callback);
        }

        // Switch / dimmer / colour-bulb commands. Note `on` is the Node-RED
        // event emitter, so the power commands are named turnOn/turnOff.
        turnOn(deviceId, callback) { return this.sendDeviceCommand(deviceId, 'on', callback); }
        turnOff(deviceId, callback) { return this.sendDeviceCommand(deviceId, 'off', callback); }
        toggle(deviceId, callback) { return this.sendDeviceCommand(deviceId, 'toggle', callback); }
        setSwitch(deviceId, state, callback) { return this.sendDeviceCommand(deviceId, 'setSwitch', state, callback); }
        setLevel(deviceId, level, duration, callback) {
            if (typeof duration === 'function') { callback = duration; duration = undefined; }
            return duration === undefined
                ? this.sendDeviceCommand(deviceId, 'setLevel', level, callback)
                : this.sendDeviceCommand(deviceId, 'setLevel', level, duration, callback);
        }
        setColor(deviceId, hue, saturation, level, callback) {
            if (typeof level === 'function') { callback = level; level = undefined; }
            return level === undefined
                ? this.sendDeviceCommand(deviceId, 'setColor', hue, saturation, callback)
                : this.sendDeviceCommand(deviceId, 'setColor', hue, saturation, level, callback);
        }
        setHue(deviceId, hue, callback) { return this.sendDeviceCommand(deviceId, 'setHue', hue, callback); }
        setSaturation(deviceId, saturation, callback) { return this.sendDeviceCommand(deviceId, 'setSaturation', saturation, callback); }
        setColorTemperature(deviceId, temperature, level, callback) {
            if (typeof level === 'function') { callback = level; level = undefined; }
            return level === undefined
                ? this.sendDeviceCommand(deviceId, 'setColorTemperature', temperature, callback)
                : this.sendDeviceCommand(deviceId, 'setColorTemperature', temperature, level, callback);
        }
        setColorHex(deviceId, hex, callback) { return this.sendDeviceCommand(deviceId, 'setColorHex', hex, callback); }
        refreshDevice(deviceId, callback) { return this.sendDeviceCommand(deviceId, 'refresh', callback); }

        getDeviceCommands(deviceId, callback) {
            return this.makerApiRequest(this.makerApiUrl(`devices/${deviceId}/commands`),
                { deviceId: deviceId, command: 'commands' }, callback);
        }

        // -- dashboard control surface ------------------------------------------

        /**
         * Handle a dashboard control action: the single entry point the UI
         * (ui_switch / ui_slider / ui_colour_picker in the Devices view) calls.
         * Accepts {"deviceId","command","value"} or a Node-RED msg wrapping it
         * in `payload`, and publishes the result on this node's output.
         */
        controlDevice(msg, callback) {
            const done = (result) => {
                if (callback) { callback(result.ok ? null : result.error, result); }
                this.send({ payload: result, topic: `hubitat/device/${result.deviceId}/command` });
                return result;
            };
            if (!msg || typeof msg !== 'object') {
                return done(this.fail('invalid_payload', "control action must be an object with 'deviceId' and 'command'"));
            }
            const request = (msg.payload && typeof msg.payload === 'object') ? msg.payload : msg;
            const deviceId = request.deviceId !== undefined ? request.deviceId
                : (request.device_id !== undefined ? request.device_id : request.id);
            const command = request.command;
            let value = request.value !== undefined ? request.value : request.values;
            if (value === undefined && SUPPORTED_COMMANDS[command]) {
                const inline = SUPPORTED_COMMANDS[command].args
                    .filter((name) => request[name] !== undefined && request[name] !== null)
                    .map((name) => request[name]);
                if (inline.length) { value = inline; }
            }

            const args = Array.isArray(value) ? value.slice() : (value === undefined || value === null ? [] : [value]);
            return this.sendDeviceCommand(deviceId, command, ...args, done);
        }

        // Alias so a hubitat-control node's input can be wired straight here.
        handleControl(msg, callback) { return this.controlDevice(msg, callback); }

        // -- existing API surface -----------------------------------------------

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
