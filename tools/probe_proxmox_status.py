#!/usr/bin/env python3
"""
Discover the real Proxmox /nodes/<node>/status shape from the RUNNING runtime.

The Home Lab tab needs more fields to fill the screen. Rather than trust
documentation (or memory) for the key names, deploy a temp tab that performs the
exact request the flow performs, store the RAW response in flow context, read it
back, and print the observed top-level keys.

Read-only GET; restores the original flows afterwards.

Usage:
  python3 tools/probe_proxmox_status.py [http://host:1880]
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://sh-dashboard:1880"

TAB_ID = "probe-pve-tab"
INJ_ID = "probe-pve-inject"
FN_ID = "probe-pve-fn"
HTTP_ID = "probe-pve-http"
STORE_ID = "probe-pve-store"

BUILD = (
    "var base = env.get('PROXMOX_URL');\n"
    "var tok  = env.get('PROXMOX_TOKEN');\n"
    "if (!base || !tok) { flow.set('pve_status', 'skip: PROXMOX_URL/TOKEN unset'); return null; }\n"
    "var node = env.get('PROXMOX_NODE') || 'pve';\n"
    "msg.method = 'GET';\n"
    "msg.url = base.replace(/\\/+$/,'') + '/api2/json/nodes/' + node + '/status';\n"
    "msg.headers = { 'Authorization': 'PVEAPIToken=' + tok };\n"
    "msg.rejectUnauthorized = false;\n"
    "flow.set('pve_status', 'requesting');\n"
    "return msg;\n"
)

STORE = (
    "var body = msg.payload;\n"
    "if (typeof body === 'string') {\n"
    "  try { body = JSON.parse(body); } catch (e) {\n"
    "    flow.set('pve_status', 'non-json: ' + body.slice(0,150)); return null;\n"
    "  }\n"
    "}\n"
    "var d = (body && body.data) ? body.data : body;\n"
    "if (!d || typeof d !== 'object') { flow.set('pve_status', 'no data object'); return null; }\n"
    "flow.set('pve_status', 'ok');\n"
    "flow.set('pve_keys', Object.keys(d).sort().join(','));\n"
    "// Scalar values only, so the dump stays readable.\n"
    "var flat = {};\n"
    "Object.keys(d).forEach(function (k) {\n"
    "  var v = d[k];\n"
    "  if (v === null || typeof v !== 'object') flat[k] = v;\n"
    "  else flat[k] = '[object: ' + Object.keys(v).join('|') + ']';\n"
    "});\n"
    "flow.set('pve_flat', JSON.stringify(flat));\n"
    "return null;\n"
)


def req(method, path, data=None, headers=None, timeout=25):
    url = BASE + path
    body = json.dumps(data).encode() if data is not None else None
    h = {"Content-Type": "application/json"} if data is not None else {}
    if headers:
        h.update(headers)
    r = urllib.request.Request(url, data=body, headers=h, method=method)
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        raw = resp.read().decode() or ""
        try:
            return resp.status, json.loads(raw)
        except Exception:
            return resp.status, raw


def main():
    print(f"proxmox status probe target: {BASE}")
    original = req("GET", "/flows")[1]
    if not isinstance(original, list):
        print("could not read /flows"); return 2
    print(f"current flows: {len(original)} nodes")

    probe = [
        {"id": TAB_ID, "type": "tab", "label": "PveProbe", "disabled": False, "info": ""},
        {"id": INJ_ID, "type": "inject", "z": TAB_ID, "name": "probe",
         "props": [{"p": "payload"}], "repeat": "", "crontab": "", "once": True,
         "onceDelay": 0.2, "topic": "", "payload": "", "payloadType": "date",
         "x": 150, "y": 100, "wires": [[FN_ID]]},
        {"id": FN_ID, "type": "function", "z": TAB_ID, "name": "build",
         "func": BUILD, "outputs": 1, "noerr": 0, "initialize": "", "finalize": "",
         "libs": [], "x": 340, "y": 100, "wires": [[HTTP_ID]]},
        {"id": HTTP_ID, "type": "http request", "z": TAB_ID, "name": "PVE status",
         "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
         "persist": False, "proxy": "", "authType": "", "x": 530, "y": 100,
         "wires": [[STORE_ID]]},
        {"id": STORE_ID, "type": "function", "z": TAB_ID, "name": "store",
         "func": STORE, "outputs": 0, "noerr": 0, "initialize": "", "finalize": "",
         "libs": [], "x": 720, "y": 100, "wires": [[]]},
    ]

    try:
        code = req("POST", "/flows", original + probe,
                   {"Node-RED-Deployment-Type": "full"})[0]
        print(f"deploy probe (temp): HTTP {code}")
        if code != 204:
            return 2
        time.sleep(1.5)
        print("trigger:", req("POST", f"/inject/{INJ_ID}", data={})[0])

        data = None
        for _ in range(15):
            time.sleep(1.0)
            _, ctx = req("GET", f"/context/flow/{TAB_ID}")
            if not isinstance(ctx, dict):
                continue
            mem = ctx.get("memory", {})

            def unwrap(v):
                if isinstance(v, dict) and "msg" in v:
                    v = v["msg"]
                if isinstance(v, str):
                    try:
                        return json.loads(v)
                    except Exception:
                        return v
                return v

            if "pve_status" in mem:
                data = {k[len("pve_"):]: unwrap(v)
                        for k, v in mem.items() if k.startswith("pve_")}
                break
    finally:
        code = req("POST", "/flows", original,
                   {"Node-RED-Deployment-Type": "full"})[0]
        print(f"restore original flows: HTTP {code}"
              + ("  (OK)" if code == 204 else "  <- CHECK THE CANVAS"))

    if not data:
        print("no probe result"); return 2

    print("\n== Proxmox node status ==")
    print("status:", data.get("status"))
    print("keys  :", data.get("keys"))
    flat = data.get("flat")
    if isinstance(flat, str):
        try:
            flat = json.loads(flat)
        except Exception:
            pass
    if isinstance(flat, dict):
        print("\nvalues (scalars verbatim, objects summarised):")
        for k in sorted(flat):
            print(f"  {k:16s} {str(flat[k])[:90]}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("connection failed:", e); sys.exit(2)
