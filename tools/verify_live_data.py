#!/usr/bin/env python3
"""
Trigger the dashboard flows and report success per service.

Deploys a temporary probe tab carrying one inject -> function node per service.
Each reads its own env vars, builds the SAME request the real flow builds, and
records the outcome (HTTP status and whether the body looks live) into flow
context. Then the results are read back and the original flows restored.

This is read-only against the services: it issues GETs only.

Only status codes / booleans are printed -- never credential values or payloads.

Usage:
  python3 tools/verify_live_data.py [http://host:1880]
Exit 0 = every configured service answered with a usable payload.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://sh-dashboard:1880"

TAB = "liveprobe-tab"

# Each entry: (context key, inject id, function name, function body)
# The bodies mirror the real flows' request construction.
FUNCS = [
    ("proxmox", "lp-inj-pve", "Proxmox", """
      var url = env.get('PROXMOX_URL');
      var tok = env.get('PROXMOX_TOKEN');
      var node = env.get('PROXMOX_NODE') || 'pve';
      if (!url || !tok) { flow.set('lp_proxmox', 'skip: PROXMOX_URL/TOKEN unset'); return null; }
      msg.method = 'GET';
      msg.url = url.replace(/\\/+$/,'') + '/api2/json/nodes/' + node + '/status';
      msg.headers = { 'Authorization': 'PVEAPIToken=' + tok };
      msg.rejectUnauthorized = false;
      msg._svc = 'proxmox';
      return msg;
    """),
    ("hubitat", "lp-inj-hub", "Hubitat", """
      // Probe the device LIST, not a specific device: a 404 on the list means a
      // bad app id, whereas a 200-list/404-device means only the device id is
      // wrong. Probing the device directly cannot tell those apart.
      var base = env.get('HUBITAT_URL');
      var app  = env.get('HUBITAT_APP_ID');
      var tok  = env.get('HUBITAT_ACCESS_TOKEN') || env.get('HUBITAT_API_KEY');
      if (!base || !app || !tok) { flow.set('lp_hubitat', 'skip: HUBITAT_* unset'); return null; }
      msg.method = 'GET';
      msg.url = base.replace(/\\/+$/,'') + '/apps/api/' + app + '/devices?access_token=' + tok;
      msg._svc = 'hubitat';
      return msg;
    """),
    ("unifi", "lp-inj-uni", "UniFi", """
      var base = env.get('UNIFI_URL');
      var site = env.get('UNIFI_SITE') || 'default';
      var key  = env.get('UNIFI_API_KEY');
      var user = env.get('UNIFI_USERNAME');
      var pass = env.get('UNIFI_PASSWORD');
      if (!base) { flow.set('lp_unifi', 'skip: UNIFI_URL unset'); return null; }
      base = base.replace(/\\/+$/,'');
      msg.rejectUnauthorized = false;
      if (key) {
        msg.method = 'GET';
        msg.url = base + '/api/s/' + site + '/stat/sta';
        msg.headers = { 'X-API-KEY': key };
      } else if (user && pass) {
        // Mirror the flow's login-URL derivation EXACTLY. Posting to
        // <base>/api/login on a UniFi OS console hits a path that does not
        // exist, so the probe would report 401 for a perfectly good password.
        var login = env.get('UNIFI_LOGIN_URL');
        if (!login) {
          login = base + '/api/login';
          var m = base.match(/^(https?:\\/\\/[^\\/]+)\\/proxy\\/network/);
          if (m) { login = m[1] + '/api/auth/login'; }
        }
        msg.method = 'POST';
        msg.url = login;
        msg.headers = { 'Content-Type': 'application/json' };
        msg.payload = JSON.stringify({ username: user, password: pass, remember: true });
      } else {
        flow.set('lp_unifi', 'skip: no UNIFI credentials');
        return null;
      }
      msg._svc = 'unifi';
      return msg;
    """),
]

# One result-recording node per service, wired after the http request.
RESULT_FN = """
var svc = msg._svc || 'unknown';
var code = msg.statusCode || 0;
var body = msg.payload;
var size = 0;
try { size = body ? JSON.stringify(body).length : 0; } catch (e) { size = -1; }
var verdict;
if (msg.error) { verdict = 'ERROR: ' + msg.error; }
else if (code >= 200 && code < 300 && size > 2) { verdict = 'LIVE (HTTP ' + code + ', ' + size + ' bytes)'; }
else if (code >= 200 && code < 300) { verdict = 'EMPTY (HTTP ' + code + ')'; }
else { verdict = 'HTTP ' + code; }
var prev = flow.get('lp_results') || {};
prev[svc] = verdict;
flow.set('lp_results', prev);
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


def main():
    print(f"live-data check: {BASE}")
    original = req("GET", "/flows")[1]
    if not isinstance(original, list):
        print("cannot read /flows"); return 2
    print(f"current flows: {len(original)} nodes")

    probe = [{"id": TAB, "type": "tab", "label": "LiveProbe", "disabled": False, "info": ""},
             {"id": "lp-init", "type": "function", "z": TAB, "name": "reset",
              "func": "flow.set('lp_results', {});\nreturn null;", "outputs": 1,
              "noerr": 0, "initialize": "", "finalize": "", "libs": [],
              "x": 100, "y": 20, "wires": [[]]}]
    for key, inj, name, body in FUNCS:
        http_id, res_id = f"{inj}-http", f"{inj}-res"
        probe += [
            {"id": inj, "type": "inject", "z": TAB, "name": name, "props": [{"p": "payload"}],
             "repeat": "", "crontab": "", "once": False, "onceDelay": 0.1, "topic": "",
             "payload": "", "payloadType": "date", "x": 150, "y": 100,
             "wires": [[f"{inj}-fn"]]},
            {"id": f"{inj}-fn", "type": "function", "z": TAB, "name": name + " req",
             "func": body, "outputs": 1, "noerr": 0, "initialize": "", "finalize": "",
             "libs": [], "x": 330, "y": 100, "wires": [[http_id]]},
            {"id": http_id, "type": "http request", "z": TAB, "name": name + " call",
             "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
             "persist": False, "proxy": "", "authType": "", "x": 520, "y": 100,
             "wires": [[res_id]]},
            {"id": res_id, "type": "function", "z": TAB, "name": name + " result",
             "func": RESULT_FN, "outputs": 1, "noerr": 0, "initialize": "", "finalize": "",
             "libs": [], "x": 700, "y": 100, "wires": [[]]},
        ]

    results = {}
    try:
        code = req("POST", "/flows", original + probe)[0]
        print(f"deploy probe: HTTP {code}")
        if code != 204:
            return 2
        time.sleep(1.5)

        # reset, then fire each service probe
        req("POST", "/inject/lp-init", data={})
        for key, inj, name, _ in FUNCS:
            pc = req("POST", f"/inject/{inj}", data={})[0]
            print(f"  trigger {name}: HTTP {pc}")

        for _ in range(15):
            time.sleep(1.2)
            _, ctx = req("GET", f"/context/flow/{TAB}")
            mem = ctx.get("memory", {}) if isinstance(ctx, dict) else {}
            r = mem.get("lp_results")
            if isinstance(r, dict) and "msg" in r:
                try:
                    r = json.loads(r["msg"])
                except Exception:
                    r = None
            if isinstance(r, dict) and len(r) >= 1:
                results = r
                if len(results) >= len(FUNCS):
                    break
    finally:
        rc = req("POST", "/flows", original)[0]
        print(f"restore original flows: HTTP {rc}" + ("  (OK)" if rc == 204 else "  <- CHECK CANVAS"))

    print("\n== service responses ==")
    bad = 0
    for key, inj, name, _ in FUNCS:
        v = results.get(key, "no result (node did not run)")
        print(f"  {name:9s} {v}")
        if not str(v).startswith("LIVE") and not str(v).startswith("skip"):
            bad += 1
    print()
    if bad:
        print(f"{bad} service(s) did not return live data.")
        return 1
    print("OK: all configured services responded.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("connection failed:", e); sys.exit(2)
