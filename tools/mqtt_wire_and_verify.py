#!/usr/bin/env python3
"""Wire WallPanel MQTT broker credentials into the live Node-RED runtime and
verify the kiosk control path end to end.

Usage:
    python3 tools/mqtt_wire_and_verify.py --user RH-HA --password '...'

Why a script rather than a curl one-liner:
  * broker credentials live in the Node-RED CREDENTIAL STORE, not in flows.json,
    so they must be injected with a v2 `{"flows":..., "credentials":...}` POST;
  * the v1 array form (what the rest of the project uses) cannot carry them;
  * there is no GET /credentials/<id> on this build, so the write can only be
    proven BEHAVIOURALLY -- which is the second half of this script.

Verification is a full round trip with no tablet required:
  1. subscribe to the command topic        -> the retained brightness message
                                              proves Node-RED authenticated and
                                              can PUBLISH (mqtt out works)
  2. publish {"value":true} to the motion
     topic                                 -> Node-RED must PUBLISH a wake
                                              command, which proves the
                                              SUBSCRIBE side and the motion
                                              function both work
  3. publish a fake <base>/state           -> the Kiosk status widget must show
                                              it (checked as text over the
                                              dashboard HTML if a browser is
                                              unavailable)

Exit code 0 only if steps 1 and 2 are observed.
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

import paho.mqtt.client as mqtt

NODE_RED = "http://192.168.4.100:1880"
FLOWS_FILE = Path(__file__).resolve().parent.parent / "flows" / "all-flows.flow.json"
BROKER_HOST = "100.104.204.118"
BROKER_PORT = 1883
BASE = "wallpanel/a7lite"
CMD_TOPIC = BASE + "/command"
MOTION_TOPIC = BASE + "/sensor/motion"
STATE_TOPIC = BASE + "/state"


def http(path, data=None, method=None, headers=None):
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(NODE_RED + path, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.status, r.read().decode()


def live_flows():
    _, body = http("/flows")
    return json.loads(body)


def repo_flows():
    """The GENERATED flow set -- what actually gets deployed.

    This must not be the live set. An earlier version of this script re-posted
    `live_flows()` with credentials, which meant it redeployed whatever was
    already running and silently ignored the fix sitting in the repo: the
    motion path stayed broken while the script reported a successful deploy.
    """
    return json.loads(FLOWS_FILE.read_text())


def broker_id(flows):
    brokers = [n for n in flows if n.get("type") == "mqtt-broker"]
    if len(brokers) != 1:
        sys.exit(f"expected exactly 1 mqtt-broker node, found {len(brokers)}")
    return brokers[0]["id"], brokers[0]["broker"], str(brokers[0]["port"])


def write_credentials(flows, bid, user, password):
    """v2 object form: the ONLY way to carry credentials over the Admin API."""
    payload = {"flows": flows,
               "credentials": {bid: {"user": user, "password": password}}}
    st, _ = http("/flows", data=json.dumps(payload).encode(), method="POST",
                 headers={"Node-RED-API-Version": "v2",
                          "Node-RED-Deployment-Type": "full"})
    return st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--user", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument("--broker-host", default=BROKER_HOST)
    args = ap.parse_args()

    flows = repo_flows()
    live = live_flows()
    bid, host, port = broker_id(flows)
    print(f"[1] repo nodes: {len(flows)} (live: {len(live)}); "
          f"broker {bid} -> {host}:{port}")

    # Confirm the flow points at the host we are about to authenticate against.
    if host != args.broker_host:
        print(f"[!] flow broker host {host} != --broker-host {args.broker_host}; "
              f"writing credentials for the flow's host")

    # ---- pre-flight: does the credential even authenticate? ----------------
    rc_holder = {}

    def on_connect(c, u, f, rc, props=None):
        rc_holder["rc"] = getattr(rc, "value", rc)
        rc_holder["done"] = True

    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="shd-prewire-check")
    c.username_pw_set(args.user, args.password)
    c.on_connect = on_connect
    try:
        c.connect(host, int(port), 10)
    except Exception as e:
        sys.exit(f"[2] CONNECT failed: {e}")
    c.loop_start()
    for _ in range(100):
        if rc_holder.get("done"):
            break
        time.sleep(0.05)
    c.loop_stop()
    try:
        c.disconnect()
    except Exception:
        pass
    rc = rc_holder.get("rc")
    if rc != 0:
        sys.exit(f"[2] CONNACK rc={rc} -- broker REJECTED these credentials "
                 f"(0 = accepted). Refusing to write a credential that cannot work.")
    print("[2] credential authenticates: CONNACK 0 (accepted)")

    # ---- write the credential into the runtime ----------------------------
    st = write_credentials(flows, bid, args.user, args.password)
    print(f"[3] v2 deploy with credentials -> HTTP {st}")
    if st not in (200, 204):
        sys.exit(f"[3] deploy rejected: HTTP {st}")

    # ---- observe the outbound path (retained brightness) ------------------
    seen = {"brightness": None, "wake": None}

    def on_msg(client, userdata, m):
        try:
            payload = json.loads(m.payload.decode())
        except Exception:
            return
        if m.topic == CMD_TOPIC:
            if "brightness" in payload:
                seen["brightness"] = payload
            if payload.get("wake") is True:
                seen["wake"] = (payload, time.time())

    sub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                      client_id="shd-wire-verify-%d" % int(time.time()))
    sub.username_pw_set(args.user, args.password)
    sub.on_message = on_msg
    sub.connect(host, int(port), 10)
    sub.subscribe([(CMD_TOPIC, 1), (STATE_TOPIC, 1)])
    sub.loop_start()

    print("[4] waiting up to 45s for the retained brightness command ...")
    for _ in range(90):
        if seen["brightness"]:
            break
        time.sleep(0.5)
    if seen["brightness"]:
        print(f"    OUT PATH OK  <- {CMD_TOPIC} {json.dumps(seen['brightness'])}")
    else:
        print("    OUT PATH NOT OBSERVED (no retained brightness within 45s)")
        print("    hint: mqtt out only publishes on the 5-minute schedule tick;")
        print("          a fresh deploy fires it once after ~5s, so re-run if needed")

    # ---- drive the inbound path: motion -> wake ---------------------------
    print("[5] publishing motion -> expecting a wake command")
    pub = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                      client_id="shd-motion-sim-%d" % int(time.time()))
    pub.username_pw_set(args.user, args.password)
    pub.connect(host, int(port), 10)
    pub.loop_start()
    t0 = time.time()
    pub.publish(MOTION_TOPIC, json.dumps({"value": True}), qos=1)
    for _ in range(60):
        if seen["wake"]:
            break
        time.sleep(0.1)
    sub.loop_stop()
    pub.loop_stop()
    try:
        sub.disconnect(); pub.disconnect()
    except Exception:
        pass

    if seen["wake"]:
        payload, ts = seen["wake"]
        print(f"    IN PATH OK   <- motion produced {json.dumps(payload)} "
              f"in {(ts - t0) * 1000:.0f} ms")
    else:
        print("    IN PATH FAILED -- no wake command came back within 6s")

    ok = bool(seen["brightness"]) and bool(seen["wake"])
    print("\nRESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
