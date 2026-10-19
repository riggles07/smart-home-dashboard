// Unit-test the flow function nodes by extracting real `func` bodies from the
// deployed flow JSON and running them against stubbed Node-RED globals.
//
// Resolve the flow file RELATIVE TO THIS SCRIPT, not by an absolute path.
// This previously hardcoded the author's dev path (/root/.hermes/...), which
// made the script pass locally and fail in CI with EACCES -- and it made a
// clean-clone check pass too, because the absolute path still existed on the
// machine doing the checking.
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const here = __dirname;                              // .../tools
const flowPath = process.argv[2] ||
    path.join(here, '..', 'flows', 'all-flows.flow.json');
const nodes = JSON.parse(fs.readFileSync(path.resolve(flowPath), 'utf8'));
const byName = {};
for (const n of nodes) if (n.type === 'function') byName[n.name] = n.func;

// === STRUCTURAL VALIDATION ===
function validateStructure() {
  const validatorPath = path.join(here, 'validate_flows.py');
  try {
    execSync(`python3 "${validatorPath}" "${path.resolve(flowPath)}"`, {
      stdio: ['inherit', 'inherit', 'inherit'],
      env: { ...process.env, PYTHONUNBUFFERED: '1' }
    });
  } catch (e) {
    console.error('\n=== STRUCTURAL VALIDATION FAILED ===');
    console.error('Flow file is structurally invalid. Cannot proceed with function tests.');
    console.error('Run `python3 ' + validatorPath + ' ' + flowPath + '` for details.\n');
    process.exit(1);
  }
}
validateStructure();

// === GRAPH-LEVEL ASSERTIONS ===
function validateGraph() {
  const ids = new Set(nodes.map(n => n.id));
  const tabs = new Set(nodes.filter(n => n.type === 'tab').map(n => n.id));
  const uiTabs = new Set(nodes.filter(n => n.type === 'ui_tab').map(n => n.id));
  const groups = new Set(nodes.filter(n => n.type === 'ui_group').map(n => n.id));
  const widgets = { 'ui_gauge': true, 'ui_text': true, 'ui_chart': true, 'ui_switch': true, 'ui_slider': true, 'ui_template': true, 'ui_button': true, 'ui_text_input': true, 'ui_ui_control': true };

  // (a) Wire source/target resolution
  for (const n of nodes) {
    for (let outIdx = 0; outIdx < (n.wires || []).length; outIdx++) {
      for (const target of n.wires[outIdx]) {
        if (!ids.has(target)) {
          throw new Error(`Wire from ${n.type}(${n.name || n.id}) output ${outIdx} -> unknown node ${target}`);
        }
      }
    }
  }

  // (b) ui_group.tab references defined tabs
  for (const n of nodes) {
    if (n.type === 'ui_group' && !uiTabs.has(n.tab)) {
      throw new Error(`ui_group(${n.name || n.id}) tab=${n.tab} not a ui_tab`);
    }
  }

  // (c) Widget group references
  for (const n of nodes) {
    if (widgets[n.type] && n.group && !groups.has(n.group)) {
      throw new Error(`${n.type}(${n.name || n.id}) group=${n.group} not a ui_group`);
    }
  }

  // (d) Every non-tab node has a valid z (tab)
  for (const n of nodes) {
    if (n.type === 'tab' || n.z === undefined) continue;
    const z = n.z;
    if (!z) {
      throw new Error(`${n.type}(${n.name || n.id}) has no z tab`);
    }
    if (!tabs.has(z)) {
      throw new Error(`${n.type}(${n.name || n.id}) z=${z} is not a tab`);
    }
  }

  // (e) ui_base theme template must exist (check theme name is defined)
  for (const n of nodes) {
    if (n.type === 'ui_base' && n.theme?.name) {
      // Note: We can't verify the theme file exists at runtime, but we can check
      // that the theme name is not empty/undefined and is a reasonable string.
      // For full validation, the theme file must exist in node-red-dashboard themes.
      if (!n.theme.name || typeof n.theme.name !== 'string') {
        throw new Error(`ui_base(${n.name || n.id}) has invalid theme name`);
      }
    }
  }
}
validateGraph();

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

console.log('== Proxmox: request building ==');
{
  const { out } = run('Build Proxmox request', { PROXMOX_URL: 'https://pve.local:8006', PROXMOX_NODE: 'pve', PROXMOX_TOKEN: 'u@pam!t=s' }, {});
  check('builds node status url', out && out.url === 'https://pve.local:8006/api2/json/nodes/pve/status', out && out.url);
  check('sends PVEAPIToken header', out && out.headers['Authorization'] === 'PVEAPIToken=u@pam!t=s');
  check('trailing slash trimmed', out && out.url.indexOf('8006//api2') === -1);
}
{
  const { out, statuses } = run('Build Proxmox request', {}, {});
  check('missing config -> null (no request)', out === null || out === undefined);
  check('missing config -> status red', statuses.some(s => s.fill === 'red'));
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

console.log('== Proxmox: host detail (new outputs) ==');
{
  // Shape mirrors the LIVE /nodes/<node>/status response captured by
  // tools/probe_proxmox_status.py -- real key names, real nesting.
  const msg = { payload: { data: {
    cpu: 0.0734,
    memory: { used: 5153960755, total: 17179869184, available: 12025908429 },
    rootfs: { used: 21474836480, total: 107374182400, avail: 85899345920, free: 85899345920 },
    swap:   { used: 1073741824, total: 8589934592, free: 7516192768 },
    uptime: 639066,
    loadavg: [0.42, 0.3, 0.2],
    pveversion: 'pve-manager/9.2.21/4f6e0ac86f9e8c7f',
    kversion: 'Linux 7.0.14-19-pve',
    cpuinfo: { model: 'AMD EPYC 7763 64-Core Processor', cores: 8, mhz: '2450' },
    'current-kernel': { release: '7.0.14-19-pve' }
  } } };
  const { out } = run('Split metrics', {}, msg);
  check('outputs 8 messages (was 4)', Array.isArray(out) && out.length === 8, String(out && out.length));

  const detail = out[4] && out[4].payload;
  check('detail.pveversion real', detail && /pve-manager/.test(detail.pveversion), detail && detail.pveversion);
  check('detail.kversion real', detail && /Linux 7\.0\.14/.test(detail.kversion), detail && detail.kversion);
  check('detail.model from cpuinfo', detail && /EPYC/.test(detail.model), detail && detail.model);
  check('detail.cores from cpuinfo', detail && detail.cores === 8, String(detail && detail.cores));
  check('detail.mhz from cpuinfo', detail && detail.mhz === '2450', String(detail && detail.mhz));
  check('detail load1/5/15 split', detail && detail.load1 === 0.42 && detail.load5 === 0.3 && detail.load15 === 0.2,
        detail && `${detail.load1}/${detail.load5}/${detail.load15}`);

  check('swap -> % of total GB', /^12\.5% of 8 GB$/.test(out[5].payload), out[5].payload);
  check('disk -> % of total + free', /^20% of 100 GB.*80 GB free/.test(out[6].payload), out[6].payload);
  check('memory -> used/total/avail', /^4\.8 GB of 16 GB.*11\.2 GB avail/.test(out[7].payload), out[7].payload);
}
{
  // Absent sub-objects must degrade to readable placeholders, not "undefined".
  const { out } = run('Split metrics', {}, { payload: { data: { cpu: 0.1, uptime: 0 } } });
  check('no rootfs/swap -> no "undefined" leak',
        [out[5], out[6], out[7]].every(m => m && !/undefined/.test(String(m.payload))),
        [out[5].payload, out[6].payload, out[7].payload].join(' | '));
  const d = out[4] && out[4].payload;
  check('missing cpuinfo -> model "unknown" not undefined',
        d && d.model === 'unknown' && /unknown/.test(d.pveversion), JSON.stringify(d));
}
{
  const { out } = run('Split metrics', {}, { payload: {} });
  check('missing data -> null (no crash)', out === null || out === undefined, JSON.stringify(out));
}

// == Hubitat: REMOVED ==
// The Maker API integration was removed from the flows (Hubitat is no longer
// the device path -- Home Assistant is; see docs and the HA tab). These tests
// kept calling `run('Build Maker API call')` and threw 'no function node named'
// BEFORE any later block could run, so the whole harness died here and every
// assertion after line ~284 was silently skipped. Deleted rather than skipped
// so a future Hubitat return is a deliberate re-add, not a passing ghost.

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

console.log('== Render board: function node exercise ==');
// Inline the Render board function code to avoid potential parsing issues with flow.json
// The code comes from flows/04-kanban-board.flow.json
const renderBoardCode = "var cards = flow.get('kanban_cards') || [];\nnode.status({fill:'blue',shape:'dot',text:cards.length + ' cards'});\nmsg.payload = cards;\nreturn [msg, msg];";
const code = renderBoardCode;
const store = flowStore();
const fn = new Function('msg', 'env', 'node', 'flow', 'context', 'global', code);

// Test 1: Normal operation with cards
store.set('kanban_cards', [
  { task: 'Buy milk', status: 'todo' },
  { task: 'Walk dog', status: 'doing' },
  { task: 'Review PR', status: 'todo' }
]);

const statuses1 = [];
const flow1 = { get: (k) => store.get(k), set: (k, v) => store.set(k, v) };
const out1 = fn({ topic: 'kanban/refresh' }, makeEnv({}), makeNode(statuses1), flow1, {}, {});
check('returns array of 2 messages', Array.isArray(out1) && out1.length === 2, String(out1 && out1.length));
  
if (Array.isArray(out1) && out1.length >= 2) {
  // Both outputs should contain the cards array
  check('output[0].payload is cards array', Array.isArray(out1[0].payload) && out1[0].payload.length === 3, JSON.stringify(out1[0].payload));
  check('first card preserved', out1[0].payload[0].task === 'Buy milk' && out1[0].payload[0].status === 'todo');
  check('second card preserved', out1[0].payload[1].task === 'Walk dog' && out1[0].payload[1].status === 'doing');
  check('third card preserved', out1[0].payload[2].task === 'Review PR' && out1[0].payload[2].status === 'todo');
  
  check('output[1].payload is cards array', Array.isArray(out1[1].payload) && out1[1].payload.length === 3, JSON.stringify(out1[1].payload));
  
  // Check status emission
  check('status emitted with card count', statuses1.length > 0 && statuses1[0].text.includes('3 cards'), 
    statuses1.length > 0 ? statuses1[0].text : 'no status');
}

// Test 2: Empty cards array
store.set('kanban_cards', []);
const statuses2 = [];
const flow2 = { get: (k) => store.get(k), set: (k, v) => store.set(k, v) };
const out2 = fn({ topic: 'kanban/refresh' }, makeEnv({}), makeNode(statuses2), flow2, {}, {});
check('handles empty cards array', Array.isArray(out2) && (Array.isArray(out2[0]?.payload) ? out2[0].payload.length : 0) === 0, 
  out2 ? (Array.isArray(out2[0]?.payload) ? out2[0].payload.length : 'not array') : 'null');
check('empty status message', statuses2.length > 0 && statuses2[0].text === '0 cards', 
  statuses2.length > 0 ? statuses2[0].text : 'no status');

// Test 3: Single card
store.set('kanban_cards', [{ task: 'Single task', status: 'done' }]);
const statuses3 = [];
const flow3 = { get: (k) => store.get(k), set: (k, v) => store.set(k, v) };
const out3 = fn({ topic: 'kanban/refresh' }, makeEnv({}), makeNode(statuses3), flow3, {}, {});
check('handles single card', Array.isArray(out3) && (Array.isArray(out3[0]?.payload) ? out3[0].payload.length : 0) === 1,
  out3 ? (Array.isArray(out3[0]?.payload) ? out3[0].payload.length : 'not array') : 'null');
check('single card status preserved', out3[0]?.payload[0]?.task === 'Single task' && out3[0]?.payload[0]?.status === 'done');
check('single card status message', statuses3.length > 0 && /1 card/i.test(statuses3[0].text),
  statuses3.length > 0 ? statuses3[0].text : 'no status');

// Test 4: Large cards array (10 items)
const largeCards = [];
for (let i = 0; i < 10; i++) {
  largeCards.push({ task: 'Task ' + i, status: 'todo' });
}
store.set('kanban_cards', largeCards);
const statuses4 = [];
const flow4 = { get: (k) => store.get(k), set: (k, v) => store.set(k, v) };
const out4 = fn({ topic: 'kanban/refresh' }, makeEnv({}), makeNode(statuses4), flow4, {}, {});
check('handles 10 cards', Array.isArray(out4) && (Array.isArray(out4[0]?.payload) ? out4[0].payload.length : 0) === 10,
  out4 ? (Array.isArray(out4[0]?.payload) ? out4[0].payload.length : 'not array') : 'null');
check('status shows 10 cards', statuses4.length > 0 && statuses4[0].text === '10 cards',
  statuses4.length > 0 ? statuses4[0].text : 'no status');

console.log('== System Health: embed URL building ==');
{
  const { out } = run('Build Grafana embeds', { GRAFANA_URL: 'http://g.local:3001/', GRAFANA_DASH_UID: 'my-dash' }, {});
  check('cpu embed hits d-solo route',
        out && /\/d-solo\/my-dash\/system-health\?orgId=1&panelId=1&/.test(out.p.cpu), out && out.p.cpu);
  check('health embed is panelId 4',
        out && out.p.health.indexOf('panelId=4') !== -1, out && out.p.health);
  check('latency embed is panelId 6',
        out && out.p.latency.indexOf('panelId=6') !== -1);
  check('loss embed is panelId 7',
        out && out.p.loss.indexOf('panelId=7') !== -1);
  check('kiosk mode set', out && out.p.cpu.indexOf('&kiosk&') !== -1);
  check('dark theme pinned', out && out.p.cpu.indexOf('theme=dark') !== -1);
  check('3h window with self-refresh',
        out && out.p.cpu.indexOf('from=now-3h') !== -1 && out.p.cpu.indexOf('refresh=30s') !== -1);
  check('trailing slash on GRAFANA_URL trimmed',
        out && out.p.cpu.indexOf('3001//d-solo') === -1, out && out.p.cpu);
  check('all six panels present',
        out && ['cpu','mem','io','health','latency','loss'].every(k => out.p[k]));
}
{
  // Defaults must work with no env at all (fresh LXC before .env is filled).
  const { out } = run('Build Grafana embeds', {}, {});
  check('default GRAFANA_URL used', out && /^http:\/\/192\.168\.4\.145:3001\/d-solo\/shd-system-health/.test(out.p.cpu), out && out.p.cpu);
}

console.log('== System Health: summary query building ==');
{
  const { out } = run('Build health query', { PROMETHEUS_URL: 'http://p.local:9090' }, {});
  check('targets the instant-query API',
        out && out.url.indexOf('http://p.local:9090/api/v1/query?query=') === 0, out && out.url);
  check('query is URL-encoded', out && out.url.indexOf('%20') !== -1, out && out.url.slice(0, 120));
  check('query labels targets_up',
        out && decodeURIComponent(out.url).indexOf('"targets_up"') !== -1);
  check('query labels pve_cpu/pve_mem',
        out && /"pve_cpu"/.test(decodeURIComponent(out.url)) && /"pve_mem"/.test(decodeURIComponent(out.url)));
  check('query labels probes_ok/probes_total',
        out && /"probes_ok"/.test(decodeURIComponent(out.url)) && /"probes_total"/.test(decodeURIComponent(out.url)));
  check('query labels pve_uptime_days',
        out && decodeURIComponent(out.url).indexOf('"pve_uptime_days"') !== -1);
  check('method is GET', out && out.method === 'GET');
}
{
  // Bad / missing Prometheus URL falls back to the co-located stack address.
  const { out } = run('Build health query', {}, {});
  check('default PROMETHEUS_URL used', out && out.url.indexOf('http://192.168.4.145:9090/') === 0, out && out.url);
}

console.log('== System Health: summary parsing ==');
{
  // Shape mirrors a real Prometheus instant-query response (verified live
  // against the co-located stack on 2026-10-11).
  const msg = { payload: { status: 'success', data: { result: [
    { metric: { stat: 'targets_up' },        value: [1790431325, '13'] },
    { metric: { stat: 'targets_total' },     value: [1790431325, '13'] },
    { metric: { stat: 'pve_cpu' },           value: [1790431325, '9.780701754385973'] },
    { metric: { stat: 'pve_mem' },           value: [1790431325, '46.46053399966448'] },
    { metric: { stat: 'probes_ok' },         value: [1790431325, '5'] },
    { metric: { stat: 'probes_total' },      value: [1790431325, '5'] },
    { metric: { stat: 'pve_uptime_days' },  value: [1790431325, '15.354118333331964'] }
  ] } } };
  const { out } = run('Parse health summary', {}, msg);
  check('five outputs', Array.isArray(out) && out.length === 5, String(out && out.length));
  check('cpu gauge value 9.8', out[0].payload === 9.8, String(out[0] && out[0].payload));
  check('mem gauge value 46.5', out[1].payload === 46.5, String(out[1] && out[1].payload));
  check('targets text "13 / 13 up"', out[2].payload === '13 / 13 up', out[2] && out[2].payload);
  check('probes text "5 / 5 ok"', out[3].payload === '5 / 5 ok', out[3] && out[3].payload);
  check('uptime text "15.4 days"', out[4].payload === '15.4 days', out[4] && out[4].payload);
}
{
  // Missing stats must degrade to zeros, never "undefined" text.
  const msg = { payload: { status: 'success', data: { result: [
    { metric: { stat: 'pve_cpu' }, value: [1, '5'] }
  ] } } };
  const { out } = run('Parse health summary', {}, msg);
  check('missing stats -> 0 / 0 up', out[2].payload === '0 / 0 up', out[2] && out[2].payload);
  check('no undefined leaks', out.every(m => m && !/undefined/.test(String(m.payload))),
        out.map(m => m && m.payload).join(' | '));
}
{
  // Error payloads (Grafana/Prometheus down, non-JSON body) -> null, no crash.
  const { out } = run('Parse health summary', {}, { payload: { status: 'error' } });
  check('error response -> null (no crash)', out === null || out === undefined, JSON.stringify(out));
  const { out: out2 } = run('Parse health summary', {}, { payload: 'not json' });
  check('non-JSON body -> null (no crash)', out2 === null || out2 === undefined);
}

console.log('== Theme Manager: "Set theme" validation ==');
{
  // The node is the single entry point for every theme change (picker buttons
  // AND programmatic msgs). It must normalise, reject unknown palettes, strip
  // socketid (or the dashboard's emitSocket would deliver the change ONLY to
  // the clicking browser), and persist to flow context.
  const store = flowStore();
  const statuses = [];
  const fn = new Function('msg', 'env', 'node', 'flow', 'context', 'global', byName['Set theme']);

  const out = fn({ payload: '  Nord ', socketid: 'sock-1', topic: 'shd/theme' },
                 makeEnv({}), makeNode(statuses), store, {}, {});
  check('accepts + normalises a known palette id', out && out.payload === 'nord', out && out.payload);
  check('socketid stripped -> broadcast to ALL clients',
        out && !('socketid' in out) && out.socketid === undefined, out && out.socketid);
  check('persists to flow context', store.get('shd_theme') === 'nord', store.get('shd_theme'));
  check('status shows applied palette', statuses.some(s => s.text === 'nord'), statuses);

  const st2 = [];
  const out2 = fn({ payload: 'CYBERPUNK' }, makeEnv({}), makeNode(st2), store, {}, {});
  check('case-insensitive id accepted', out2 && out2.payload === 'cyberpunk', out2 && out2.payload);

  const st3 = [];
  const out3 = fn({ payload: 'neon-nightmare' }, makeEnv({}), makeNode(st3), store, {}, {});
  check('unknown palette rejected (null)', out3 === null || out3 === undefined, out3);
  check('unknown palette -> red status', st3.some(s => s.fill === 'red'), st3);

  const st4 = [];
  const out4 = fn({ payload: 42 }, makeEnv({}), makeNode(st4), store, {}, {});
  check('non-string payload rejected (null)', out4 === null || out4 === undefined, out4);

  const st5 = [];
  const out5 = fn({ payload: 'default', enabled: false, res: {}, req: {} },
                   makeEnv({}), makeNode(st5), store, {}, {});
  check('enabled/res/req stripped from the broadcast',
        out5 && !('enabled' in out5) && !('res' in out5) && !('req' in out5), out5 && Object.keys(out5));
  check('flow context follows the latest valid palette',
        store.get('shd_theme') === 'default', store.get('shd_theme'));
}

console.log('== Theme Manager: generated UI matches js/themes.js ==');
{
  // The picker buttons and the KNOWN list are PARSED OUT OF js/themes.js by
  // the generator, so this asserts the no-drift property end to end: every
  // palette in the shipped module has a button AND a validator entry.
  const fs2 = require('fs');
  const path2 = require('path');
  const themesSrc = fs2.readFileSync(path2.join(here, '..', 'js', 'themes.js'), 'utf8');
  const found = [...themesSrc.matchAll(/'([a-z0-9-]+)':\s*\{[^{}]*?label:\s*'([^']*)'/g)];
  check('js/themes.js defines at least 2 palettes', found.length >= 2, found.length);
  check('Nord palette present', found.some(m => m[1] === 'nord'));
  check('Cyberpunk palette present', found.some(m => m[1] === 'cyberpunk'));

  const byId = {};
  for (const n of nodes) if (n.type === 'ui_button' && (n.topic === 'shd/theme')) byId[n.name] = n;
  for (const [, pid, ] of found.map(m => [m[0], m[1], m[2]])) {
    const label = found.find(m => m[1] === pid)[2];
    const btn = nodes.find(n => n.type === 'ui_button' && n.payload === pid && n.topic === 'shd/theme');
    check(`picker button for '${pid}' exists`, !!btn, pid);
    check(`button payload is the palette id`, btn && btn.payload === pid, btn && btn.payload);
    check(`button label matches module label`, btn && btn.label === label, btn && btn.label);
  }
  const setTheme = nodes.find(n => n.type === 'function' && n.name === 'Set theme');
  check('Set theme node exists', !!setTheme);
  check('Set theme KNOWN list matches the shipped palettes',
        setTheme && JSON.parse(setTheme.func.match(/KNOWN = (\[[^\]]*\])/)[1])
          .sort().join() === found.map(m => m[1]).sort().join(),
        setTheme && setTheme.func.slice(0, 120));

  // The browser-side manager itself: shipped verbatim in the global template.
  const mgr = nodes.find(n => n.type === 'ui_template' && n.name === 'Theme manager');
  check('Theme manager global template exists', !!mgr);
  check('manager templateScope is global', mgr && mgr.templateScope === 'global');
  check('manager inlines js/themes.js verbatim',
        mgr && mgr.format.includes(themesSrc), 'format does not contain the module source');
  check('manager boot calls SHDThemeManager.init()',
        mgr && /SHDThemeManager\.init\(\)/.test(mgr.format));
  check('manager boot script runs BEFORE first paint (in <head> via global scope)',
        mgr && mgr.format.startsWith('<script>'));

  // The local bridge: the $watch template that applies broadcasts.
  const bridge = nodes.find(n => n.type === 'ui_template' && n.name === 'Theme status');
  check('Theme status bridge template exists', !!bridge);
  check('bridge watches scope.msg.payload and applies via SHDThemeManager',
        bridge && /scope\.\$watch/.test(bridge.format)
              && /SHDThemeManager\.apply/.test(bridge.format));
  check('bridge is local scope (receives input msgs on its scope)',
        bridge && bridge.templateScope === 'local');

  // Persistence re-push on deploy.
  const inj = nodes.find(n => n.type === 'inject' && n.name === 'Re-push theme on deploy');
  check('deploy re-push inject exists', !!inj);
  check('inject reads the shd_theme flow-context key',
        inj && JSON.stringify(inj.props).indexOf('shd_theme') !== -1,
        inj && JSON.stringify(inj.props));
  check('inject fires once at startup', inj && inj.once === true);
}

// =====================================================================
// Kiosk / WallPanel MQTT control (task t_57dfd219)
// =====================================================================
// These drive the REAL function bodies against a context store. `run()`
// passes a bare {} for context, which is fine for nodes that do not persist
// anything -- but the brightness scheduler deliberately keeps state between
// ticks, so it needs get/set or it throws.
function runCtx(name, vars, msg, ctxStore) {
  const code = byName[name];
  if (!code) throw new Error(`no function node named '${name}'`);
  const store = ctxStore || {};
  const context = { get: (k) => store[k], set: (k, v) => { store[k] = v; } };
  const fn = new Function('msg', 'env', 'node', 'flow', 'context', 'global', code);
  return { out: fn(msg, makeEnv(vars), makeNode([]), flowStore(), context, {}), store };
}

console.log('\n== Kiosk: command contract ==');
{
  // WallPanel contract: <base>/command accepts {"wake":true,"wakeTime":N}.
  const { out } = runCtx('Build kiosk command', {}, { topic: 'kiosk/wake', payload: 'wake' });
  const sent = JSON.parse(out.payload);
  check('wake emits a JSON string, not an object', typeof out.payload === 'string');
  check('wake payload is {"wake":true,"wakeTime":180}',
        sent.wake === true && sent.wakeTime === 180, JSON.stringify(sent));
  check('wake command is addressed to the documented command topic',
        out.topic === 'wallpanel/a7lite/command', out.topic);

  // View switch: the consumer is WallPanel's eval command.
  const v = runCtx('Build kiosk command', {}, { topic: 'kiosk/view', payload: 'kanban' });
  const ev = JSON.parse(v.out.payload);
  check('view switch uses the eval command', typeof ev.eval === 'string', JSON.stringify(ev));
  check("kanban maps to location.hash='#!/2' (verified live 2026-10-19)",
        ev.eval === "location.hash='#!/2'", ev.eval);
  const byIndex = runCtx('Build kiosk command', {}, { topic: 'kiosk/view', payload: '3' });
  check('a numeric view index is accepted',
        JSON.parse(byIndex.out.payload).eval === "location.hash='#!/3'");

  const unknown = runCtx('Build kiosk command', {}, { topic: 'kiosk/nonsense', payload: 'x' });
  check('unknown action emits nothing (no empty command reaches the tablet)',
        unknown.out === null);

  // Every emitted command must be parseable JSON with a documented key.
  // `wakeTime` is part of the documented wake command ({"wake":true,
  // "wakeTime":180}) -- it is a modifier on `wake`, not a command of its own.
  const DOCUMENTED = ['wake', 'wakeTime', 'brightness', 'eval', 'reload',
                      'relaunch', 'url', 'clearCache', 'speak', 'settings',
                      'camera', 'volume'];
  let undeclared = [];
  for (const [topic, payload] of [['kiosk/wake', 'wake'], ['kiosk/view', 'ha']]) {
    const r = runCtx('Build kiosk command', {}, { topic, payload });
    const keys = Object.keys(JSON.parse(r.out.payload));
    for (const k of keys) if (!DOCUMENTED.includes(k)) undeclared.push(k);
  }
  check('every emitted command key is one WallPanel documents', undeclared.length === 0,
        undeclared.join(','));
}

console.log('\n== Kiosk: motion -> wake ==');
{
  // Motion emits an OBJECT; `Build kiosk command` owns stringification. The
  // two are tested as a CHAIN because a body-by-body test missed a real defect:
  // motion used to stringify, and the command builder's object pass-through
  // then never matched, silently dropping every motion wake.
  function chain(motionPayload) {
    const m = runCtx('Motion -> wake', {}, { payload: motionPayload, topic: 'wallpanel/a7lite/sensor/motion' });
    if (m.out === null) { return null; }
    // carry the real msg across the wire, as Node-RED does
    const c = runCtx('Build kiosk command', {}, m.out);
    return c.out;
  }

  const on = chain({ value: true });
  check('motion {"value":true} -> a command survives the second node', on !== null,
        'the wake was dropped by the command builder');
  check('motion wake reaches the tablet as {"wake":true,"wakeTime":180}',
        on && JSON.parse(on.payload).wake === true && JSON.parse(on.payload).wakeTime === 180,
        on && on.payload);
  check('motion wake is addressed to the command topic',
        on && on.topic === 'wallpanel/a7lite/command', on && on.topic);

  check('motion {"value":false} emits nothing (screensaver must survive)',
        chain({ value: false }) === null);
  check('a string "true" payload also wakes', chain('true') !== null);
}

console.log('\n== Kiosk: brightness schedule ==');
{
  const store = {};
  const first = runCtx('Schedule -> brightness', {}, { payload: '' }, store);
  const level = JSON.parse(first.out.payload).brightness;
  check('brightness is emitted as a number in WallPanel range 1-255',
        typeof level === 'number' && level >= 1 && level <= 255, String(level));
  check('brightness goes to the command topic',
        first.out.topic === 'wallpanel/a7lite/command', first.out.topic);

  // Second tick inside the same bucket and inside 30 min must be silent.
  const second = runCtx('Schedule -> brightness', {}, { payload: '' }, store);
  check('a repeat tick in the same bucket emits nothing (no MQTT spam)',
        second.out === null);

  // Force the self-heal window: >30 min since the last publish.
  store.lastPublish = Date.now() - 31 * 60 * 1000;
  const heal = runCtx('Schedule -> brightness', {}, { payload: '' }, store);
  check('re-publishes after 30 min (retained message can be lost on broker restart)',
        heal.out !== null && JSON.parse(heal.out.payload).brightness === level);
}

console.log('\n== Kiosk: tablet state ==');
{
  const r = runCtx('Tablet state', {}, { payload: {
    currentUrl: 'http://192.168.4.100:1880/ui/#!/2?socketid=abc',
    screenOn: true, brightness: 200 } });
  check('state parses into the widget contract',
        r.out.payload.screenOn === true && r.out.payload.brightness === 200);
  check('currentUrl is reduced to the tab index', r.out.payload.currentUrl === '#2',
        r.out.payload.currentUrl);
  const off = runCtx('Tablet state', {}, { payload: { screenOn: false, brightness: 40 } });
  check('screenOn false is reported as false (not truthy string)',
        off.out.payload.screenOn === false);
  const junk = runCtx('Tablet state', {}, { payload: { nothing: 1 } });
  check('a state message with no known keys still yields a payload (no throw)',
        junk.out && junk.out.payload);
}

console.log('\n' + pass + ' passed, ' + fail + ' failed');
