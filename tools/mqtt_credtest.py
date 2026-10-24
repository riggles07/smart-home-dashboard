"""Test the panel's MQTT credentials against the live broker.

Reads creds from argv so nothing is hard-coded in the repo, reports the CONNACK code in
plain language, then proves the account is actually *usable* (subscribe + publish round
trip) rather than merely accepted -- an ACL-restricted login connects fine and then fails
on every topic, which looks identical to a panel that "connects but shows nothing".
"""
import sys
import time

import paho.mqtt.client as mqtt

HOST = "100.104.204.118"
PORT = 1883
RC = {0: "ACCEPTED", 1: "bad protocol version", 2: "bad client id",
      3: "broker unavailable", 4: "BAD USERNAME OR PASSWORD", 5: "NOT AUTHORISED"}

user = sys.argv[1]
password = sys.argv[2]
label = sys.argv[3] if len(sys.argv) > 3 else user

res = {"rc": None, "msgs": [], "suback": None}


def on_connect(c, _u, _f, rc):
    res["rc"] = rc
    if rc == 0:
        c.subscribe([("wallpanel/#", 0), ("homeassistant/#", 0)])


def on_subscribe(_c, _u, _mid, granted):
    res["suback"] = list(granted)


def on_message(_c, _u, m):
    res["msgs"].append((m.topic, m.payload[:80]))


c = mqtt.Client(client_id="hermes-credtest", clean_session=True)
c.username_pw_set(user, password)
c.on_connect, c.on_subscribe, c.on_message = on_connect, on_subscribe, on_message
c.connect(HOST, PORT, 10)
c.loop_start()
t0 = time.time()
while res["rc"] is None and time.time() - t0 < 8:
    time.sleep(0.05)

print(f"  {label:<22} rc={res['rc']} {RC.get(res['rc'], '?')}")
if res["rc"] == 0:
    c.publish("wallpanel/hermes-probe", "hello", qos=0)
    time.sleep(6)
    print(f"  subscriptions granted : {res['suback']}  (128 = refused by ACL)")
    print(f"  retained/live messages: {len(res['msgs'])}")
    for t, p in res["msgs"][:6]:
        print(f"    {t}  {p!r}")
c.loop_stop()
c.disconnect()
