#!/usr/bin/env python3
"""
Discover the real Hubitat Maker API device-list shape from the RUNNING runtime.

The Devices tab needs to render the device list with the right field names.
Rather than guess them from docs, deploy a temp tab that performs the exact
request the flow performs and stores the RAW response in flow context, then read
it back and print the observed keys.

Read-only: it issues a GET (the Maker API list endpoint) and restores the
original flows afterwards.

Usage:
  python3 tools/probe_hubitat_devices.py [http://host:1880]
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://sh-dashboard:1880"

TAB_ID = "probe-dev-tab"
INJ_ID = "probe-dev-inject"
FN_ID = "probe-dev-fn"
HTTP_ID = "probe-dev-http"
STORE_ID = "probe-dev-store"

# Same request the Devices tab builds (the device LIST, not one device).
BUILD = (
    "var base = env.get('HUBITAT_URL');\n"
    "var app  = env.get('HUBITAT_APP_ID');\n"
    "var tok  = env.get('HUBITAT_ACCESS_TOKEN') || env.get('HUBITAT_API_KEY');\n"
    "if (!base || !app || !tok) {\n"
    "  flow.set('devprobe_status', 'skip: missing HUBITAT_* config');\n"
    "  return null;\n"
    "}\n"
    "msg.method = 'GET';\n"
    "msg.url = base.replace(/\\/+$/,'') + '/apps/api/' + app + '/devices?access_token=' + tok;\n"
    "flow.set('devprobe_status', 'requesting');\n"
    "return msg;\n"
)

STORE = (
    "var body = msg.payload;\n"
    "if (typeof body === 'string') {\n"
    "  try { body = JSON.parse(body); } catch (e) {\n"
    "    flow.set('devprobe_status', 'non-json response: ' + body.slice(0,120));\n"
    "    return null;\n"
    "  }\n"
    "}\n"
    "var list = Array.isArray(body) ? body : (body && body.devices) || [];\n"
    "flow.set('devprobe_count', list.length);\n"
    "flow.set('devprobe_status', 'ok');\n"
    "if (list.length) {\n"
    "  // Keys present on the first device, and a small sample of values.\n"
    "  flow.set('devprobe_keys', Object.keys(list[0]).sort().join(','));\n"
    "  flow.set('devprobe_sample', JSON.stringify(list.slice(0,3)));\n"
    "}\n"
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
    print(f"device probe target: {BASE}")
    original = req("GET", "/flows")[1]
    if not isinstance(original, list):
        print("could not read /flows"); return 2
    print(f"current flows: {len(original)} nodes")

    probe = [
        {"id": TAB_ID, "type": "tab", "label": "DevProbe", "disabled": False, "info": ""},
        {"id": INJ_ID, "type": "inject", "z": TAB_ID, "name": "probe",
         "props": [{"p": "payload"}], "repeat": "", "crontab": "", "once": True,
         "onceDelay": 0.2, "topic": "", "payload": "", "payloadType": "date",
         "x": 150, "y": 100, "wires": [[FN_ID]]},
        {"id": FN_ID, "type": "function", "z": TAB_ID, "name": "build",
         "func": BUILD, "outputs": 1, "noerr": 0, "initialize": "", "finalize": "",
         "libs": [], "x": 340, "y": 100, "wires": [[HTTP_ID]]},
        {"id": HTTP_ID, "type": "http request", "z": TAB_ID, "name": "Maker API",
         "method": "use", "ret": "txt", "paytoqs": "ignore", "url": "", "tls": "",
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
                    try: return json.loads(v)
                    except Exception: return v
                return v
            if "devprobe_status" in mem:
                data = {k[len("devprobe_"):]: unwrap(v)
                        for k, v in mem.items() if k.startswith("devprobe_")}
                break
    finally:
        code = req("POST", "/flows", original,
                   {"Node-RED-Deployment-Type": "full"})[0]
        print(f"restore original flows: HTTP {code}"
              + ("  (OK)" if code == 204 else "  <- CHECK THE CANVAS"))

    if not data:
        print("no probe result"); return 2

    print("\n== Maker API device list ==")
    # NOTE: keys were de-prefixed when building `data`, so look up the bare name.
    print("status:", data.get("status"))
    print("count :", data.get("count"))
    keys = data.get("keys")
    if keys:
        print("keys  :", keys)
    sample = data.get("sample")
    if sample:
        try:
            items = json.loads(sample) if isinstance(sample, str) else sample
            print("\nsample (first 3, trimmed):")
            for it in items[:3]:
                if isinstance(it, dict):
                    keep = {k: it[k] for k in
                            ("id", "name", "label", "type", "attributes", "capabilities")
                            if k in it}
                    print("  ", json.dumps(keep)[:400])
        except Exception as e:
            print("  (could not parse sample:", e, ")")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("connection failed:", e); sys.exit(2)
