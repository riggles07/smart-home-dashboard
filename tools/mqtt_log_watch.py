"""Watch the Mosquitto add-on log for connection attempts from the tailnet / LAN.

The point: a wall panel that reaches the broker leaves a `New connection from <ip>`
line within milliseconds -- even if its password is wrong. So this distinguishes
"network can't reach the broker" from "credentials rejected" without guessing.

Polls the supervisor log proxy (the HA long-lived token can read add-on logs) and
prints only NEW lines, so the output is a clean event stream.
"""
import hashlib
import time
import urllib.request

import sys

DURATION = int(sys.argv[1]) if len(sys.argv) > 1 else 20 * 60   # seconds
INTERVAL = int(sys.argv[2]) if len(sys.argv) > 2 else 5         # seconds

env = {}
for line in open("/root/.hermes/.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1)
        env[k] = v
URL = env["HA_URL"].rstrip("/") + "/api/hassio/addons/core_mosquitto/logs"
HDR = {"Authorization": "Bearer " + env["HA_TOKEN"]}


def fetch():
    req = urllib.request.Request(URL, headers=HDR)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


seen = set()
start = time.time()
print(f"watching Mosquitto log for {DURATION // 60} min (poll every {INTERVAL}s)", flush=True)
try:
    while time.time() - start < DURATION:
        try:
            log = fetch()
        except Exception as e:
            print(f"[warn] fetch failed: {type(e).__name__}", flush=True)
            time.sleep(INTERVAL)
            continue
        for line in log.splitlines():
            h = hashlib.md5(line.encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            if not line.strip() or line.strip().startswith("error:"):
                continue
            # only report things that mean someone tried to talk to the broker
            if any(k in line for k in ("New connection", "New client", "disconnect",
                                       "not authorised", "Bad username")):
                print(line.strip()[:170], flush=True)
        time.sleep(INTERVAL)
except KeyboardInterrupt:
    pass
print("watcher finished", flush=True)
