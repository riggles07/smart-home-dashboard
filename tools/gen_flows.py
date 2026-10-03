#!/usr/bin/env python3
"""
Generate real Node-RED flows (Path B) for the Smart Home Dashboard.

Produces flow JSON containing ACTUAL node instances (tabs, dashboard widgets,
inject/function/http-request/debug) -- not custom node-type definitions.

All node types used are verified present in the live palette
(/tmp/nr-types.txt, pulled from http://sh-dashboard:1880/nodes).

Credentials are NEVER hardcoded: function nodes read them from env vars
(PROXMOX_URL / PROXMOX_TOKEN / HUBITAT_* / UNIFI_*).
"""
import json, os, hashlib

OUT = "/root/.hermes/projects/smart-home-dashboard/flows"

def _id(seed):
    """Deterministic 16-hex-char node id."""
    return hashlib.sha1(seed.encode()).hexdigest()[:16]

def nid(seed):
    return _id(seed)

flows_all = []

def add(*nodes):
    flows_all.extend(nodes)

# ---------------------------------------------------------------- Global theming
#
# The legacy node-red-dashboard has NO `css:` setting. Verified against the
# bundled README: the only documented settings are
#   ui.path / ui.middleware / ui.ioMiddleware / ui.readOnly / ui.defaultGroup
# and theme/layout live in the `ui_base` (UI Settings) config node, not here.
# `config/settings.js` therefore cannot apply css/dashboard.css, and it is not
# served over HTTP (httpStatic is unset) -- so a <link> would 404.
#
# The working, dependency-free route is to INLINE the theme into a ui_template
# on an invisible ui_group. A ui_template renders into the page, so a <style>
# block inside it applies globally, and the dashboard pushes it over the
# existing websocket -- no extra HTTP plumbing required.
THEME_CSS_PATH = "/root/.hermes/projects/smart-home-dashboard/css/dashboard.css"


def load_theme_css(path=THEME_CSS_PATH):
    """Inline the theme, stripping anything that could break the <style> block."""
    with open(path) as fh:
        css = fh.read()
    # A stray "</style" would terminate the block early and spill CSS as text.
    css = css.replace("</style", "<\\/style")
    # Strip comments: they carry no runtime value and keep the node compact.
    while "/*" in css and "*/" in css:
        a = css.index("/*")
        b = css.index("*/", a) + 2
        css = css[:a] + css[b:]
    return css


# The dashboard ships its own rule:
#     body.nr-dashboard-theme { background-color: #eee; ... }
# Specificity (0,1,1) beats the theme's plain `body {...}` (0,0,1) REGARDLESS of
# source order, so the theme's dark background silently loses and the page paints
# light while the text colour flips to #eee -- unreadable. Re-assert the page
# colours at the SAME specificity (injected later, so it wins on the tie) instead
# of reaching for !important, which would also stomp the dashboard's widget themes.
#
# Measured in the live UI (Node-RED 5.0.7 + legacy dashboard 3.6.6), the theme's
# own `.ui_tab .tab-link` rule matches NOTHING -- those classes are not in this
# version's DOM. Tab entries render as `md-list-item` (48px, fine) and the toolbar
# hamburger as `button.md-icon-button` (40px, UNDER the 44px target). Target the
# selectors that actually exist; the extra `body.nr-dashboard-theme` qualifier
# also lifts specificity above Angular Material's own rules.
THEME_OVERRIDE = """
body.nr-dashboard-theme {
  background: var(--shd-bg);
  color: var(--shd-text);
}

/* ------------------------------------------------------------------
   The dashboard's own theme block defines the --nr-dashboard-* variables
   but then PAINTS its primary surfaces with hardcoded colours that ignore
   them. Measured in dashboard 3.6.6 (selector -> colour):
     body.nr-dashboard-theme md-content md-card   -> #fff
     .nr-dashboard-theme ui-card-panel            -> #fff
     body.nr-dashboard-theme md-toolbar           -> #0094CE
     body.nr-dashboard-theme md-sidenav           -> #eee
   Overriding only the variables therefore darkens :root while the page
   still renders light. These rules match or exceed each original's
   specificity, and this block is injected last, so ties resolve here.
   Deliberately not !important: nothing here is inline, and !important
   would also defeat the dashboard's later runtime theming.
   ------------------------------------------------------------------ */
body.nr-dashboard-theme md-content md-card {
  background: var(--shd-card);
  color: var(--shd-text);
}
body.nr-dashboard-theme ui-card-panel {
  background: var(--shd-card);
  color: var(--shd-text);
}
body.nr-dashboard-theme md-toolbar {
  background: var(--shd-surface);
  color: var(--shd-text);
}
body.nr-dashboard-theme md-sidenav {
  background: var(--shd-surface);
  color: var(--shd-text);
}

/* Tab drawer entries and the toolbar button are Angular Material elements,
   not `.ui_tab .tab-link` (which matches nothing in this version). The
   toolbar button measured 40px -- under the 44px touch target. */
body.nr-dashboard-theme md-sidenav md-list-item,
body.nr-dashboard-theme md-sidenav .md-button {
  min-height: var(--shd-touch-target);
  touch-action: manipulation;
}
body.nr-dashboard-theme md-sidenav md-list-item p,
body.nr-dashboard-theme md-sidenav .md-button {
  color: var(--shd-text);
}
body.nr-dashboard-theme button.md-icon-button,
body.nr-dashboard-theme .md-icon-button {
  min-height: var(--shd-touch-target);
  min-width: var(--shd-touch-target);
  touch-action: manipulation;
  color: var(--shd-text);
}

/* Charts/gauge/template content the dashboard paints on its own light panel. */
body.nr-dashboard-theme md-card .nr-dashboard-text,
body.nr-dashboard-theme md-card table,
body.nr-dashboard-theme md-card th,
body.nr-dashboard-theme md-card td {
  color: var(--shd-text);
}
body.nr-dashboard-theme md-card th {
  border-bottom-color: var(--shd-accent);
}
"""


_theme_css = load_theme_css()
T = nid("tab-homelab")
add({"id": nid("uitab-theme"), "type": "ui_tab", "z": T, "name": "Theme",
     "icon": "paint-brush", "order": 99, "disabled": False, "hidden": True})
_TG = nid("grp-theme")
add({"id": _TG, "type": "ui_group", "z": T, "name": "Theme",
     "tab": nid("uitab-theme"), "order": 1, "disp": True, "width": "12",
     "collapse": False})
add({"id": nid("tpl-theme"), "type": "ui_template", "z": T, "name": "Mobile theme",
     "group": _TG, "order": 1, "width": "0", "height": "0",
     "format": "<style>\n" + _theme_css + "\n" + THEME_OVERRIDE + "</style>",
     "storeOutMessages": False, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "global", "x": 130, "y": 900, "wires": [[]]})

# ---------------------------------------------------------------- Tab 1: Home Lab
T = nid("tab-homelab")
add({"id": T, "type": "tab", "label": "Home Lab", "disabled": False, "info": ""})
add({"id": nid("uitab-h"), "type": "ui_tab", "z": T, "name": "Home Lab",
     "icon": "dashboard", "order": 1, "disabled": False, "hidden": False})
G = nid("grp-pve")
add({"id": G, "type": "ui_group", "z": T, "name": "Proxmox Host",
     "tab": nid("uitab-h"), "order": 1, "disp": True, "width": "6", "collapse": False})

add({"id": nid("gg-cpu"), "type": "ui_gauge", "z": T, "name": "Proxmox CPU",
     "group": G, "order": 1, "width": "6", "height": "4", "gtype": "gage",
     "title": "CPU", "label": "%", "format": "{{value}}", "min": 0, "max": "100",
     "colors": ["#00b500", "#e6e600", "#ca3838"], "seg1": "", "seg2": "",
     "x": 640, "y": 120, "wires": []})
add({"id": nid("gg-mem"), "type": "ui_gauge", "z": T, "name": "Proxmox Memory",
     "group": G, "order": 2, "width": "6", "height": "4", "gtype": "gage",
     "title": "Memory", "label": "%", "format": "{{value}}", "min": 0, "max": "100",
     "colors": ["#00b500", "#e6e600", "#ca3838"], "seg1": "", "seg2": "",
     "x": 640, "y": 220, "wires": []})
add({"id": nid("txt-status"), "type": "ui_text", "z": T, "name": "Host Status",
     "group": G, "order": 3, "width": "6", "height": "2",
     "label": "Status", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 320, "wires": []})
add({"id": nid("ch-cpu"), "type": "ui_chart", "z": T, "name": "CPU History",
     "group": G, "order": 4, "width": "6", "height": "5", "label": "CPU %",
     "chartType": "line", "legend": "false", "xformat": "HH:mm:ss",
     "interpolate": "linear", "nodata": "", "dot": False, "ymin": "0", "ymax": "100",
     "removeOlder": "5", "removeOlderPoints": "", "removeOlderUnit": "60",
     "cutout": 0, "useOneColor": False, "colors": ["#1f77b4", "#aec7e8"],
     "x": 650, "y": 420, "wires": []})

add({"id": nid("inj-h"), "type": "inject", "z": T, "name": "Every 30s",
     "props": [{"p": "payload"}], "repeat": "30", "crontab": "", "once": True,
     "onceDelay": 0.5, "topic": "", "payload": "", "payloadType": "date",
     "x": 150, "y": 120, "wires": [[nid("fn-h-build")]]})
add({"id": nid("fn-h-build"), "type": "function", "z": T, "name": "Build Proxmox request",
     "func": (
        "// Credentials come from env vars -- never hardcoded.\n"
        "var base = env.get('PROXMOX_URL');\n"
        "var tok  = env.get('PROXMOX_TOKEN');\n"
        "if (!base || !tok) {\n"
        "  node.status({fill:'red',shape:'ring',text:'missing config'});\n"
        "  return null;\n"
        "}\n"
        "var node = env.get('PROXMOX_NODE') || 'pve';\n"
        "msg.method = 'GET';\n"
        "msg.url = base.replace(/\\/+$/, '') + '/api2/json/nodes/' + node + '/status';\n"
        "msg.headers = {};\n"
        "msg.headers['Authorization'] = 'PVEAPIToken=' + tok;\n"
        "msg.rejectUnauthorized = false;\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 360, "y": 120, "wires": [[nid("http-h")]]})
add({"id": nid("http-h"), "type": "http request", "z": T, "name": "Proxmox API",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 570, "y": 120,
     "wires": [[nid("json-h")]]})
add({"id": nid("json-h"), "type": "json", "z": T, "name": "Parse",
     "property": "payload", "action": "obj", "pretty": False,
     "x": 730, "y": 120, "wires": [[nid("fn-h-parse")]]})
add({"id": nid("fn-h-parse"), "type": "function", "z": T, "name": "Split metrics",
     "func": (
        "var d = (msg.payload && msg.payload.data) ? msg.payload.data : null;\n"
        "if (!d) { node.status({fill:'red',shape:'ring',text:'no data'}); return null; }\n"
        "var cpu = Math.round((d.cpu || 0) * 1000) / 10;\n"
        "var memUsed = (d.memory && d.memory.used) || 0;\n"
        "var memTot = (d.memory && d.memory.total) || 1;\n"
        "var mem = Math.round(memUsed / memTot * 1000) / 10;\n"
        "var up = d.uptime || 0;\n"
        "var days = Math.floor(up / 86400), hrs = Math.floor((up % 86400) / 3600);\n"
        "node.status({fill:'green',shape:'dot',text:cpu + '% cpu'});\n"
        "var mCpu = {payload: cpu};\n"
        "var mMem = {payload: mem};\n"
        "var mStat = {payload: 'Up ' + days + 'd ' + hrs + 'h' + "
        "(d.loadavg ? ' | load ' + (Math.round(d.loadavg[0]*100)/100) : '')};\n"
        "var mChart = {payload: cpu, topic: 'cpu'};\n"
        "return [mCpu, mMem, mStat, mChart];"
     ),
     "outputs": 4, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 900, "y": 120,
     "wires": [[nid("gg-cpu")], [nid("gg-mem")], [nid("txt-status")], [nid("ch-cpu")]]})
add({"id": nid("dbg-h"), "type": "debug", "z": T, "name": "Proxmox raw",
     "active": True, "tosidebar": True, "console": False, "tostatus": False,
     "complete": "payload", "targetType": "msg", "statusVal": "", "statusType": "auto",
     "x": 740, "y": 200, "wires": []})

# ---------------------------------------------------------------- Tab 2: Hubitat Devices
T = nid("tab-devices")
add({"id": T, "type": "tab", "label": "Devices", "disabled": False, "info": ""})
add({"id": nid("uitab-d"), "type": "ui_tab", "z": T, "name": "Devices",
     "icon": "lightbulb-o", "order": 2, "disabled": False, "hidden": False})
G = nid("grp-devs")
add({"id": G, "type": "ui_group", "z": T, "name": "Device Control",
     "tab": nid("uitab-d"), "order": 1, "disp": True, "width": "6", "collapse": False})

add({"id": nid("sw-power"), "type": "ui_switch", "z": T, "name": "Power",
     "label": "Power", "tooltip": "", "group": G, "order": 1, "width": 0, "height": 0,
     "passthru": True, "decouple": "false", "topic": "hubitat/power", "topicType": "str",
     "style": "", "onvalue": "true", "onvalueType": "bool", "onicon": "", "oncolor": "",
     "offvalue": "false", "offvalueType": "bool", "officon": "", "offcolor": "",
     "x": 130, "y": 120, "wires": [[nid("fn-d-cmd")]]})
add({"id": nid("sl-level"), "type": "ui_slider", "z": T, "name": "Brightness",
     "label": "Brightness", "tooltip": "", "group": G, "order": 2, "width": 0, "height": 0,
     "passthru": True, "outs": "all", "topic": "hubitat/level", "topicType": "str",
     "min": 0, "max": "100", "step": 1, "x": 130, "y": 220, "wires": [[nid("fn-d-cmd")]]})
add({"id": nid("txt-dev"), "type": "ui_text", "z": T, "name": "Last Result",
     "group": G, "order": 3, "width": "6", "height": "2",
     "label": "Result", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 320, "wires": []})

add({"id": nid("fn-d-cmd"), "type": "function", "z": T, "name": "Build Maker API call",
     "func": (
        "// Hubitat Maker API: GET /apps/api/<appId>/devices/<devId>/<cmd>/<value>?access_token=<tok>\n"
        "var base = env.get('HUBITAT_URL') || 'http://hubitat.local';\n"
        "var app  = env.get('HUBITAT_APP_ID') || '';\n"
        "var tok  = env.get('HUBITAT_ACCESS_TOKEN') || env.get('HUBITAT_API_KEY') || '';\n"
        "var dev  = env.get('HUBITAT_DEVICE_ID') || '';\n"
        "if (!app || !tok || !dev) {\n"
        "  node.status({fill:'red',shape:'ring',text:'missing config'});\n"
        "  msg.payload = 'Set HUBITAT_APP_ID, HUBITAT_ACCESS_TOKEN and HUBITAT_DEVICE_ID in the LXC env';\n"
        "  return [null, msg];\n"
        "}\n"
        "var cmd, val = null;\n"
        "if (msg.topic === 'hubitat/power') { cmd = msg.payload ? 'on' : 'off'; }\n"
        "else if (msg.topic === 'hubitat/level') { cmd = 'setLevel'; val = msg.payload; }\n"
        "else { node.status({fill:'grey',shape:'ring',text:'ignored'}); return null; }\n"
        "var url = base.replace(/\\/+$/, '') + '/apps/api/' + app + '/devices/' + dev + '/' + cmd;\n"
        "if (val !== null) { url += '/' + val; }\n"
        "url += '?access_token=' + tok;\n"
        "msg.method = 'GET';\n"
        "msg.url = url;\n"
        "node.status({fill:'blue',shape:'dot',text:cmd});\n"
        "return [msg, null];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 360, "y": 170, "wires": [[nid("http-d")], [nid("txt-dev")]]})
add({"id": nid("http-d"), "type": "http request", "z": T, "name": "Hubitat Maker API",
     "method": "use", "ret": "txt", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 590, "y": 170,
     "wires": [[nid("fn-d-result")]]})
add({"id": nid("fn-d-result"), "type": "function", "z": T, "name": "Format result",
     "func": (
        "// http request sets msg.error on a transport failure.\n"
        "if (msg.error || !msg.statusCode) {\n"
        "  node.status({fill:'red',shape:'ring',text:'unreachable'});\n"
        "  msg.payload = 'ERROR: Hubitat unreachable (' + (msg.error || msg.payload || 'no response') + ')';\n"
        "  return msg;\n"
        "}\n"
        "if (msg.statusCode >= 200 && msg.statusCode < 300) {\n"
        "  node.status({fill:'green',shape:'dot',text:'ok'});\n"
        "  msg.payload = 'OK (' + msg.statusCode + ')';\n"
        "} else {\n"
        "  node.status({fill:'red',shape:'ring',text:'http ' + msg.statusCode});\n"
        "  var body = (typeof msg.payload === 'string') ? msg.payload : JSON.stringify(msg.payload);\n"
        "  msg.payload = 'ERROR HTTP ' + msg.statusCode + ': ' + String(body).slice(0, 200);\n"
        "}\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 790, "y": 170, "wires": [[nid("txt-dev")]]})

# ---------------------------------------------------------------- Tab 3: UniFi Network
T = nid("tab-network")
add({"id": T, "type": "tab", "label": "Network", "disabled": False, "info": ""})
add({"id": nid("uitab-u"), "type": "ui_tab", "z": T, "name": "Network",
     "icon": "wifi", "order": 3, "disabled": False, "hidden": False})
G = nid("grp-net")
add({"id": G, "type": "ui_group", "z": T, "name": "Network Overview",
     "tab": nid("uitab-u"), "order": 1, "disp": True, "width": "12", "collapse": False})

add({"id": nid("txt-clients"), "type": "ui_text", "z": T, "name": "Clients Online",
     "group": G, "order": 1, "width": "6", "height": "2",
     "label": "Clients", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 120, "wires": []})
TEMPLATE_CLIENTS = (
    "<table class='table' style='width:100%'>\n"
    "  <thead><tr><th>Client</th><th>IP</th><th>MAC</th></tr></thead>\n"
    "  <tbody>\n"
    "    <tr ng-repeat='c in msg.payload'>\n"
    "      <td>{{c.hostname}}</td><td>{{c.ip}}</td><td>{{c.mac}}</td>\n"
    "    </tr>\n"
    "  </tbody>\n"
    "</table>"
)
TEMPLATE_CARDS = (
    "<table class='table' style='width:100%'>\n"
    "  <thead><tr><th>Task</th><th>Status</th></tr></thead>\n"
    "  <tbody>\n"
    "    <tr ng-repeat='c in msg.payload'>\n"
    "      <td>{{c.task}}</td><td>{{c.status}}</td>\n"
    "    </tr>\n"
    "  </tbody>\n"
    "</table>"
)

add({"id": nid("tbl-clients"), "type": "ui_template", "z": T, "name": "Client List",
     "group": G, "order": 2, "width": "12", "height": "8",
     "format": TEMPLATE_CLIENTS, "storeOutMessages": True, "fwdInMessages": True,
     "resendOnRefresh": True, "templateScope": "local",
     "x": 650, "y": 220, "wires": [[]]})

add({"id": nid("inj-u"), "type": "inject", "z": T, "name": "Every 60s",
     "props": [{"p": "payload"}], "repeat": "60", "crontab": "", "once": True,
     "onceDelay": 1.0, "topic": "", "payload": "", "payloadType": "date",
     "x": 130, "y": 120, "wires": [[nid("fn-u-login")]]})

# Decide auth mode: API key (X-API-KEY) if set, else legacy cookie login.
# out0 -> cookie login, out1 -> straight to the stat endpoint.
add({"id": nid("fn-u-login"), "type": "function", "z": T, "name": "Build UniFi auth",
     "func": (
        "// UniFi controllers need auth. Credentials come from env vars.\n"
        "// UNIFI_URL may carry a path prefix: UniFi OS (UDM/Cloud Gateway) serves\n"
        "// the Network app under /proxy/network, self-hosted controllers do not.\n"
        "var base = env.get('UNIFI_URL');\n"
        "var site = env.get('UNIFI_SITE') || 'default';\n"
        "var key  = env.get('UNIFI_API_KEY');\n"
        "var user = env.get('UNIFI_USERNAME');\n"
        "var pass = env.get('UNIFI_PASSWORD');\n"
        "msg.rejectUnauthorized = false;\n"
        "msg.headers = {'Accept': 'application/json'};\n"
        "if (!base) {\n"
        "  node.status({fill:'red',shape:'ring',text:'no UNIFI_URL'});\n"
        "  return [null, {payload: [], topic: 'unifi/error', "
        "_error: 'UNIFI_URL is not set. Use https://<host>/proxy/network for a UniFi OS console, or https://<host>:8443 for a self-hosted controller'}];\n"
        "}\n"
        "base = base.replace(/\\/+$/, '');\n"
        "msg.url_stat = base + '/api/s/' + site + '/stat/sta';\n"
        "if (key) {\n"
        "  node.status({fill:'green',shape:'dot',text:'api key'});\n"
        "  msg.method = 'GET';\n"
        "  msg.url = msg.url_stat;\n"
        "  msg.headers['X-API-KEY'] = key;\n"
        "  // out1 is the API-key path and MUST still go through the HTTP request\n"
        "  // node. Returning it on out0 (the login path) sent it straight to the\n"
        "  // parser, which then read the inject's Date payload instead of client\n"
        "  // data and always rendered 0 clients. Both auth routes converge on the\n"
        "  // same HTTP node; out0 only differs in that it needs a login first.\n"
        "  return [null, msg];\n"
        "}\n"
        "if (!user || !pass) {\n"
        "  node.status({fill:'red',shape:'ring',text:'no credentials'});\n"
        "  return [null, {payload: [], topic: 'unifi/error', "
        "_error: 'Set UNIFI_API_KEY, or UNIFI_USERNAME + UNIFI_PASSWORD, in the service environment'}];\n"
        "}\n"
        "// Pick the login endpoint. A UniFi OS console (base carries\n"
        "// /proxy/network) authenticates at the console root via /api/auth/login;\n"
        "// self-hosted controllers use /api/login. UNIFI_LOGIN_URL overrides both.\n"
        "var login = env.get('UNIFI_LOGIN_URL');\n"
        "if (!login) {\n"
        "  login = base + '/api/login';\n"
        "  var m = base.match(/^(https?:\\/\\/[^\\/]+)\\/proxy\\/network/);\n"
        "  if (m) { login = m[1] + '/api/auth/login'; }\n"
        "}\n"
        "node.status({fill:'blue',shape:'dot',text:'logging in'});\n"
        "msg.method = 'POST';\n"
        "msg.url = login;\n"
        "msg.headers['Content-Type'] = 'application/json';\n"
        "msg.payload = JSON.stringify({username: user, password: pass, remember: true});\n"
        "return [msg, null];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     # out0 (login required) -> the login HTTP node.
     # out1 (API key, request already built) -> the SAME stat HTTP node the
     # login path reaches after Capture session. It must NOT go to the parser
     # directly -- that skipped the request entirely and always rendered 0
     # clients. `msg.url` is already set on both routes, and the http request
     # node is method:"use", so it honours whatever the function set.
     "x": 340, "y": 120,
     "wires": [[nid("http-u-login")], [nid("http-u-stat")]]})

add({"id": nid("http-u-login"), "type": "http request", "z": T, "name": "UniFi login",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 540, "y": 60,
     "wires": [[nid("fn-u-cookie")]]})
add({"id": nid("fn-u-cookie"), "type": "function", "z": T, "name": "Capture session",
     "func": (
        "// Carry the UniFi session cookie (or X-CSRF-Token on newer builds)\n"
        "// into the stat request.\n"
        "var h = msg.headers || {};\n"
        "var setCookie = h['set-cookie'] || h['Set-Cookie'];\n"
        "var cookie = null;\n"
        "if (Array.isArray(setCookie)) { setCookie = setCookie.join('; '); }\n"
        "if (setCookie) {\n"
        "  var part = String(setCookie).split(';')[0];\n"
        "  if (part) { cookie = part; }\n"
        "}\n"
        "if (!cookie) {\n"
        "  node.status({fill:'red',shape:'ring',text:'login failed'});\n"
        "  msg.payload = [];\n"
        "  msg.topic = 'unifi/error';\n"
        "  msg._error = 'UniFi login returned no session cookie (HTTP ' + (msg.statusCode || '?') + ')';\n"
        "  return msg;\n"
        "}\n"
        "node.status({fill:'green',shape:'dot',text:'session ok'});\n"
        "msg.method = 'GET';\n"
        "msg.url = msg.url_stat;\n"
        "msg.headers = {'Accept': 'application/json'};\n"
        "if (msg.csrfToken || (h['x-csrf-token'])) {\n"
        "  msg.headers['X-CSRF-Token'] = msg.csrfToken || h['x-csrf-token'];\n"
        "}\n"
        "msg.headers['Cookie'] = cookie;\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 730, "y": 60, "wires": [[nid("http-u-stat")]]})

add({"id": nid("http-u-stat"), "type": "http request", "z": T, "name": "UniFi clients",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 420, "y": 200,
     "wires": [[nid("fn-u-parse")]]})

add({"id": nid("fn-u-parse"), "type": "function", "z": T, "name": "Split client data",
     "func": (
        "// Handles both the success path and the config-error path.\n"
        "if (msg.topic === 'unifi/error' || msg._error) {\n"
        "  node.status({fill:'red',shape:'ring',text:'error'});\n"
        "  var errMsg = msg._error || String(msg.payload || '');\n"
        "  return [ {payload: 0}, {payload: 'ERROR: ' + errMsg} ];\n"
        "}\n"
        "var data = (msg.payload && msg.payload.data) ? msg.payload.data : [];\n"
        "var rows = [];\n"
        "data.forEach(function (c) {\n"
        "  rows.push({hostname: c.hostname || c.name || c.mac, "
        "ip: (c.ip || (c['ip'] || '')), mac: c.mac || ''});\n"
        "});\n"
        "node.status({fill:'green',shape:'dot',text:rows.length + ' clients'});\n"
        "return [ {payload: rows.length}, {payload: rows} ];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 900, "y": 300, "wires": [[nid("txt-clients")], [nid("tbl-clients")]]})

# ---------------------------------------------------------------- Tab 4: Kanban Board
T = nid("tab-kanban")
add({"id": T, "type": "tab", "label": "Kanban", "disabled": False, "info": ""})
add({"id": nid("uitab-k"), "type": "ui_tab", "z": T, "name": "Kanban",
     "icon": "tasks", "order": 4, "disabled": False, "hidden": False})
G = nid("grp-kan")
add({"id": G, "type": "ui_group", "z": T, "name": "Task Board",
     "tab": nid("uitab-k"), "order": 1, "disp": True, "width": "12", "collapse": False})

add({"id": nid("ti-task"), "type": "ui_text_input", "z": T, "name": "New task",
     "label": "New task", "tooltip": "", "group": G, "order": 1, "width": 0, "height": 0,
     "passthru": True, "mode": "text", "delay": 300, "topic": "kanban/new",
     "sendOnBlur": True, "className": "", "x": 130, "y": 120, "wires": [[nid("fn-k-add")]]})
add({"id": nid("btn-add"), "type": "ui_button", "z": T, "name": "Add",
     "group": G, "order": 2, "width": 0, "height": 0, "passthru": False,
     "label": "Add", "tooltip": "", "color": "", "bgcolor": "", "className": "",
     "icon": "", "payload": "", "payloadType": "str", "topic": "kanban/render",
     "topicType": "str", "x": 130, "y": 200, "wires": [[nid("fn-k-render")]]})
add({"id": nid("tbl-cards"), "type": "ui_template", "z": T, "name": "Cards",
     "group": G, "order": 3, "width": "12", "height": "8",
     "format": TEMPLATE_CARDS, "storeOutMessages": True, "fwdInMessages": True,
     "resendOnRefresh": True, "templateScope": "local",
     "x": 650, "y": 220, "wires": [[]]})

add({"id": nid("fn-k-add"), "type": "function", "z": T, "name": "Add card",
     "func": (
        "var task = (typeof msg.payload === 'string' ? msg.payload : '').trim();\n"
        "if (!task) { node.status({fill:'grey',shape:'ring',text:'empty'}); return null; }\n"
        "var cards = flow.get('kanban_cards') || [];\n"
        "cards.push({task: task, status: 'todo'});\n"
        "flow.set('kanban_cards', cards);\n"
        "node.status({fill:'green',shape:'dot',text:cards.length + ' cards'});\n"
        "msg.payload = cards;\n"
        "return [msg, msg];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "flow.set('kanban_cards', flow.get('kanban_cards') || []);",
     "finalize": "", "libs": [], "x": 350, "y": 120,
     "wires": [[nid("tbl-cards")], [nid("dbg-k")]]})
add({"id": nid("fn-k-render"), "type": "function", "z": T, "name": "Render board",
     "func": (
        "var cards = flow.get('kanban_cards') || [];\n"
        "node.status({fill:'blue',shape:'dot',text:cards.length + ' cards'});\n"
        "msg.payload = cards;\n"
        "return [msg, msg];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 350, "y": 200, "wires": [[nid("tbl-cards")], [nid("dbg-k")]]})
add({"id": nid("inj-k"), "type": "inject", "z": T, "name": "Load board",
     "props": [{"p": "payload"}], "repeat": "60", "crontab": "", "once": True,
     "onceDelay": 1.5, "topic": "", "payload": "", "payloadType": "date",
     "x": 140, "y": 280, "wires": [[nid("fn-k-render")]]})
add({"id": nid("dbg-k"), "type": "debug", "z": T, "name": "Cards",
     "active": True, "tosidebar": True, "console": False, "tostatus": False,
     "complete": "payload", "targetType": "msg", "statusVal": "", "statusType": "auto",
     "x": 570, "y": 320, "wires": []})

# ---------------------------------------------------------------- Tab 5: Settings
T = nid("tab-settings")
add({"id": T, "type": "tab", "label": "Settings", "disabled": False, "info": ""})
add({"id": nid("uitab-s"), "type": "ui_tab", "z": T, "name": "Settings",
     "icon": "cog", "order": 5, "disabled": False, "hidden": False})
G = nid("grp-set")
add({"id": G, "type": "ui_group", "z": T, "name": "System Info",
     "tab": nid("uitab-s"), "order": 1, "disp": True, "width": "6", "collapse": False})
add({"id": nid("txt-info"), "type": "ui_text", "z": T, "name": "Deployment Info",
     "group": G, "order": 1, "width": "6", "height": "4",
     "label": "Info", "format": "{{msg.payload}}", "layout": "row-left",
     "className": "", "x": 640, "y": 120, "wires": []})
add({"id": nid("inj-s"), "type": "inject", "z": T, "name": "Load info",
     # Inject property schema is {"p":<property>,"v":<value>,"vt":<type>} --
     # NOT {"name":...,"value":...}. The wrong keys are silently ignored, the
     # node falls back to payloadType, and the widget renders a timestamp (or
     # nothing) instead of the intended string.
     "props": [{"p": "payload", "v": "Smart Home Dashboard\nNode-RED flows deployed.\n\nSet credentials in the LXC env:\nPROXMOX_URL, PROXMOX_TOKEN, HUBITAT_APP_ID, HUBITAT_ACCESS_TOKEN, HUBITAT_DEVICE_ID, UNIFI_URL", "vt": "str"}],
     # repeat is REQUIRED, not cosmetic: a one-shot inject fires once at DEPLOY
     # time, so any browser that connects afterwards finds the widget empty. A
     # widget only shows data pushed after it subscribed, so every inject that
     # feeds a display must re-fire on an interval.
     "repeat": "300", "crontab": "", "once": True, "onceDelay": 2.0, "topic": "",
     "payload": "", "payloadType": "date", "x": 150, "y": 120, "wires": [[nid("txt-info")]]})

# ---------------------------------------------------------------- write files
os.makedirs(OUT, exist_ok=True)
files = {
    "01-home-lab-monitor.flow.json":   flows_all[:len([n for n in flows_all])],
}
# Split by tab for readability: group nodes by their tab id
by_tab = {}
for node in flows_all:
    if node["type"] == "tab":
        key = node["id"]
    else:
        key = node.get("z", "orphan")
    by_tab.setdefault(key, []).append(node)

labels = {
    nid("tab-homelab"): "01-home-lab-monitor.flow.json",
    nid("tab-devices"): "02-hubitat-devices.flow.json",
    nid("tab-network"): "03-unifi-network.flow.json",
    nid("tab-kanban"):  "04-kanban-board.flow.json",
    nid("tab-settings"):"05-settings.flow.json",
}
written = []
for tab_id, nodes in by_tab.items():
    fname = labels.get(tab_id, "99-other.flow.json")
    with open(os.path.join(OUT, fname), "w") as fh:
        json.dump(nodes, fh, indent=2)
    written.append((fname, len(nodes)))

# Also write one combined file for single-shot import
with open(os.path.join(OUT, "all-flows.flow.json"), "w") as fh:
    json.dump(flows_all, fh, indent=2)

print("Generated files in", OUT)
for fname, count in written:
    print(f"  {fname}: {count} nodes")
print(f"  all-flows.flow.json: {len(flows_all)} nodes total")

# validation against live palette
palette = set()
with open("/tmp/nr-types.txt") as fh:
    for line in fh:
        if line.strip():
            palette.add(line.strip())
used = sorted({n["type"] for n in flows_all})
missing = [t for t in used if t not in palette and t not in ("tab",)]
print("\nNode types used:", ", ".join(used))
if missing:
    print("MISSING FROM PALETTE:", ", ".join(missing))
else:
    print("OK: every node type used exists in the live palette")
