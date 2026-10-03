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
        "var base = env.get('PROXMOX_URL') || 'https://proxmox.local:8006';\n"
        "var node = env.get('PROXMOX_NODE') || 'pve';\n"
        "msg.method = 'GET';\n"
        "msg.url = base.replace(/\\/+$/, '') + '/api2/json/nodes/' + node + '/status';\n"
        "msg.headers = {};\n"
        "var tok = env.get('PROXMOX_TOKEN');\n"
        "if (tok) { msg.headers['Authorization'] = 'PVEAPIToken=' + tok; }\n"
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
        "if (msg.statusCode && msg.statusCode >= 200 && msg.statusCode < 300) {\n"
        "  node.status({fill:'green',shape:'dot',text:'ok'});\n"
        "  msg.payload = 'OK (' + msg.statusCode + ')';\n"
        "} else {\n"
        "  node.status({fill:'red',shape:'ring',text:'error'});\n"
        "  msg.payload = 'Error ' + (msg.statusCode || '') + ' ' + msg.payload;\n"
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
     "x": 150, "y": 120, "wires": [[nid("fn-u-build")]]})
add({"id": nid("fn-u-build"), "type": "function", "z": T, "name": "Build UniFi request",
     "func": (
        "// UniFi controller API -- credentials from env vars, never hardcoded.\n"
        "var base = env.get('UNIFI_URL') || 'https://unifi.local:8443';\n"
        "msg.method = 'GET';\n"
        "msg.url = base.replace(/\\/+$/, '') + '/api/s/default/stat/sta';\n"
        "msg.headers = {'Accept': 'application/json'};\n"
        "msg.rejectUnauthorized = false;\n"
        "node.status({fill:'blue',shape:'dot',text:'polling'});\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 360, "y": 120, "wires": [[nid("http-u")]]})
add({"id": nid("http-u"), "type": "http request", "z": T, "name": "UniFi API",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 570, "y": 120,
     "wires": [[nid("json-u")]]})
add({"id": nid("json-u"), "type": "json", "z": T, "name": "Parse",
     "property": "payload", "action": "obj", "pretty": False,
     "x": 730, "y": 120, "wires": [[nid("fn-u-parse")]]})
add({"id": nid("fn-u-parse"), "type": "function", "z": T, "name": "Split client data",
     "func": (
        "var rows = [];\n"
        "var data = msg.payload && msg.payload.data ? msg.payload.data : [];\n"
        "data.forEach(function (c) {\n"
        "  rows.push({hostname: c.hostname || c.name || c.mac, "
        "ip: c.ip || '', mac: c.mac || ''});\n"
        "});\n"
        "node.status({fill:'green',shape:'dot',text:rows.length + ' clients'});\n"
        "return [ {payload: rows.length}, {payload: rows} ];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 900, "y": 120, "wires": [[nid("txt-clients")], [nid("tbl-clients")]]})

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
     "props": [{"p": "payload"}], "repeat": "", "crontab": "", "once": True,
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
     "props": [{"name": "payload", "value": "Smart Home Dashboard\\nNode-RED flows deployed.\\n\\nSet credentials in the LXC env:\\nPROXMOX_URL, PROXMOX_TOKEN, HUBITAT_APP_ID, HUBITAT_ACCESS_TOKEN, HUBITAT_DEVICE_ID, UNIFI_URL", "vt": "str"}],
     "repeat": "", "crontab": "", "once": True, "onceDelay": 2.0, "topic": "",
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
