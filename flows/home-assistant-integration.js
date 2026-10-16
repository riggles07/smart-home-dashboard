/**
 * Home Assistant Integration Flow
 * Smart home device controls and real-time state sync
 *
 * Home Assistant is the primary smart home orchestrator (Phase 7 migration,
 * replacing the Hubitat integration). Two transports are used, per the
 * requirements (docs/REQUIREMENTS_V2.md):
 *
 *   Control path (Dashboard UI -> HA):
 *     REST service calls -- POST /api/services/<domain>/<service>
 *     with "Authorization: Bearer <LLAT>". REST is preferred for one-off
 *     commands because every call is self-contained.
 *
 *   State path (HA -> Dashboard UI):
 *     The WebSocket API -- ws(s)://<host>/api/websocket. One connection
 *     authenticates, then `get_states` snapshots every entity and
 *     `subscribe_events` (state_changed) pushes updates in real time,
 *     giving bidirectional sync: a UI action fires a service call, HA
 *     emits state_changed, and the dashboard re-syncs the widget.
 *
 * Credentials come from the node config or the HA_URL / HA_TOKEN
 * (Long-Lived Access Token) / HA_ENTITY_ID environment variables -- never
 * hard-coded, never logged.
 *
 * Legacy Hubitat device commands (on/off/toggle/setLevel/setColor/...) are
 * mapped onto HA service calls by mapHubitatCommand(), so dashboard widgets
 * written against the Hubitat Maker API keep working against HA entities.
 *
 * Every command calls back with `(err, result)` where `result` is a
 * structured object ({ok, code, entityId, domain, service, serviceData,
 * statusCode, message, error}), so an unreachable hub degrades gracefully
 * instead of throwing.
 */
module.exports = function (RED) {
    "use strict";

    // Service calls the dashboard can make, keyed "<domain>.<service>".
    // `data` lists the service_data fields the UI may set.
    const SUPPORTED_SERVICES = {
        "light.turn_on": { domain: "light", service: "turn_on", data: ["brightness_pct", "brightness", "hs_color", "kelvin", "rgb_color"], description: "Turn a light on, optionally setting brightness/colour." },
        "light.turn_off": { domain: "light", service: "turn_off", data: [], description: "Turn a light off." },
        "light.toggle": { domain: "light", service: "toggle", data: ["brightness_pct", "hs_color", "kelvin"], description: "Toggle a light." },
        "switch.turn_on": { domain: "switch", service: "turn_on", data: [], description: "Turn a switch on." },
        "switch.turn_off": { domain: "switch", service: "turn_off", data: [], description: "Turn a switch off." },
        "switch.toggle": { domain: "switch", service: "toggle", data: [], description: "Toggle a switch." },
        "homeassistant.update_entity": { domain: "homeassistant", service: "update_entity", data: [], description: "Ask HA to re-read an entity's state (legacy 'refresh')." },
        "homeassistant.turn_off": { domain: "homeassistant", service: "turn_off", data: [], description: "Turn off any controllable entity." },
        "homeassistant.turn_on": { domain: "homeassistant", service: "turn_on", data: [], description: "Turn on any controllable entity." }
    };

    // Numeric ranges the dashboard enforces before calling HA.
    const NUMERIC_RANGES = {
        brightness_pct: [0, 100],
        brightness: [0, 255],
        kelvin: [1000, 10000],
        hue: [0, 100],          // Hubitat hue scale -- converted to 0-360 below
        saturation: [0, 100],
        level: [0, 100]
    };

    // Legacy Hubitat Maker API command -> HA service. The domain comes from
    // the target entity (light.* / switch.*), so one table covers lights,
    // switches and dimmers. Sensor entities are read-only and have no entry,
    // which is how read-only devices are rejected.
    const HUBITAT_COMMAND_MAP = {
        on: { service: "turn_on", data: [] },
        off: { service: "turn_off", data: [] },
        toggle: { service: "toggle", data: [] },
        setSwitch: { service: null, data: ["state"] },        // turn_on/turn_off chosen from `state`
        setLevel: { service: "turn_on", data: ["brightness_pct"] },
        setHue: { service: "turn_on", data: ["hs_color"] },  // partial colour: full saturation assumed
        setSaturation: { service: "turn_on", data: ["hs_color"] },
        setColor: { service: "turn_on", data: ["hs_color", "brightness_pct"] },
        setColorTemperature: { service: "turn_on", data: ["kelvin"] },
        setColorHex: { service: "turn_on", data: ["rgb_color"] },
        refresh: { service: "update_entity", data: [] }
    };

    // Hubitat capability family -> HA entity domain, used when a legacy
    // widget addresses a device by capability rather than by entity id.
    const HUBITAT_CAPABILITY_DOMAINS = {
        switch: "switch",
        dimmer: "light",
        "color-bulb": "light",
        sensor: "sensor",
        common: "homeassistant"
    };

    // Entities that can never accept a service call.
    const READ_ONLY_DOMAINS = ["sensor", "binary_sensor", "input_datetime", "weather", "zone", "device_tracker"];

    // `entity_id` is the service TARGET (body root for REST, `target` for
    // the WS protocol) -- it is never valid inside service_data, so the
    // `data` allow-lists above never contain it.

    const WEBSOCKET_PATH = "/api/websocket";

    class HomeAssistantNode extends RED.Node {
        constructor(type, msg, config, node) {
            super(type, msg, config, node);
            this.config = config || {};
            this.timeout = this.config.timeout || 10000;
            this.states = {};            // entity_id -> current HA state object
            this.commandId = 0;          // WebSocket command id counter (per protocol)
            this.devices = [];
            this.activeAutomations = [];
            // Resolve credentials up front (same as the Python mirror), so a
            // command sent before init() fails with missing_configuration
            // rather than a null dereference.
            this.baseUrl = this.config.url || process.env.HA_URL || 'http://homeassistant.local:8123';
            this.token = this.config.token || process.env.HA_TOKEN || null;
            this.entityId = this.config.entityId || process.env.HA_ENTITY_ID || null;
        }

        init() {
            this.baseUrl = this.config.url || process.env.HA_URL || 'http://homeassistant.local:8123';
            this.token = this.config.token || process.env.HA_TOKEN || null;
            this.entityId = this.config.entityId || process.env.HA_ENTITY_ID || null;

            // HA -> dashboard: a device-state event refreshes the entity.
            this.on('subscribe', (event) => {
                if (event.type === 'device-state') {
                    this.updateEntityState(event.entityId);
                }
            });

            this.setInterval(this.refreshStates, this.config.refresh || 60000);
        }

        // -- URL / protocol helpers ------------------------------------------------
        //
        // The REST and WebSocket APIs share a base URL; only the scheme and
        // path differ (http -> ws for the socket).

        restUrl(path) {
            if (!this.baseUrl) { throw new Error('Home Assistant URL is not configured'); }
            if (!this.token) { throw new Error('Home Assistant token (HA_TOKEN, LLAT) is not configured'); }
            return `${this.baseUrl.replace(/\/+$/, '')}/api/${String(path).replace(/^\/+/, '')}`;
        }

        websocketUrl() {
            if (!this.baseUrl) { throw new Error('Home Assistant URL is not configured'); }
            const wsBase = this.baseUrl.replace(/\/+$/, '').replace(/^http/, 'ws');
            return `${wsBase}${WEBSOCKET_PATH}`;
        }

        nextCommandId() {
            this.commandId += 1;
            return this.commandId;
        }

        // WebSocket protocol messages (developers.home-assistant.io/docs/api/websocket).
        buildAuthMessage() {
            if (!this.token) { throw new Error('Home Assistant token (HA_TOKEN, LLAT) is not configured'); }
            return { type: 'auth', access_token: this.token };
        }

        buildGetStatesCommand() {
            return { id: this.nextCommandId(), type: 'get_states' };
        }

        buildSubscribeEventsCommand(eventType) {
            return { id: this.nextCommandId(), type: 'subscribe_events', event_type: eventType || 'state_changed' };
        }

        buildCallServiceCommand(domain, service, entityId, serviceData) {
            // Per the HA WebSocket protocol the `service` key is REQUIRED
            // (a frame without it is rejected with "required key not
            // provided @ data['service']"); the target goes in `target`.
            const command = {
                id: this.nextCommandId(),
                type: 'call_service',
                domain: domain,
                service: service,
                target: { entity_id: entityId }
            };
            if (serviceData && Object.keys(serviceData).length) {
                command.service_data = serviceData;
            }
            return command;
        }

        supportedServices() {
            return JSON.parse(JSON.stringify(SUPPORTED_SERVICES));
        }

        /**
         * Validate/normalise serviceData before it goes to HA, using the
         * declared NUMERIC_RANGES so an out-of-range brightness_pct is
         * rejected locally instead of surfacing as an opaque HA error.
         * Returns a normalised copy, or null when there is nothing to
         * validate. Throws on bad input (mirrors the Python mirror's
         * ValueError).
         */
        validateServiceData(domain, service, serviceData) {
            if (!serviceData) { return null; }
            if (typeof serviceData !== 'object' || Array.isArray(serviceData)) {
                throw new Error('service data must be a mapping of field names to values');
            }
            const spec = SUPPORTED_SERVICES[`${domain}.${service}`];
            const allowed = spec ? spec.data.slice() : [];
            const normalised = {};
            Object.keys(serviceData).forEach((key) => {
                const value = serviceData[key];
                if (key === 'entity_id') {
                    // The target entity is set by the caller; a second id in
                    // serviceData is at best redundant, at worst conflicting.
                    throw new Error("service data may not carry 'entity_id' -- pass it as the entityId argument");
                }
                if (allowed.length && allowed.indexOf(key) === -1) {
                    throw new Error(`service ${domain}.${service} does not accept '${key}'; accepted: ${allowed.join(', ')}`);
                }
                if (NUMERIC_RANGES[key]) {
                    const number = Number(value);
                    const range = NUMERIC_RANGES[key];
                    if (!isFinite(number) || number < range[0] || number > range[1]) {
                        throw new Error(`${key} must be a number between ${range[0]} and ${range[1]}`);
                    }
                    normalised[key] = Math.round(number);
                    return;
                }
                if (key === 'hs_color' || key === 'rgb_color') {
                    if (!Array.isArray(value) || !value.length) {
                        throw new Error(`${key} must be a list of numbers`);
                    }
                    normalised[key] = value.slice();
                    return;
                }
                normalised[key] = value;
            });
            return normalised;
        }

        // -- state normalisation -----------------------------------------------------

        /**
         * Normalise a HA state object into the shape dashboard widgets use.
         * Brightness (HA stores 0-255) is surfaced as a 0-100 percentage.
         */
        normalizeState(state) {
            if (!state || !state.entity_id) { return null; }
            const attrs = state.attributes || {};
            let brightnessPct = null;
            if (typeof attrs.brightness_pct === 'number') {
                brightnessPct = Math.round(attrs.brightness_pct);
            } else if (typeof attrs.brightness === 'number') {
                brightnessPct = Math.round((attrs.brightness / 255) * 100);
            }
            return {
                entityId: state.entity_id,
                domain: String(state.entity_id).split('.')[0],
                state: state.state,
                friendlyName: attrs.friendly_name || state.entity_id,
                isOn: state.state === 'on',
                brightnessPct: brightnessPct,
                lastChanged: state.last_changed || null,
                lastUpdated: state.last_updated || null
            };
        }

        /**
         * Fold one `state_changed` event into the local state cache and
         * publish the normalised entity on its state topic (HA -> UI half of
         * the bidirectional sync).
         */
        handleStateEvent(event) {
            const data = (event && event.data) || {};
            if (!data.entity_id || !data.new_state) { return null; }
            this.states[data.entity_id] = data.new_state;
            const normalized = this.normalizeState(data.new_state);
            if (normalized) {
                this.send({
                    payload: normalized,
                    topic: `ha/entity/${data.entity_id}/state`
                });
            }
            return normalized;
        }

        updateEntityState(entityId) {
            const state = this.states[entityId];
            if (state) {
                this.send({ payload: this.normalizeState(state), topic: `ha/entity/${entityId}/state` });
            }
            return state || null;
        }

        /**
         * Inbound WebSocket message dispatcher. Returns the outbound
         * protocol messages to send (auth / get_states / subscribe_events)
         * -- the caller just writes them to the socket.
         */
        handleServerMessage(message) {
            const out = [];
            if (!message || !message.type) { return out; }
            switch (message.type) {
                case 'auth_required':
                    out.push(this.buildAuthMessage());
                    break;
                case 'auth_ok':
                    // Snapshot every entity, then subscribe to live changes.
                    out.push(this.buildGetStatesCommand());
                    out.push(this.buildSubscribeEventsCommand('state_changed'));
                    break;
                case 'auth_invalid':
                    this.status && this.status({ fill: 'red', shape: 'ring', text: 'auth failed (bad HA_TOKEN?)' });
                    break;
                case 'result':
                    if (message.success && Array.isArray(message.result)) {
                        // get_states response: refresh the whole cache.
                        message.result.forEach((state) => {
                            if (state && state.entity_id) { this.states[state.entity_id] = state; }
                        });
                        this.send({ payload: Object.keys(this.states).length, topic: 'ha/state_count' });
                    } else if (message.success === false) {
                        // A command frame HA rejected. Dropping it silently
                        // would leave the dashboard believing the command
                        // succeeded.
                        const detail = (message.error && message.error.message) ? message.error.message : 'unknown error';
                        this.status && this.status({ fill: 'red', shape: 'ring', text: `command ${message.id} failed: ${detail}` });
                    }
                    break;
                case 'event':
                    this.handleStateEvent(message.event);
                    break;
                default:
                    break;
            }
            return out;
        }

        // -- legacy Hubitat -> HA mapping ---------------------------------------------

        /**
         * Map a legacy Hubitat device command onto a HA service call.
         *
         * domain defaults to the target entity's prefix (light.* -> light).
         * Returns {domain, service, serviceData} or throws on bad input,
         * mirroring the Python mirror's ValueError.
         */
        mapHubitatCommand(command, value, domain, entityId) {
            const spec = HUBITAT_COMMAND_MAP[command];
            if (!spec) {
                throw new Error(`unsupported device command '${command}'; supported: ${Object.keys(HUBITAT_COMMAND_MAP).join(', ')}`);
            }
            const target = entityId || this.entityId;
            let resolvedDomain = domain || (target ? String(target).split('.')[0] : null);
            if (!resolvedDomain) { throw new Error('no target entity/domain configured (set HA_ENTITY_ID)'); }

            const serviceData = {};
            let service = spec.service;

            if (service === 'update_entity') {
                // `update_entity` lives on the `homeassistant` domain --
                // `light.update_entity` etc. do not exist and HA would 404.
                // It is also valid for read-only domains (it forces a
                // re-poll rather than commanding the device), so route it
                // now and let the read-only check below see the
                // `homeassistant` domain.
                resolvedDomain = 'homeassistant';
            }
            if (READ_ONLY_DOMAINS.indexOf(resolvedDomain) !== -1) {
                throw new Error(`entity domain '${resolvedDomain}' is read-only and accepts no commands`);
            }

            if (command === 'setSwitch') {
                // value: {state: 'on'|'off'} or the bare string
                const wanted = (value && typeof value === 'object') ? value.state : value;
                if (wanted === 'on') { service = 'turn_on'; }
                else if (wanted === 'off') { service = 'turn_off'; }
                else { throw new Error("setSwitch requires state 'on' or 'off'"); }
            } else if (command === 'setLevel') {
                const level = Number(value);
                if (!isFinite(level) || level < 0 || level > 100) { throw new Error('setLevel requires a level between 0 and 100'); }
                serviceData.brightness_pct = Math.round(level);
            } else if (command === 'setHue') {
                const hue = Number(value);
                if (!isFinite(hue) || hue < 0 || hue > 100) { throw new Error('setHue requires a Hubitat hue between 0 and 100'); }
                // Hubitat hue is 0-100; HA hs_color hue is 0-360.
                serviceData.hs_color = [Math.round(hue * 3.6), 100];
            } else if (command === 'setSaturation') {
                const sat = Number(value);
                if (!isFinite(sat) || sat < 0 || sat > 100) { throw new Error('setSaturation requires a saturation between 0 and 100'); }
                serviceData.hs_color = [0, Math.round(sat)];
            } else if (command === 'setColor') {
                const colour = (typeof value === 'object') ? value : {};
                const hue = Number(colour.hue);
                const sat = Number(colour.saturation);
                if (!isFinite(hue) || !isFinite(sat)) { throw new Error('setColor requires hue and saturation'); }
                serviceData.hs_color = [Math.round(hue * 3.6), Math.round(sat)];
                if (colour.level !== undefined && colour.level !== null) {
                    const level = Number(colour.level);
                    if (!isFinite(level) || level < 0 || level > 100) { throw new Error('setColor level must be between 0 and 100'); }
                    serviceData.brightness_pct = Math.round(level);
                }
            } else if (command === 'setColorTemperature') {
                const kelvin = Number(value);
                if (!isFinite(kelvin) || kelvin < 1000 || kelvin > 10000) { throw new Error('setColorTemperature requires a Kelvin value between 1000 and 10000'); }
                serviceData.kelvin = Math.round(kelvin);
            } else if (command === 'setColorHex') {
                const hex = String((typeof value === 'object') ? value.hex : value).replace('#', '');
                if (!/^[0-9a-fA-F]{6}$/.test(hex)) { throw new Error("setColorHex requires a 6-digit RGB hex, e.g. 'FF0400'"); }
                serviceData.rgb_color = [
                    parseInt(hex.slice(0, 2), 16),
                    parseInt(hex.slice(2, 4), 16),
                    parseInt(hex.slice(4, 6), 16)
                ];
            }

            return { domain: resolvedDomain, service: service, serviceData: serviceData };
        }

        /**
         * Map a legacy Hubitat capability onto a HA entity domain.
         */
        mapCapabilityDomain(capability) {
            return HUBITAT_CAPABILITY_DOMAINS[capability] || null;
        }

        // -- REST surface -------------------------------------------------------------

        fail(code, message, extra) {
            const result = Object.assign({
                ok: false,
                code: code,
                entityId: null,
                domain: null,
                service: null,
                serviceData: null,
                statusCode: null,
                message: message,
                error: message
            }, extra || {});
            if (this.log) { this.log(`Home Assistant call failed (${code}): ${message}`); }
            return result;
        }

        /**
         * Trigger a HA service via the REST API.
         *   POST /api/services/<domain>/<service>
         *   Authorization: Bearer <LLAT>
         * `serviceData` carries extra fields (brightness_pct, hs_color, ...).
         */
        callService(domain, service, entityId, serviceData, callback) {
            let target = entityId || this.entityId;
            if (!target) {
                const result = this.fail('missing_configuration', 'no target entity configured (set HA_ENTITY_ID or pass entityId)');
                if (callback) { callback(result.error, result); }
                return result;
            }
            const domainOfTarget = String(target).split('.')[0];
            const useDomain = domain || domainOfTarget;
            if (!service) {
                const result = this.fail('invalid_argument', 'a service name is required (e.g. turn_on)');
                if (callback) { callback(result.error, result); }
                return result;
            }
            if (READ_ONLY_DOMAINS.indexOf(useDomain) !== -1) {
                const result = this.fail('read_only', `entity domain '${useDomain}' is read-only and accepts no commands`, { entityId: target, domain: useDomain, service: service });
                if (callback) { callback(result.error, result); }
                return result;
            }
            if (SUPPORTED_SERVICES[`${useDomain}.${service}`] === undefined &&
                SUPPORTED_SERVICES[`homeassistant.${service}`] === undefined) {
                const result = this.fail(
                    'unknown_service',
                    `unsupported service ${useDomain}.${service}; supported: ${Object.keys(SUPPORTED_SERVICES).join(', ')}`
                );
                if (callback) { callback(result.error, result); }
                return result;
            }
            try {
                const validated = this.validateServiceData(useDomain, service, serviceData);
                if (validated !== null) { serviceData = validated; }
            } catch (error) {
                const result = this.fail('invalid_argument', error.message, { entityId: target, domain: useDomain, service: service, serviceData: serviceData });
                if (callback) { callback(result.error, result); }
                return result;
            }

            const body = Object.assign({ entity_id: target }, serviceData || {});
            // A stray `entity_id` inside serviceData must never override the
            // validated target -- drop it rather than send two conflicting ids.
            body.entity_id = target;
            const url = this.restUrl(`services/${useDomain}/${service}`);
            this.sendRequest('POST', url, body, (err, response) => {
                if (err) {
                    const text = String((err && err.message) || err);
                    const timedOut = err.code === 'ETIMEDOUT' || err.code === 'ESOCKETTIMEDOUT' || /timeout/i.test(text);
                    const result = this.fail(
                        timedOut ? 'timeout' : 'connection_error',
                        timedOut ? 'Home Assistant did not respond in time' : `Home Assistant is unreachable (${text})`,
                        { entityId: target, domain: useDomain, service: service }
                    );
                    if (callback) { callback(result.error, result); }
                    return;
                }
                const statusCode = response.statusCode || response.status_code || null;
                if (statusCode === 401 || statusCode === 403) {
                    const result = this.fail('auth_error', `Home Assistant rejected the token (HTTP ${statusCode}) -- check HA_TOKEN (LLAT)`, { entityId: target, domain: useDomain, service: service, statusCode: statusCode });
                    if (callback) { callback(result.error, result); }
                    return;
                }
                if (statusCode && (statusCode < 200 || statusCode >= 300)) {
                    const result = this.fail('http_error', `Home Assistant returned HTTP ${statusCode}`, { entityId: target, domain: useDomain, service: service, statusCode: statusCode });
                    if (callback) { callback(result.error, result); }
                    return;
                }
                // A successful service call returns the new entity state(s).
                const payload = Array.isArray(response.body) ? response.body : (response.body && response.body.data) || response.body || [];
                if (Array.isArray(payload)) {
                    payload.forEach((state) => {
                        if (state && state.entity_id) { this.states[state.entity_id] = state; }
                    });
                }
                const result = {
                    ok: true,
                    code: 'ok',
                    entityId: target,
                    domain: useDomain,
                    service: service,
                    serviceData: serviceData || {},
                    statusCode: statusCode,
                    message: `${useDomain}.${service} sent to ${target}`,
                    error: null,
                    payload: payload
                };
                this.send && this.send({ payload: result, topic: `ha/entity/${target}/command` });
                if (callback) { callback(null, result); }
            });
            return null;
        }

        /**
         * Snapshot every entity state (REST twin of the WS get_states).
         */
        getStates(callback) {
            const url = this.restUrl('states');
            this.sendRequest('GET', url, null, (err, response) => {
                if (err) {
                    const result = this.fail('connection_error', `Home Assistant is unreachable (${err.message || err})`);
                    if (callback) { callback(result.error, result); }
                    return;
                }
                const statusCode = response.statusCode || response.status_code || null;
                if (statusCode && (statusCode < 200 || statusCode >= 300)) {
                    const result = this.fail('http_error', `Home Assistant returned HTTP ${statusCode}`, { statusCode: statusCode });
                    if (callback) { callback(result.error, result); }
                    return;
                }
                const list = Array.isArray(response.body) ? response.body : [];
                list.forEach((state) => {
                    if (state && state.entity_id) { this.states[state.entity_id] = state; }
                });
                this.status && this.status({ fill: 'green', shape: 'dot', text: `${list.length} entities` });
                if (callback) { callback(null, list); }
            });
            return null;
        }

        getEntityState(entityId, callback) {
            const url = this.restUrl(`states/${entityId}`);
            this.sendRequest('GET', url, null, (err, response) => {
                if (err || !response) {
                    const result = this.fail('connection_error', `Home Assistant is unreachable (${(err && err.message) || err || 'no response'})`);
                    if (callback) { callback(result.error, result); }
                    return;
                }
                const statusCode = response.statusCode || response.status_code || null;
                if (statusCode === 404) {
                    const result = this.fail('unknown_entity', `Home Assistant has no entity '${entityId}'`, { entityId: entityId, statusCode: statusCode });
                    if (callback) { callback(result.error, result); }
                    return;
                }
                if (statusCode && (statusCode < 200 || statusCode >= 300)) {
                    const result = this.fail('http_error', `Home Assistant returned HTTP ${statusCode}`, { entityId: entityId, statusCode: statusCode });
                    if (callback) { callback(result.error, result); }
                    return;
                }
                this.states[entityId] = response.body;
                if (callback) { callback(null, response.body); }
            });
            return null;
        }

        refreshStates() {
            this.getStates((err, list) => {
                if (!err && Array.isArray(list)) {
                    this.send({ payload: list, topic: 'ha/states' });
                }
            });
        }

        // -- convenience power commands -------------------------------------
        // Note `on` is the Node-RED event emitter, so the power commands
        // are turnOn/turnOff (same as the Hubitat node).
        turnOn(entityId, serviceData, callback) { return this.callService(null, 'turn_on', entityId, serviceData, callback); }
        turnOff(entityId, serviceData, callback) { return this.callService(null, 'turn_off', entityId, serviceData, callback); }
        toggle(entityId, callback) { return this.callService(null, 'toggle', entityId, null, callback); }

        // -- dashboard control surface -------------------------------------------------

        /**
         * Map a dashboard control action onto a HA service call.
         *
         * Accepts the native shape
         *   {"entityId": "light.kitchen", "domain": "light", "service": "turn_on", "data": {...}}
         * and the legacy Hubitat shape
         *   {"deviceId": ..., "command": "on"|"setLevel"|..., "value": ...}
         * so existing widgets keep working after the migration.
         */
        controlDevice(payload, callback) {
            let action = payload;
            if (action && action.payload && typeof action.payload === 'object' && !Array.isArray(action.payload)) {
                action = action.payload; // Node-RED msg wrapper
            }
            if (!action || typeof action !== 'object' || Array.isArray(action)) {
                const result = this.fail('invalid_payload', 'expected a mapping with entityId/domain/service or deviceId/command');
                if (callback) { callback(result.error, result); }
                return result;
            }

            if (action.service) {
                // Native HA service call.
                return this.callService(
                    action.domain,
                    action.service,
                    action.entityId || action.entity_id || this.entityId,
                    action.data || action.service_data || {},
                    callback
                );
            }

            // Legacy Hubitat command mapping.
            const entityId = action.entityId || action.entity_id || action.deviceId || this.entityId;
            const command = action.command;
            if (!command) {
                const result = this.fail('unknown_command', 'no service or command given');
                if (callback) { callback(result.error, result); }
                return result;
            }
            try {
                const mapped = this.mapHubitatCommand(command, action.value, action.domain, entityId);
                return this.callService(mapped.domain, mapped.service, entityId, mapped.serviceData, callback);
            } catch (error) {
                const result = this.fail('invalid_argument', error.message, { entityId: entityId, command: command });
                if (callback) { callback(result.error, result); }
                return result;
            }
        }

        sendRequest(method, url, data, callback) {
            // Simulated HTTP request -- the deployed flows use the palette's
            // `http request` node (see tools/gen_flows.py, HA tab), which
            // sets the same Bearer header from HA_TOKEN.
            setTimeout(() => {
                const response = {
                    success: true,
                    statusCode: 200,
                    body: data || {},
                    message: 'Home Assistant request completed (simulated)'
                };
                callback(null, response);
            }, 100);
        }
    }

    // Dashboard-facing alias: wire a `home-assistant-control` node's input
    // straight to this method so a UI action maps onto a HA service call.
    HomeAssistantNode.prototype.handleControl = HomeAssistantNode.prototype.controlDevice;

    RED.nodes.registerType("home-assistant-control", HomeAssistantNode);

    return HomeAssistantNode;
};