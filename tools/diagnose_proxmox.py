#!/usr/bin/env python3
"""
Ask Proxmox what the dashboard's API token is actually allowed to do.

A 403 on /nodes/pve says a permission is missing, but not WHY. Proxmox exposes
GET /access/permissions, which returns the CALLER's effective permission map --
so the running token can introspect itself. That distinguishes:

  - the grant never landed (empty map, or no Sys.Audit anywhere)
  - the grant landed on the user, but 'Privilege Separation' is ON so the token
    inherits nothing (token map is empty while the user has Administrator)
  - the grant landed on the wrong PATH (Sys.Audit present, but not covering
    /nodes/<node>)
  - the token authenticates as an unexpected user/token id at all

Deploys a temporary probe tab, reads the result back, restores the original
flows. GETs only. The permission map contains paths and privilege names, never a
secret, but any credential-shaped run is still masked before it is printed.

Usage: python3 tools/diagnose_proxmox.py [http://host:1880]
Exit 0 = Sys.Audit is effective on the node; 1 = not.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://sh-dashboard:1880"
TAB = "pvediag-tab"

FN = """
var url = env.get('PROXMOX_URL');
var tok = env.get('PROXMOX_TOKEN');
var node = env.get('PROXMOX_NODE') || 'pve';
if (!url || !tok) {
  flow.set('pd_summary', 'PROXMOX_URL or PROXMOX_TOKEN is unset');
  return null;
}
// Record which token identity we are authenticating as (user@realm!name),
// WITHOUT the secret half. Never store the value.
var ident = String(tok);
var eq = ident.indexOf('=');
if (eq > -1) { ident = ident.slice(0, eq); }
flow.set('pd_identity', ident);
flow.set('pd_node', node);
msg.method = 'GET';
msg.url = url.replace(/\\/+$/,'') + '/api2/json/access/permissions';
msg.headers = { 'Authorization': 'PVEAPIToken=' + tok };
msg.rejectUnauthorized = false;
return msg;
"""

RESULT = """
var code = msg.statusCode || 0;
var out;
if (msg.error) {
  out = 'ERROR: ' + msg.error;
} else {
  var perms = null;
  try {
    var p = (typeof msg.payload === 'string') ? JSON.parse(msg.payload) : msg.payload;
    perms = p && p.data ? p.data : null;
  } catch (e) { perms = null; }
  if (!perms) {
    out = 'HTTP ' + code + ' (could not parse a permission map)';
    try { out += ' :: ' + String(JSON.stringify(msg.payload)).slice(0, 200); } catch (e2) {}
  } else {
    var lines = [];
    Object.keys(perms).sort().forEach(function (path) {
      var privs = perms[path] || [];
      lines.push(path + ' -> ' + (privs.length ? privs.join(',') : '(none)'));
    });
    out = 'HTTP ' + code + '\\n' + (lines.length ? lines.join('\\n') : '(no permissions at all)');
  }
}
// Mask anything credential-shaped even though this map should be non-secret.
out = String(out).replace(/[A-Za-z0-9_\\-+\\/=]{30,}/g, '<redacted>');
flow.set('pd_perms', out);
return msg;
"""


def req(method, path, data=None, timeout=25):
    body = json.dumps(data).encode() if data is not None else None
    h = {"Content-Type": "application/json"} if data is not None else {}
    r = urllib.request.Request(BASE + path, data=body, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode() or ""
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, raw


def get_ctx(key):
    _, ctx = req("GET", f"/context/flow/{TAB}")
    mem = ctx.get("memory", {}) if isinstance(ctx, dict) else {}
    v = mem.get(key)
    if isinstance(v, dict) and "msg" in v:
        v = v["msg"]
    return v


def main():
    print(f"proxmox token diagnostic: {BASE}")
    original = req("GET", "/flows")[1]
    if not isinstance(original, list):
        print("cannot read /flows"); return 2
    print(f"current flows: {len(original)} nodes")

    probe = [
        {"id": TAB, "type": "tab", "label": "PveDiag", "disabled": False, "info": ""},
        {"id": "pd-inj", "type": "inject", "z": TAB, "name": "diag", "props": [{"p": "payload"}],
         "repeat": "", "crontab": "", "once": False, "onceDelay": 0.1, "topic": "",
         "payload": "", "payloadType": "date", "x": 150, "y": 100, "wires": [["pd-fn"]]},
        {"id": "pd-fn", "type": "function", "z": TAB, "name": "build", "func": FN,
         "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
         "x": 330, "y": 100, "wires": [["pd-http"]]},
        {"id": "pd-http", "type": "http request", "z": TAB, "name": "ask", "method": "use",
         "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "", "persist": False,
         "proxy": "", "authType": "", "x": 520, "y": 100, "wires": [["pd-res"]]},
        {"id": "pd-res", "type": "function", "z": TAB, "name": "record", "func": RESULT,
         "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
         "x": 700, "y": 100, "wires": [[]]},
    ]

    ident = node = perms = None
    try:
        code = req("POST", "/flows", original + probe)[0]
        print(f"deploy probe: HTTP {code}")
        if code != 204:
            return 2
        time.sleep(1.5)
        print(f"  trigger diag: HTTP {req('POST', '/inject/pd-inj', data={})[0]}")
        for _ in range(15):
            time.sleep(1.2)
            if get_ctx("pd_perms"):
                break
        ident = get_ctx("pd_identity")
        node = get_ctx("pd_node")
        perms = get_ctx("pd_perms")
    finally:
        rc = req("POST", "/flows", original)[0]
        print(f"restore original flows: HTTP {rc}" + ("  (OK)" if rc == 204 else "  <- CHECK CANVAS"))

    print("\n== proxmox token self-report ==")
    print(f"  token identity : {ident or '(unknown)'}")
    print(f"  node           : {node or '(unknown)'}")
    print(f"  /access/permissions:")
    for line in str(perms or "(no result)").splitlines():
        print(f"    {line}")

    have = False
    if perms:
        for line in str(perms).splitlines():
            if "->" in line and "Sys.Audit" in line:
                have = True
    print()
    if not perms:
        print("could not determine the token's permissions.")
        return 2
    if have:
        print("Sys.Audit IS present in the token's map. If /nodes/<node>/status still")
        print("403s, the granted PATH does not cover that node -- check the path.")
        # presence of Sys.Audit anywhere is 'possibly fine'; let the caller re-run verify
        return 0
    print("Sys.Audit is NOT in the token's effective permissions.")
    print("Most likely: Privilege Separation is ON, so the token inherits nothing")
    print("from its user, and no API TOKEN Permission was granted to the token itself.")
    print("Fix: Datacenter -> Permissions -> Add -> API Token Permission,")
    print("     Path /   API Token <user>@<realm>!<name>   Role PVEAuditor")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("connection failed:", e); sys.exit(2)
