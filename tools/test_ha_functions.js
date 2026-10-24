// Functional tests for the Home Assistant flow functions.
//
// Loads the REAL `func` bodies out of the deployed flow JSON and drives them
// the way Node-RED does: the body is invoked once per message and its RETURN
// value is what gets emitted; asynchronous sends go through node.send().
//
// This exists because the HA nodes spent a release as dead code (a literal
// backslash-n turned the whole body into one // comment), and then threw
// "ReferenceError: on is not defined" once that was fixed -- while every
// structural check stayed green. Structural checks are not enough; drive the
// bodies and assert on what they actually emit.
//
// Run:  node tools/test_ha_functions.js
const fs = require('fs');
const path = require('path');

const flowPath = process.argv[2] ||
  path.join(__dirname, '..', 'flows', 'all-flows.flow.json');
const nodes = JSON.parse(fs.readFileSync(path.resolve(flowPath), 'utf8'));
const byName = {};
for (const n of nodes) if (n.type === 'function') byName[n.name] = n;

let pass = 0, fail = 0;
function check(name, cond, extra) {
  if (cond) { pass++; console.log('  PASS  ' + name); }
  else { fail++; console.log('  FAIL  ' + name + (extra !== undefined ? '  -> ' + JSON.stringify(extra) : '')); }
}

// ---- fake ws ---------------------------------------------------------------
let wsConstructed = 0;
class FakeWS {
  constructor(url) { wsConstructed++; this.url = url; FakeWS.last = this; this.handlers = {}; this.sent = []; }
  on(ev, fn) { (this.handlers[ev] = this.handlers[ev] || []).push(fn); return this; }
  send(d) { this.sent.push(d); }
  close() { this.closed = true; }
  terminate() { this.closed = true; }
  fire(ev, arg) { (this.handlers[ev] || []).forEach(f => f(arg)); }
}

// ---- loader (mirrors how Node-RED invokes a classic function node) --------
function load(def, envVars) {
  if (!def) throw new Error('function node not found');
  const sent = [], statuses = [];
  const nodeObj = {
    status: s => statuses.push(s), send: m => sent.push(m),
    warn: () => {}, error: () => {}, log: () => {}
  };
  const envObj = { get: k => (Object.prototype.hasOwnProperty.call(envVars, k) ? envVars[k] : undefined) };
  const mk = () => ({ _s: {}, get(k) { return this._s[k]; }, set(k, v) { this._s[k] = v; } });
  const ctx = mk(), globalObj = mk(), flowObj = mk();
  const body = new Function('node', 'env', 'on', 'global', 'flow', 'context', 'msg', 'util', 'RED', 'ws', def.func);
  return {
    sent, statuses, ctx,
    invoke(msg) {
      sent.length = 0; statuses.length = 0;
      try {
        return body(nodeObj, envObj, undefined, globalObj, flowObj, ctx, msg, {}, {}, FakeWS);
      } catch (e) {
        throw new Error('function body threw on invoke: ' + e.message);
      }
    }
  };
}

const WS_DEF = byName['HA WebSocket Client'];
const REST_DEF = byName['HA REST Controller'];
const ENV = { HA_URL: 'http://ha.local:8123', HA_TOKEN: 'tok123', HA_ENTITY_ID: 'light.kitchen' };
const TICK = { payload: new Date(), topic: '' };

// ---- 0. the bodies must not use APIs this runtime does not provide --------
console.log('\n== unsupported API guard ==');
for (const [label, def] of [['HA WebSocket Client', WS_DEF], ['HA REST Controller', REST_DEF]]) {
  const code = def.func.split('\n').map(l => l.replace(/\/\/.*$/, '')).join('\n');
  check(label + ': does not call bare on()', !/(^|[^.\w])on\s*\(/.test(code));
  check(label + ': does not call node.on()', !/node\.on\s*\(/.test(code));
  check(label + ': does not use send()/done() params', !/(^|[^.\w])(send|done)\s*\(/.test(code));
}

// ---- 1. missing HA_TOKEN -> never actuates ---------------------------------
console.log('\n== HA WebSocket Client: no token ==');
{
  wsConstructed = 0; FakeWS.last = undefined;
  const f = load(WS_DEF, {});
  check('tick returns null', f.invoke(TICK) === null);
  check('reports no HA_TOKEN', f.statuses.some(s => s.text === 'no HA_TOKEN'), f.statuses);
  check('no websocket opened', wsConstructed === 0);
  check('no socket persisted', !f.ctx.get('ha_socket'));
}

// ---- 2. state path --------------------------------------------------------
console.log('\n== HA WebSocket Client: state path ==');
{
  wsConstructed = 0; FakeWS.last = undefined;
  const f = load(WS_DEF, ENV);
  check('tick emits nothing', f.invoke(TICK) === null);
  check('opened exactly one websocket', wsConstructed === 1);
  check('ws url is ws:// + /api/websocket', FakeWS.last.url === 'ws://ha.local:8123/api/websocket', FakeWS.last.url);

  // a second tick must NOT open a second socket (context persistence)
  f.invoke(TICK);
  check('second tick reuses the socket', wsConstructed === 1, wsConstructed);

  FakeWS.last.fire('open');
  const auth = JSON.parse(FakeWS.last.sent[0]);
  check('sends auth on open', auth.type === 'auth' && auth.access_token === 'tok123', auth);

  FakeWS.last.fire('message', JSON.stringify({ type: 'auth_ok' }));
  check('requests get_states', FakeWS.last.sent.some(s => JSON.parse(s).type === 'get_states'));
  check('subscribes to state_changed',
    FakeWS.last.sent.some(s => { const m = JSON.parse(s); return m.type === 'subscribe_events' && m.event_type === 'state_changed'; }));

  FakeWS.last.fire('message', JSON.stringify({
    type: 'result', success: true,
    result: [{ entity_id: 'light.kitchen', state: 'on', attributes: { friendly_name: 'Kitchen' } }]
  }));
  const out = f.sent[f.sent.length - 1];
  check('state list goes to output 1 only', Array.isArray(out) && out[0] === null && out[1].payload === 1, out);
  check('status shows entity count', f.statuses.some(s => /1 entities/.test(s.text || '')), f.statuses);

  f.sent.length = 0;
  FakeWS.last.fire('message', JSON.stringify({
    type: 'event',
    event: { data: { entity_id: 'light.kitchen', new_state: { state: 'on', attributes: { friendly_name: 'Kitchen', brightness_pct: 42 } } } }
  }));
  const ev = f.sent[0];
  check('state event -> output 1', Array.isArray(ev) && ev[0] === null && ev[1].topic === 'ha/entity/light.kitchen/state', ev);
  check('normalised payload',
    ev[1].payload.domain === 'light' && ev[1].payload.isOn === true && ev[1].payload.brightnessPct === 42, ev[1].payload);
  check('state events never reach the control output', f.sent.every(m => m[0] === null));

  FakeWS.last.fire('message', JSON.stringify({ type: 'auth_invalid' }));
  check('auth failure clears the socket', !f.ctx.get('ha_socket'));
  check('auth failure is visible', f.statuses.some(s => s.text === 'auth failed'), f.statuses);

  const g = load(WS_DEF, ENV);
  g.invoke(TICK);
  FakeWS.last.fire('close');
  check('close clears the socket', !g.ctx.get('ha_socket'));
}

// ---- 3. dashboard switch drives the control path --------------------------
console.log('\n== HA WebSocket Client: control path ==');
{
  FakeWS.last = undefined;
  const f = load(WS_DEF, ENV);
  f.invoke(TICK);

  let c = f.invoke({ payload: true });
  check('switch ON -> array on out0, null on out1', Array.isArray(c) && c[1] === null && c[0].topic === 'ha/control', c);
  check('url is .../api/services/light/turn_on',
    c && c[0].url === 'http://ha.local:8123/api/services/light/turn_on', c && c[0].url);
  check('body carries entity_id', c && c[0].body.entity_id === 'light.kitchen', c && c[0].body);
  check('method POST', c && c[0].method === 'POST');

  c = f.invoke({ payload: false });
  check('switch OFF -> turn_off', c && c[0].url === 'http://ha.local:8123/api/services/light/turn_off', c && c[0].url);
}

// ---- 4. explicit request + read-only guard --------------------------------
console.log('\n== HA WebSocket Client: explicit request ==');
{
  const f = load(WS_DEF, ENV);
  f.invoke(TICK);
  let c = f.invoke({ topic: 'ha/control', payload: { domain: 'light', service: 'turn_on', entityId: 'light.hall', serviceData: { brightness_pct: 30 } } });
  check('honours explicit domain/service/entityId',
    c && c[0].url === 'http://ha.local:8123/api/services/light/turn_on' && c[0].body.entity_id === 'light.hall', c);
  check('merges serviceData', c && c[0].body.brightness_pct === 30, c && c[0].body);

  c = f.invoke({ topic: 'ha/control', payload: { domain: 'sensor', service: 'turn_on', entityId: 'sensor.x' } });
  check('refuses read-only domains', c === null && f.statuses.some(s => s.text === 'read-only'), f.statuses);
}

// ---- 5. missing HA_ENTITY_ID on the switch path ---------------------------
console.log('\n== HA WebSocket Client: missing entity ==');
{
  const f = load(WS_DEF, { HA_URL: 'http://ha.local:8123', HA_TOKEN: 'tok' });
  f.invoke(TICK);
  const c = f.invoke({ payload: true });
  check('no actuation without HA_ENTITY_ID', c === null);
  check('reports no HA_ENTITY_ID', f.statuses.some(s => s.text === 'no HA_ENTITY_ID'), f.statuses);
}

// ---- 6. REST controller ---------------------------------------------------
console.log('\n== HA REST Controller ==');
{
  const f = load(REST_DEF, ENV);
  const out = f.invoke({ url: 'http://ha.local:8123/api/services/light/turn_on/', method: 'POST', body: { entity_id: 'light.kitchen' } });
  check('adds bearer auth', out.headers.Authorization === 'Bearer tok123', out.headers);
  check('content-type json', out.headers['Content-Type'] === 'application/json');
  check('strips trailing slash', out.url === 'http://ha.local:8123/api/services/light/turn_on', out.url);
  check('body -> payload', out.payload.entity_id === 'light.kitchen', out.payload);
  check('defaults method to POST', out.method === 'POST');

  const nothing = f.invoke({ topic: 'ha/state_count', payload: 12 });
  check('a stray state message returns null instead of throwing', nothing === null, nothing);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail === 0 ? 0 : 1);
