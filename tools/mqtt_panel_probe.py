"""MQTT reachability + traffic probe for the wall panel.

Answers three questions with evidence, not guesses:
  1. does the broker accept an anonymous client? (tells us whether credentials are even
     required, i.e. whether the username/password the user added is a suspect)
  2. what does the broker currently see? ($SYS broker stats if enabled)
  3. is the wall panel actually publishing anything? (subscribe to the live topics the
     WallPanel app uses and listen)
"""
import json
import sys
import time

import paho.mqtt.client as mqtt

HOST = "100.104.204.118"
PORT = 1883
LISTEN_SECS = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
USER = sys.argv[2] if len(sys.argv) > 2 else None
PASS = sys.argv[3] if len(sys.argv) > 3 else None

RC = {
    0: "accepted", 1: "bad protocol version", 2: "bad client id",
    3: "broker unavailable", 4: "bad username/password", 5: "NOT AUTHORISED",
}


def probe(label, user=None, password=None, timeout=8.0):
    seen = {}
    got = {"rc": None}

    def on_connect(c, _u, _f, rc):
        got["rc"] = rc
        c.disconnect()

    c = mqtt.Client(client_id="hermes-probe-" + label.replace(" ", "-"))
    if user:
        c.username_pw_set(user, password or "")
    c.on_connect = on_connect
    try:
        c.connect(HOST, PORT, 5)
        c.loop_start()
        t0 = time.time()
        while got["rc"] is None and time.time() - t0 < timeout:
            time.sleep(0.1)
        c.loop_stop()
    except Exception as e:
        return f"CONNECT EXCEPTION {type(e).__name__}: {e}"
    if got["rc"] is None:
        return "no CONNACK (timed out)"
    return f"rc={got['rc']} {RC.get(got['rc'], '?')}"


print("=== 1. auth posture ===")
print(f"  anonymous        : {probe('anon')}")
if USER:
    print(f"  as {USER!r} (given) : {probe('given', USER, PASS)}")
else:
    print("  (no credentials supplied to this probe - testing anonymous only)")

print(f"\n=== 2/3. live traffic, {LISTEN_SECS:.0f}s ===")
msgs = []
sysv = {}


def on_msg(_c, _u, m):
    payload = m.payload.decode("utf-8", "replace")
    if m.topic.startswith("$SYS/"):
        sysv[m.topic] = payload
        return
    msgs.append((m.topic, payload[:160], m.retain))


c = mqtt.Client(client_id="hermes-sniff")
c.on_connect = lambda cl, _u, _f, rc: (cl.subscribe("#", 0), cl.subscribe("$SYS/#", 0))
c.on_message = on_msg
c.connect(HOST, PORT, 20)
c.loop_start()
time.sleep(LISTEN_SECS)
c.loop_stop()

interesting = [m for m in msgs if m[0].startswith(("wallpanel", "homeassistant/+/+/config",
                                                    "wallpanel/+/state", "wallpanel/+/sensor"))]
wall = [m for m in msgs if m[0].startswith("wallpanel")]
print(f"  messages on '#'          : {len(msgs)}")
print(f"  messages on 'wallpanel/#' : {len(wall)}")
print(f"  retained discovery cfgs   : {len([m for m in msgs if m[0].startswith('homeassistant/')])}")
for t, p, r in interesting[:15]:
    print(f"    {'[ret]' if r else '     '} {t}  {p[:110]}")
if wall:
    print("\n  wallpanel topics seen:")
    for t in sorted({m[0] for m in wall}):
        print(f"    {t}")

print("\n  $SYS broker stats:")
for k in ("clients/connected", "clients/total", "messages/received", "messages/sent",
          "broker/version", "load/messages/received/1min"):
    if "$SYS/broker/" + k in sysv:
        print(f"    {k:<26} {sysv['$SYS/broker/' + k]}")

if not msgs:
    print("\n  (broker accepted us but relayed nothing - anonymous listener is likely"
          " read-only or acl'd, or the broker only shows $SYS when sys_interval > 0)")
