#!/usr/bin/env python3
"""
Prove whether the RUNNING Node-RED can see the flow environment variables --
without shell access to the host.

The admin API cannot read /proc/<pid>/environ, and `inject` gives no response
body. So: temporarily deploy one extra tab containing an inject -> function
node that records `env.get(name)` presence into FLOW CONTEXT, trigger it, read
the result back via GET /context/flow/<id>, then restore the original flows.

Only variable NAMES and SET/unset are printed -- never values.

Usage:
  python3 tools/probe_runtime_env.py [http://host:1880]
Exit code 0 = every required variable is visible to the runtime.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://sh-dashboard:1880"

# Core variables the flows read, grouped by which tab needs them.
REQUIRED = {
    "Home Lab": ["PROXMOX_URL", "PROXMOX_TOKEN", "PROXMOX_NODE"],
    "Devices": ["HUBITAT_URL", "HUBITAT_APP_ID", "HUBITAT_ACCESS_TOKEN",
                "HUBITAT_API_KEY", "HUBITAT_DEVICE_ID"],
    "Network": ["UNIFI_URL", "UNIFI_SITE", "UNIFI_API_KEY",
                "UNIFI_USERNAME", "UNIFI_PASSWORD", "UNIFI_LOGIN_URL"],
}
ALL_VARS = sorted({v for vars_ in REQUIRED.values() for v in vars_})

TAB_ID = "probe-env-tab"
INJ_ID = "probe-env-inject"
FN_ID = "probe-env-fn"


def req(method, path, data=None, headers=None, timeout=20):
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


def deploy(nodes):
    return req("POST", "/flows", nodes,
               {"Node-RED-Deployment-Type": "full"})[0]


def main():
    print(f"probe target: {BASE}")

    original = req("GET", "/flows")[1]
    if not isinstance(original, list):
        print("could not read /flows; aborting"); return 2
    print(f"current flows: {len(original)} nodes "
          f"({sum(1 for n in original if n['type'] == 'tab')} tabs)")

    # --- build the probe tab ---
    # One flow-context key PER variable. The context API returns compound values
    # wrapped in an envelope ({"msg":..,"format":..}), so writing a single object
    # and reading it back is ambiguous; a scalar per key is not.
    sets = "\n".join(
        f"flow.set('envprobe_{v}', env.get('{v}') ? 'SET' : 'unset');"
        for v in ALL_VARS)
    fn = (
        "// Record which env vars the RUNTIME can see. Presence only, no values.\n"
        + sets + "\n"
        "msg.payload = 'probe done';\n"
        "return msg;"
    )
    probe = [
        {"id": TAB_ID, "type": "tab", "label": "EnvProbe", "disabled": False, "info": ""},
        {"id": INJ_ID, "type": "inject", "z": TAB_ID, "name": "probe",
         "props": [{"p": "payload"}], "repeat": "", "crontab": "", "once": True,
         "onceDelay": 0.2, "topic": "", "payload": "", "payloadType": "date",
         "x": 150, "y": 100, "wires": [[FN_ID]]},
        {"id": FN_ID, "type": "function", "z": TAB_ID, "name": "probe env",
         "func": fn, "outputs": 1, "noerr": 0, "initialize": "", "finalize": "",
         "libs": [], "x": 360, "y": 100, "wires": [[]]},
    ]

    result = None
    try:
        code = deploy(original + probe)
        print(f"deploy probe (temp): HTTP {code}")
        if code != 204:
            print("probe deploy rejected"); return 2
        time.sleep(1.5)

        pcode, _ = req("POST", f"/inject/{INJ_ID}", data={})
        print(f"trigger probe inject: HTTP {pcode}")

        # poll flow context for the recorded result
        for _ in range(12):
            time.sleep(1.0)
            scode, ctx = req("GET", f"/context/flow/{TAB_ID}")
            if isinstance(ctx, dict):
                mem = ctx.get("memory", {})
                if any(k.startswith("envprobe_") for k in mem):
                    out = {}
                    for k, v in mem.items():
                        if not k.startswith("envprobe_"):
                            continue
                        name = k[len("envprobe_"):]
                        # The context API may wrap even scalars in an envelope;
                        # its "msg" is sometimes raw text, sometimes JSON.
                        if isinstance(v, dict) and "msg" in v:
                            v = v["msg"]
                        if isinstance(v, str):
                            try:
                                v = json.loads(v)
                            except Exception:
                                pass  # already the raw string, e.g. "SET"
                        out[name] = v
                    result = out
                    break
    finally:
        # ALWAYS restore the original flow set
        code = deploy(original)
        print(f"restore original flows: HTTP {code}"
              + ("  (OK)" if code == 204 else "  <- CHECK THE CANVAS"))

    if not result:
        print("\nno probe result: the runtime did not execute the probe node.")
        print("That by itself suggests the flows are not running as expected.")
        return 2

    print("\n== env visibility from the RUNNING runtime ==")
    missing = []
    for tab, vars_ in REQUIRED.items():
        print(f"[{tab}]")
        for v in vars_:
            state = result.get(v, "?")
            mark = "   " if state == "SET" else "   "
            print(f"{mark}{v:22s} {state}")
            # HUBITAT_ACCESS_TOKEN may be satisfied by HUBITAT_API_KEY
            if state != "SET":
                missing.append(v)

    # Apply the flow's own fallback rules before declaring failure.
    def ok(v):
        if result.get(v) == "SET":
            return True
        if v == "HUBITAT_ACCESS_TOKEN" and result.get("HUBITAT_API_KEY") == "SET":
            return True
        if v == "UNIFI_API_KEY" and result.get("UNIFI_USERNAME") == "SET" \
                and result.get("UNIFI_PASSWORD") == "SET":
            return True
        if v in ("PROXMOX_NODE", "UNIFI_SITE", "UNIFI_LOGIN_URL"):
            return True   # optional, has a default
        return False

    blocking = [v for v in ALL_VARS if not ok(v)]
    print()
    if blocking:
        print("STILL MISSING (flows cannot work):", ", ".join(blocking))
        return 1
    print("OK: every required variable is visible to the runtime.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.URLError as e:
        print("connection failed:", e); sys.exit(2)
