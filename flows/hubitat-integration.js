/**
 * Hubitat Integration Flow
 * Smart home device controls and automation
 *
 * Automation triggers use a Rule Machine *endpoint trigger* -- Hubitat has no
 * /api/v1/automations resource. A rule with a "Local End Point" (or "Cloud End
 * Point") trigger event exposes:
 *
 *   GET|POST http://<hub>/apps/api/<appId>/trigger/getRuleList?access_token=<token>
 *   GET|POST http://<hub>/apps/api/<appId>/trigger/<action>=<rule ids>?access_token=<token>
 *
 * where <action> is a Rule Machine action (runRuleAct / stopRuleAct / ...).
 * See https://docs2.hubitat.com/en/apps/rule-machine
 */
module.exports = function (RED) {
    "use strict";

    const DEFAULT_BASE_URL = 'http://hubitat.local:8080';
    const DEFAULT_TIMEOUT = 10000;
    const DEFAULT_TRIGGER_ACTION = 'runRuleAct';
    const AUTOMATION_TOPIC = 'hubitat/automations';
    const AUTOMATION_RESULT_TOPIC = 'hubitat/automation/result';

    /** Mask an access token before it reaches a log line or a dashboard event. */
    function redactUrl(url) {
        if (typeof url !== 'string') {
            return url;
        }
        return url.replace(/([?&](?:access_token|token|apiKey)=)[^&#]*/gi, '$1***');
    }

    class HubitatNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.apiKey = null;
            this.baseUrl = null;
            this.appId = null;
            this.accessToken = null;
            this.timeout = this.config.timeout || DEFAULT_TIMEOUT;
            this.devices = [];
            this.activeAutomations = [];
            this.automations = [];
            this.automationsResolved = false;
            this.resolveAutomations = this.config.resolveAutomations !== false;
            this.triggerMethod = (this.config.triggerMethod || 'POST').toUpperCase();
        }

        init() {
            // Initialize API connection
            this.baseUrl = this.config.url || DEFAULT_BASE_URL;
            this.apiKey = this.config.apiKey;
            // Rule Machine endpoint-trigger credentials (automation triggers).
            this.appId = this.config.appId || this.config.automationAppId;
            this.accessToken = this.config.accessToken || this.config.token || this.config.apiKey;

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

        /**
         * List the automations (Rule Machine rules) the dashboard can trigger.
         * Results are cached; pass { refresh: true } to force a re-fetch.
         */
        getAutomations(options, callback) {
            if (typeof options === 'function') {
                callback = options;
                options = {};
            }
            const opts = options || {};

            if (!opts.refresh && this.automationsResolved) {
                this.publishAutomations(this.automations, callback);
                return;
            }
            if (!this.automationConfigured()) {
                // No credentials yet: keep the legacy simulated behaviour.
                this.sendRequest('GET', `${this.baseUrl}/api/v1/automations`, null, callback);
                return;
            }

            const url = this.automationUrl({ ruleList: true });
            this.automationRequest('GET', url, {}, (err, result) => {
                // A failed request still arrives as `result` (not `err`), so
                // both must be checked before the payload is parsed -- otherwise
                // a 401 body like {"error": "Unauthorized"} is mistaken for a
                // rule list and an unreachable hub is reported as malformed.
                if (err || !result || result.ok === false) {
                    const failure = result || HubitatNode.failure(
                        'transport_error', String(err), {}
                    );
                    this.publishResult(failure);
                    if (callback) { callback(failure.error, failure); }
                    return;
                }
                const parsed = HubitatNode.parseAutomationList(result.payload);
                if (parsed === null) {
                    const failure = HubitatNode.failure(
                        'malformed_response',
                        'hub returned an unparseable automation list',
                        { url: redactUrl(url), statusCode: result.statusCode }
                    );
                    this.publishResult(failure);
                    if (callback) { callback(failure.error, failure); }
                    return;
                }
                this.automations = parsed;
                this.automationsResolved = true;
                this.log(`Hubitat automation list refreshed: ${parsed.length} rule(s)`);
                this.publishAutomations(parsed, callback);
            });
        }

        /**
         * Trigger an automation (Rule Machine rule) over an endpoint trigger.
         *
         * @param {string} automationId Rule app id, or a name from getAutomations().
         * @param {function} callback   Optional (err, result) callback.
         * @param {object} options      { action, value, method }.
         */
        triggerAutomation(automationId, callback, options) {
            if (typeof callback === 'object' && callback !== null) {
                options = callback;
                callback = null;
            }
            const opts = options || {};

            if (automationId === undefined || automationId === null || automationId === '') {
                const failure = HubitatNode.failure(
                    'unknown_automation', 'automation id is required', {}
                );
                this.publishResult(failure);
                if (callback) { callback(failure.error, failure); }
                return failure;
            }
            if (!this.automationConfigured()) {
                // Legacy simulated path (parity with the original flow).
                this.sendRequest(
                    'POST',
                    `${this.baseUrl}/api/v1/automations/${automationId}/trigger`,
                    null,
                    callback
                );
                return;
            }

            this.resolveAutomation(automationId, (resolveErr, entry) => {
                if (resolveErr) {
                    this.publishResult(resolveErr);
                    if (callback) { callback(resolveErr.error, resolveErr); }
                    return;
                }
                if (entry === null) {
                    const failure = HubitatNode.failure(
                        'unknown_automation',
                        `unknown automation id ${JSON.stringify(automationId)}`,
                        { automationId }
                    );
                    this.publishResult(failure);
                    if (callback) { callback(failure.error, failure); }
                    return;
                }

                const url = this.automationUrl({
                    automationId: entry.id,
                    action: opts.value !== undefined ? null : (opts.action || DEFAULT_TRIGGER_ACTION),
                    value: opts.value
                });
                const method = (opts.method || this.triggerMethod).toUpperCase();
                this.automationRequest(method, url, {
                    automationId: entry.id,
                    automationName: entry.name,
                    action: opts.value !== undefined ? null : (opts.action || DEFAULT_TRIGGER_ACTION)
                }, (err, result) => {
                    this.publishResult(result);
                    if (callback) { callback(err, result); }
                });
            });
        }

        // -- automation helpers -------------------------------------------------

        /** Dashboard entry point: msg.payload = { automationId, action, value }. */
        handleAutomationTrigger(msg, callback) {
            const payload = (msg && msg.payload) || msg || {};
            const data = typeof payload === 'object' ? payload : { automationId: payload };
            return this.triggerAutomation(
                data.automationId !== undefined ? data.automationId : data.automation_id,
                callback,
                { action: data.action, value: data.value }
            );
        }

        /**
         * Dashboard entry point for the automation picker.
         * msg.payload = { refresh: true } forces a re-fetch.
         */
        handleAutomationList(msg, callback) {
            const payload = (msg && msg.payload) || msg || {};
            const refresh = Boolean(payload && typeof payload === 'object' && payload.refresh);
            return this.getAutomations({ refresh: refresh }, callback);
        }

        automationConfigured() {
            return Boolean(this.baseUrl && this.appId && this.accessToken);
        }

        automationUrl(opts) {
            if (!this.baseUrl) { throw new Error('Hubitat base URL is not configured'); }
            if (!this.appId) { throw new Error('Hubitat automation app id (appId) is not configured'); }
            if (!this.accessToken) { throw new Error('Hubitat access token is not configured'); }
            const opts2 = opts || {};
            const base = `${this.baseUrl.replace(/\/+$/, '')}/apps/api/`
                + `${encodeURIComponent(this.appId)}/trigger`;
            let path;
            if (opts2.ruleList) {
                path = `${base}/getRuleList`;
            } else if (opts2.value !== undefined && opts2.value !== null) {
                path = `${base}/${encodeURIComponent(opts2.value)}`;
            } else {
                const action = opts2.action || DEFAULT_TRIGGER_ACTION;
                path = `${base}/${encodeURIComponent(action)}=${encodeURIComponent(opts2.automationId)}`;
            }
            return `${path}?access_token=${encodeURIComponent(this.accessToken)}`;
        }

        resolveAutomation(automationId, done) {
            const wanted = String(automationId);
            const find = () => this.automations.find(
                (entry) => entry.id === wanted || entry.name === wanted
            );

            if (this.automationsResolved) {
                const found = find();
                if (found) { done(null, found); return; }
                done(null, this.resolveAutomations ? null : { id: wanted, name: null });
                return;
            }
            this.getAutomations((err) => {
                if (err) { done(err, null); return; }
                const found = find();
                if (found) { done(null, found); return; }
                done(null, this.resolveAutomations ? null : { id: wanted, name: null });
            });
        }

        automationRequest(method, url, context, done) {
            this.log(`Hubitat automation ${method} ${redactUrl(url)}`);
            this.httpRequest({
                method: method,
                url: url,
                timeout: this.timeout,
                headers: { Accept: 'application/json' }
            }, (err, res, body) => {
                if (err) {
                    done(null, HubitatNode.failure(
                        'hub_unreachable', 'Hubitat hub is unreachable',
                        Object.assign({ error: String(err) }, context)
                    ));
                    return;
                }
                const status = res && res.statusCode;
                let payload = null;
                try {
                    payload = body ? JSON.parse(body) : null;
                } catch (parseErr) {
                    payload = null;
                }
                if (status >= 400) {
                    let code = 'http_error';
                    let message = `Hubitat returned HTTP ${status}`;
                    if (status === 401 || status === 403) {
                        code = 'auth_failure';
                        message = `Hubitat rejected the request (HTTP ${status}); check the app id and access token`;
                    } else if (status === 404) {
                        message = 'Hubitat automation endpoint not found (HTTP 404); the app id has no endpoint trigger configured';
                    }
                    done(null, HubitatNode.failure(code, message, Object.assign({
                        statusCode: status, payload: payload, url: redactUrl(url)
                    }, context)));
                    return;
                }
                const result = Object.assign({
                    ok: true,
                    code: 'ok',
                    error: null,
                    automations: null,
                    automationId: null,
                    automationName: null,
                    action: null,
                    method: method,
                    url: redactUrl(url),
                    statusCode: status,
                    message: 'automation triggered',
                    payload: payload
                }, context);
                done(null, result);
            });
        }

        publishAutomations(automations, callback) {
            const result = {
                ok: true,
                code: 'ok',
                error: null,
                automations: automations,
                automationId: null,
                automationName: null,
                action: null,
                method: 'GET',
                url: null,
                statusCode: null,
                message: `${automations.length} automation(s) available`,
                payload: null
            };
            this.send({ payload: result, topic: AUTOMATION_TOPIC });
            if (callback) { callback(null, result); }
            return result;
        }

        publishResult(result) {
            if (!result) { return result; }
            const topic = result.automationId
                ? `${AUTOMATION_RESULT_TOPIC}/${result.automationId}`
                : AUTOMATION_RESULT_TOPIC;
            if (result.ok) {
                this.log(`Hubitat automation ok: ${result.message}`);
            } else {
                this.warn(`Hubitat automation failed (${result.code}): ${result.message}`);
            }
            this.send({ payload: result, topic: topic });
            return result;
        }

        /** Normalise getRuleList output: {"<id>": "<name>"} -> [{id, name}]. */
        static parseAutomationList(payload) {
            if (payload === null || payload === undefined) { return null; }
            let body = payload;
            if (!Array.isArray(body) && typeof body === 'object') {
                ['rules', 'automations', 'result', 'data'].forEach((key) => {
                    if (body[key] && typeof body[key] === 'object') { body = body[key]; }
                });
            }
            let entries;
            if (Array.isArray(body)) {
                entries = body;
            } else if (body && typeof body === 'object') {
                entries = Object.keys(body).map((key) => ({ id: key, name: body[key] }));
            } else {
                return null;
            }
            return entries.map((entry) => {
                if (entry && typeof entry === 'object') {
                    const id = entry.id !== undefined ? entry.id : entry.ruleId;
                    const name = entry.name !== undefined ? entry.name : entry.label;
                    if (id === undefined || id === null || id === '') { return null; }
                    return { id: String(id), name: name !== undefined && name !== null ? String(name) : String(id) };
                }
                if (typeof entry === 'string' && entry) { return { id: entry, name: entry }; }
                return null;
            }).filter((entry) => entry !== null);
        }

        /** Build a structured failure result (mirrors the Python AutomationResult). */
        static failure(code, message, extra) {
            return Object.assign({
                ok: false,
                code: code,
                error: message,
                automations: null,
                automationId: null,
                automationName: null,
                action: null,
                method: null,
                url: null,
                statusCode: null,
                message: message,
                payload: null
            }, extra || {});
        }

        // Legacy parity shims: Hubitat has no /api/v1/automations resource, so
        // these only exercise the simulated transport. Rule enable/disable is
        // done on the hub (Rule Machine), not over Maker API.
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
