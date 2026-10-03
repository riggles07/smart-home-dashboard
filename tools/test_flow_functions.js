// Unit-test the flow function nodes by extracting real `func` bodies from the
// deployed flow JSON and running them against stubbed Node-RED globals.
const fs = require('fs');
const path = '/root/.hermes/projects/smart-home-dashboard/flows/all-flows.flow.json';
const nodes = JSON.parse(fs.readFileSync(path, 'utf8'));
const byName = {};
for (const n of nodes) if (n.type === 'function') byName[n.name] = n.func;

function makeEnv(vars) {
  return { get: (k) => (k in vars ? vars[k] : undefined), set: () => {} };
}
function makeNode(statusCalls) {
  return { status: (s) => statusCalls.push(s) };
}
function flowStore() {
  const s = {};
  return { get: (k) => s[k], set: (k, v) => { s[k] = v; } };
}

let pass = 0, fail = 0;
function check(label, cond, detail) {
  if (cond) { pass++; console.log(`  PASS  ${label}`); }
  else { fail++; console.log(`  FAIL  ${label}${detail ? ' -- ' + detail : ''}`); }
}

function run(name, vars, msg) {
  const code = byName[name];
  if (!code) throw new Error(`no function node named '${name}'`);
  const statuses = [];
  const fn = new Function('msg', 'env', 'node', 'flow', 'context', 'global', code);
  const out = fn(msg, makeEnv(vars), makeNode(statuses), flowStore(), {}, {});
  return { out, statuses };
}

console.log('== UniFi: API-key path ==');
{
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://unifi.example:8443', UNIFI_API_KEY: 'KEY123', UNIFI_SITE: 'default' }, { payload: 1 });
  check('routes to out1 (no login needed)', out[0] === null && out[1] !== null);
  check('url points at stat endpoint', out[1] && out[1].url === 'https://unifi.example:8443/api/s/default/stat/sta', out[1] && out[1].url);
  check('X-API-KEY header set', out[1] && out[1].headers['X-API-KEY'] === 'KEY123');
  check('TLS verification relaxed for self-signed', out[1] && out[1].rejectUnauthorized === false);
}
{
  // UniFi OS (UDM/Cloud Gateway): Network app is behind /proxy/network.
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://192.168.1.1/proxy/network', UNIFI_API_KEY: 'K' }, { payload: 1 });
  check('UniFi OS prefix preserved in stat url',
        out[1] && out[1].url === 'https://192.168.1.1/proxy/network/api/s/default/stat/sta',
        out[1] && out[1].url);
}
{
  // Trailing slash must not produce a double slash.
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://192.168.1.1/proxy/network/', UNIFI_API_KEY: 'K' }, { payload: 1 });
  check('trailing slash trimmed', out[1] && out[1].url.indexOf('network//api') === -1, out[1] && out[1].url);
}
{
  // UniFi OS login lives at /api/auth/login -- must be overridable.
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://192.168.1.1/proxy/network', UNIFI_USERNAME: 'u', UNIFI_PASSWORD: 'p', UNIFI_LOGIN_URL: 'https://192.168.1.1/api/auth/login' }, { payload: 1 });
  check('UNIFI_LOGIN_URL override honoured',
        out[0] && out[0].url === 'https://192.168.1.1/api/auth/login', out[0] && out[0].url);
}
{
  // Without the override, a UniFi OS base should auto-derive /api/auth/login
  // at the console root -- sending /proxy/network/api/login would be wrong.
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://192.168.1.1/proxy/network', UNIFI_USERNAME: 'u', UNIFI_PASSWORD: 'p' }, { payload: 1 });
  check('UniFi OS login path auto-derived',
        out[0] && out[0].url === 'https://192.168.1.1/api/auth/login', out[0] && out[0].url);
}
{
  // Self-hosted controller: no prefix, so /api/login is correct.
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://192.168.1.1:8443', UNIFI_USERNAME: 'u', UNIFI_PASSWORD: 'p' }, { payload: 1 });
  check('self-hosted login path is /api/login',
        out[0] && out[0].url === 'https://192.168.1.1:8443/api/login', out[0] && out[0].url);
}
{
  // Missing UNIFI_URL must fail loudly, not silently default to unifi.local.
  const { out, statuses } = run('Build UniFi auth', { UNIFI_USERNAME: 'u', UNIFI_PASSWORD: 'p' }, { payload: 1 });
  check('missing UNIFI_URL -> actionable error', out[1] && /UNIFI_URL is not set/.test(out[1]._error), out[1] && out[1]._error);
  check('missing UNIFI_URL -> status red', statuses.some(s => s.fill === 'red'));
}

console.log('== UniFi: legacy user/pass path ==');
{
  const { out } = run('Build UniFi auth', { UNIFI_URL: 'https://unifi.local:8443', UNIFI_SITE: 'default', UNIFI_USERNAME: 'admin', UNIFI_PASSWORD: 'pw' }, { payload: 1 });
  check('routes to out0 (login)', out[0] !== null && out[1] === null);
  check('POSTs /api/login', out[0] && out[0].method === 'POST' && out[0].url === 'https://unifi.local:8443/api/login', out[0] && out[0].url);
  check('body carries credentials', out[0] && JSON.parse(out[0].payload).username === 'admin');
  check('remembers stat url for later', out[0] && out[0].url_stat === 'https://unifi.local:8443/api/s/default/stat/sta');
}

console.log('== UniFi: missing credentials ==');
{
  const { out, statuses } = run('Build UniFi auth', { UNIFI_URL: 'https://unifi.local:8443' }, { payload: 1 });
  check('routes to out1 with error payload', out[1] && out[1].topic === 'unifi/error');
  check('error message is actionable', out[1] && /UNIFI_API_KEY|UNIFI_USERNAME/.test(out[1]._error), out[1] && out[1]._error);
  check('status shows red/no-credentials', statuses.some(s => s.fill === 'red'));
}

console.log('== UniFi: session cookie capture ==');
{
  const msg = { headers: { 'set-cookie': 'unifises=abc123; Path=/; HttpOnly' }, url_stat: 'https://u/api/s/default/stat/sta' };
  const { out } = run('Capture session', {}, msg);
  check('extracts cookie value', out.headers && out.headers['Cookie'] === 'unifises=abc123', out.headers && out.headers['Cookie']);
  check('switches to GET stat URL', out.method === 'GET' && out.url === 'https://u/api/s/default/stat/sta');
}
{
  const { out } = run('Capture session', {}, { headers: {}, url_stat: 'x', statusCode: 401 });
  check('no cookie -> error path', out.topic === 'unifi/error' && /401/.test(out._error), out._error);
}

console.log('== UniFi: client parsing ==');
{
  const msg = { payload: { data: [{ hostname: 'laptop', ip: '10.0.0.5', mac: 'aa:bb' }, { name: 'phone', mac: 'cc:dd' }, { mac: 'ee:ff' }] } };
  const { out } = run('Split client data', {}, msg);
  check('count output = 3', out[0].payload === 3, JSON.stringify(out[0].payload));
  check('rows mapped', out[1].payload.length === 3 && out[1].payload[0].hostname === 'laptop');
  check('name used when hostname absent', out[1].payload[1].hostname === 'phone', out[1].payload[1].hostname);
  check('mac used as last resort', out[1].payload[2].hostname === 'ee:ff', out[1].payload[2].hostname);
}
{
  const { out } = run('Split client data', {}, { topic: 'unifi/error', _error: 'no creds' });
  check('error path -> 0 + ERROR row', out[0].payload === 0 && /ERROR/.test(out[1].payload), out[1].payload);
}

console.log('== Proxmox: metric parsing ==');
{
  const msg = { payload: { data: { cpu: 0.0734, memory: { used: 2000, total: 8000 }, uptime: 90061, loadavg: [0.42, 0.3, 0.2] } } };
  const { out } = run('Split metrics', {}, msg);
  check('cpu -> 7.3%', out[0].payload === 7.3, String(out[0].payload));
  check('mem -> 25%', out[1].payload === 25, String(out[1].payload));
  check('uptime -> "Up 1d 1h"', /Up 1d 1h/.test(out[2].payload), out[2].payload);
  check('chart msg carries topic', out[3].payload === 7.3 && out[3].topic === 'cpu');
}
{
  const { out } = run('Split metrics', {}, { payload: {} });
  check('missing data -> null (no crash)', out === null || out === undefined, JSON.stringify(out));
}

console.log('== Hubitat: command building ==');
{
  const { out } = run('Build Maker API call', { HUBITAT_URL: 'http://hub.local', HUBITAT_APP_ID: '42', HUBITAT_ACCESS_TOKEN: 'tok', HUBITAT_DEVICE_ID: '7' }, { topic: 'hubitat/power', payload: true });
  check('power on -> /devices/7/on', out[0] && out[0].url === 'http://hub.local/apps/api/42/devices/7/on?access_token=tok', out[0] && out[0].url);
}
{
  const { out } = run('Build Maker API call', { HUBITAT_URL: 'http://hub.local', HUBITAT_APP_ID: '42', HUBITAT_ACCESS_TOKEN: 'tok', HUBITAT_DEVICE_ID: '7' }, { topic: 'hubitat/level', payload: 65 });
  check('brightness -> /setLevel/65', out[0] && /devices\/7\/setLevel\/65\?/.test(out[0].url), out[0] && out[0].url);
}
{
  const { out } = run('Build Maker API call', {}, { topic: 'hubitat/power', payload: true });
  check('missing config -> error on out1', out[1] && /HUBITAT_APP_ID/.test(out[1].payload), out[1] && out[1].payload);
}
{
  const { out } = run('Build Maker API call', { HUBITAT_URL: 'http://h', HUBITAT_APP_ID: '1', HUBITAT_ACCESS_TOKEN: 't', HUBITAT_DEVICE_ID: '2' }, { topic: 'other', payload: 1 });
  check('unknown topic -> ignored (null)', out === null || out === undefined);
}

console.log('== Hubitat: result formatting ==');
{
  const { out } = run('Format result', {}, { statusCode: 200, payload: '{"ok":true}' });
  check('2xx -> OK', /^OK \(200\)/.test(out.payload), out.payload);
}
{
  const { out } = run('Format result', {}, { error: 'ENOTFOUND hub.local' });
  check('transport error -> ERROR unreachable', /ERROR: Hubitat unreachable/.test(out.payload), out.payload);
}
{
  const { out } = run('Format result', {}, { statusCode: 403, payload: 'forbidden' });
  check('4xx -> ERROR HTTP 403', /ERROR HTTP 403/.test(out.payload), out.payload);
}

console.log('== Kanban: card store ==');
{
  const code = byName['Add card'];
  const store = flowStore();
  const fn = new Function('msg', 'env', 'node', 'flow', 'context', 'global', code);
  const st = [];
  let r = fn({ payload: 'Buy milk' }, makeEnv({}), makeNode(st), store, {}, {});
  r = fn({ payload: 'Walk dog' }, makeEnv({}), makeNode(st), store, {}, {});
  check('two cards persisted in flow context', store.get('kanban_cards').length === 2, JSON.stringify(store.get('kanban_cards')));
  check('card shape {task,status}', store.get('kanban_cards')[0].task === 'Buy milk' && store.get('kanban_cards')[0].status === 'todo');
  const r3 = fn({ payload: '   ' }, makeEnv({}), makeNode(st), store, {}, {});
  check('blank input ignored', r3 === null && store.get('kanban_cards').length === 2);
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
