/**
 * Live check of flows/hubitat-integration.js against a real HTTP server.
 *
 * Loads the flow with a stub RED runtime, points it at a local Rule Machine
 * endpoint-trigger stub, and drives the real network path (node's http module)
 * through getAutomations() / triggerAutomation().
 *
 *   node scripts/live_trigger_check.js
 */
'use strict';

const http = require('http');
const { URL } = require('url');
const path = require('path');

const APP_ID = '10249';
const TOKEN = '00000000-1111-2222-3333-444444444444';
const RULES = { '943': 'Good Morning', '956': 'Away Mode', '10217': 'Movie Night' };

const seen = [];
let sendCount = 0;
const failures = [];

function check(label, condition, detail) {
    const status = condition ? 'PASS' : 'FAIL';
    console.log(`  [${status}] ${label}${detail ? ' -- ' + detail : ''}`);
    if (!condition) { failures.push(label); }
}

// ---- Rule Machine endpoint-trigger stub -------------------------------------
const server = http.createServer((req, res) => {
    const url = new URL(req.url, `http://${req.headers.host}`);
    seen.push({ method: req.method, path: decodeURIComponent(url.pathname), token: url.searchParams.get('access_token') });

    const reply = (status, body) => {
        const text = JSON.stringify(body);
        res.writeHead(status, { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(text) });
        res.end(text);
    };

    if (url.searchParams.get('access_token') !== TOKEN) { reply(401, { error: 'Unauthorized' }); return; }

    const prefix = `/apps/api/${APP_ID}/trigger`;
    if (!url.pathname.startsWith(prefix)) { reply(404, { error: 'Not Found' }); return; }
    const rest = decodeURIComponent(url.pathname.slice(prefix.length)).replace(/^\/+/, '');

    if (rest === 'getRuleList') { reply(200, RULES); return; }
    if (rest.startsWith('runRuleAct=')) {
        const ids = rest.slice('runRuleAct='.length).split('&');
        const unknown = ids.filter((id) => !RULES[id]);
        if (unknown.length) { reply(404, { error: `unknown rule ${unknown}` }); return; }
        reply(200, { status: 'ok', ranRules: ids.map((id) => ({ id, name: RULES[id] })) });
        return;
    }
    if (rest.startsWith('stopRuleAct=')) { reply(200, { status: 'ok', stopped: rest.split('=')[1] }); return; }
    reply(404, { error: `no such endpoint ${rest}` });
});

// ---- minimal RED runtime ----------------------------------------------------
function makeRed() {
    const types = {};
    class BaseNode {
        constructor(type, msg, config) {
            this.type = type;
            this.msg = msg;
            this.config = config || {};
            this.logs = [];
        }
        on() { }
        setInterval() { }
        status() { }
        log(m) { this.logs.push(m); }
        warn(m) { this.logs.push('WARN: ' + m); }
        send(msg) { sendCount += 1; this.sent = this.sent || []; this.sent.push(msg); }
        // Real HTTP via node's http module -- the actual production path for
        // a node-red-exec / http-request style node.
        //
        // The flow passes the node-red-contrib-http-request option shape
        // ({ method, url, timeout, headers }), which core http.request does NOT
        // accept, so translate `url` into hostname/port/path here.
        httpRequest(opts, cb) {
            const target = new URL(opts.url);
            const req = http.request({
                protocol: target.protocol,
                hostname: target.hostname,
                port: target.port || (target.protocol === 'https:' ? 443 : 80),
                path: `${target.pathname}${target.search}`,
                method: opts.method || 'GET',
                headers: opts.headers
            }, (res) => {
                let body = '';
                res.on('data', (c) => { body += c; });
                res.on('end', () => cb(null, res, body));
            });
            req.on('error', (err) => cb(err));
            req.setTimeout(opts.timeout || 5000, () => req.destroy(new Error('timeout')));
            req.end();
        }
    }
    return {
        types,
        Node: BaseNode,
        nodes: { addType: (name, cfg) => { types[name] = cfg; } }
    };
}

const RED = makeRed();
RED.nodes.registerType = (name, cls) => { RED.types[name] = cls; };

const flow = require(path.join(__dirname, '..', 'flows', 'hubitat-integration.js'));

server.listen(0, '127.0.0.1', async () => {
    const base = `http://127.0.0.1:${server.address().port}`;
    console.log(`Live Hubitat stub (JS) on ${base} -- real http over TCP\n`);

    const HubitatNode = flow(RED);
    const make = (config) => {
        const node = new HubitatNode('hubitat-control', {}, Object.assign({
            url: base, appId: APP_ID, accessToken: TOKEN
        }, config));
        node.init();
        node.sent = [];
        return node;
    };
    // Poll until a condition holds (bounded) instead of a fixed sleep, so a
    // slow cold-start round-trip cannot race the checks.
    const waitFor = (predicate, timeoutMs = 5000) => new Promise((resolve) => {
        const started = Date.now();
        const poll = () => {
            let done;
            try { done = predicate() === true; } catch (e) { done = true; }
            if (done || Date.now() - started >= timeoutMs) return resolve();
            setTimeout(poll, 25);
        };
        poll();
    });

    try {
        // 1. list
        console.log('1. getAutomations() -> GET .../trigger/getRuleList');
        const node = make();
        let listing = null;
        node.getAutomations((err, res) => { listing = res; });
        await waitFor(() => listing !== null);
        check('list ok', listing && listing.ok === true, listing && listing.message);
        check('3 rules returned', listing && listing.automations.length === 3, JSON.stringify(listing && listing.automations));
        check('cached after fetch', node.automationsResolved === true);
        check('published on hubitat/automations', node.sent.some((m) => m.topic === 'hubitat/automations'));

        // 2. cache
        const callsBefore = seen.length;
        let cacheCb = 0;
        node.getAutomations(() => { cacheCb++; });
        await waitFor(() => cacheCb === 1);
        check('second call served from cache', seen.length === callsBefore);

        // 3. trigger by id
        console.log('\n2. triggerAutomation(id) -> POST .../trigger/runRuleAct=943');
        const node2 = make();
        let trig = null;
        node2.triggerAutomation('943', (err, res) => { trig = res; });
        await waitFor(() => trig !== null);
        check('trigger ok', trig && trig.ok === true, trig && trig.message);
        check('resolved name', trig && trig.automationName === 'Good Morning');
        check('hub ran the rule', trig && trig.payload && trig.payload.ranRules[0].id === '943', JSON.stringify(trig && trig.payload));
        const lastReq = seen[seen.length - 1];
        check('POST method used', lastReq.method === 'POST', lastReq.method);
        check('url shape', lastReq.path === `/apps/api/${APP_ID}/trigger/runRuleAct=943`, lastReq.path);
        check('token redacted in result', trig && !String(trig.url).includes(TOKEN), trig && trig.url);
        check('published on per-rule topic',
            node2.sent.some((m) => m.topic === 'hubitat/automation/result/943'),
            JSON.stringify(node2.sent.map((m) => m.topic)));

        // 4. trigger by name
        console.log('\n3. triggerAutomation(name) -> resolved app id');
        const node3 = make();
        let byName = null;
        node3.triggerAutomation('Movie Night', (err, res) => { byName = res; });
        await waitFor(() => byName !== null);
        check('trigger by name ok', byName && byName.ok === true, byName && byName.message);
        check('resolved to 10217', byName && byName.automationId === '10217', byName && byName.automationId);

        // 5. unknown id
        console.log('\n4. unknown automation id');
        const before = seen.length;
        let unknown = null;
        node.triggerAutomation('0000', (err, res) => { unknown = res; });
        await waitFor(() => unknown !== null);
        check('unknown rejected', unknown && unknown.ok === false);
        check('code=unknown_automation', unknown && unknown.code === 'unknown_automation', unknown && unknown.code);
        check('no http call made', seen.length === before, `${seen.length - before} extra`);

        // 6. auth failure
        console.log('\n5. auth failure (bad token -> 401)');
        const bad = make({ accessToken: 'wrong' });
        let auth = null;
        bad.getAutomations((err, res) => { auth = res; });
        await waitFor(() => auth !== null);
        check('auth failure reported', auth && auth.ok === false);
        check('code=auth_failure', auth && auth.code === 'auth_failure', auth && auth.code);
        check('statusCode 401', auth && auth.statusCode === 401, String(auth && auth.statusCode));

        // 7. unreachable
        console.log('\n6. hub unreachable (connection refused)');
        const dead = make({ url: 'http://127.0.0.1:1', timeout: 1500 });
        let unreachable = null;
        dead.getAutomations((err, res) => { unreachable = res; });
        await waitFor(() => unreachable !== null);
        check('unreachable reported', unreachable && unreachable.ok === false);
        check('code=hub_unreachable', unreachable && unreachable.code === 'hub_unreachable', unreachable && unreachable.code);

        // 8. legacy simulation fallback
        console.log('\n7. legacy simulated path (no credentials)');
        const sim = new HubitatNode('hubitat-control', {}, { url: base });
        sim.init();
        sim.sent = [];
        let simulated = null;
        sim.triggerAutomation('aut1', (err, res) => { simulated = res; });
        await waitFor(() => simulated !== null);
        check('falls back to simulator', simulated && simulated.success === true, JSON.stringify(simulated));

        // 9. static helpers
        console.log('\n8. helpers');
        const picker = make();
        let fromEntryPoint = null;
        picker.handleAutomationList({ payload: { refresh: true } }, (err, res) => { fromEntryPoint = res; });
        await waitFor(() => fromEntryPoint !== null);
        check('handleAutomationList() entry point', fromEntryPoint && fromEntryPoint.ok === true
            && fromEntryPoint.automations.length === 3, fromEntryPoint && fromEntryPoint.message);
        check('parseAutomationList handles map',
            JSON.stringify(HubitatNode.parseAutomationList({ '1': 'A' })) === JSON.stringify([{ id: '1', name: 'A' }]));
        check('parseAutomationList handles list',
            JSON.stringify(HubitatNode.parseAutomationList([{ id: 1, label: 'A' }])) === JSON.stringify([{ id: '1', name: 'A' }]));
        check('parseAutomationList rejects garbage', HubitatNode.parseAutomationList('nope') === null);
        check('failure() shape', HubitatNode.failure('x', 'm', {}).ok === false
            && HubitatNode.failure('x', 'm', {}).code === 'x');

        console.log(`\n${seen.length} request(s) served, ${sendCount} dashboard message(s) sent.`);
    } catch (e) {
        console.error('UNEXPECTED ERROR:', e);
        failures.push('unexpected: ' + e.message);
    } finally {
        server.close();
    }

    if (failures.length) {
        console.log(`\nFAILED: ${failures.length} check(s): ${failures.join(', ')}`);
        process.exit(1);
    }
    console.log('\nAll live JS checks passed.');
    process.exit(0);
});
