"""Measure the panel's layout: who is eating the screen.

"Leaves a lot of wasted space" is a symptom with several possible owners -- the Lovelace
view (masonry max-width + padding), hui-root chrome, or the card itself (fixed aspect
ratio, max-width). Guessing which one wastes a round trip, so this asks the page for the
actual boxes and computed styles and reports one compact line.
"""
import json
import time
from urllib.parse import unquote

import paho.mqtt.client as mqtt
import requests

from mqtt_creds import creds

BASE = "100.104.204.118"
TOPIC = "wallpanel/mywallpanel/command"
CLEAN = "/cartoon-plan/cartoon-plan"

PROBE = r"""
(function(){
  function sr(el){ return el && el.shadowRoot ? el.shadowRoot : null; }
  function q(el, sel){ var r = sr(el); return r ? r.querySelector(sel) : (el ? el.querySelector(sel) : null); }
  function box(el){
    if (!el) return 'noel';
    var r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return [Math.round(r.width), Math.round(r.height), Math.round(r.top), Math.round(r.left),
            s.padding, s.margin, s.maxWidth, s.maxHeight].join(',');
  }
  try {
    var ha = document.querySelector('home-assistant');
    var main = q(ha, 'home-assistant-main');
    var panel = q(main, 'ha-panel-lovelace');
    var hui = q(panel, 'hui-root');
    var view = hui ? q(hui, 'hui-view') : null;
    var card = view ? view.querySelector('floorplan-cartoon-card') : null;
    var img = card && sr(card) ? sr(card).querySelector('img.floorplan') || sr(card).querySelector('img') : null;
    var lov = panel && panel.lovelace;
    var views = (lov && lov.config && lov.config.views) || [];
    var cv = (lov && lov.current_view) || 0;
    var vcfg = views[cv] || {};
    var out = [
      'vw' + window.innerWidth + 'x' + window.innerHeight,
      'root:' + box(hui),
      'view:' + box(view),
      'card:' + box(card),
      'img:' + box(img),
      'nat' + (img ? img.naturalWidth + 'x' + img.naturalHeight : 0),
      'panel' + (vcfg.panel ? 1 : 0),
      'cols' + (vcfg.cards ? vcfg.cards.length : -1)
    ].join('~');
    history.replaceState({}, '', location.pathname + '?geo=' + encodeURIComponent(out));
  } catch (e) {
    try { history.replaceState({}, '', location.pathname + '?geo=ERR' + encodeURIComponent(e.message)); } catch (x) {}
  }
})()
"""

env = {}
for line in open("/root/.hermes/.env"):
    if "=" in line:
        k, v = line.strip().split("=", 1)
        env[k] = v
HA = env["HA_URL"].rstrip("/")
H = {"Authorization": "Bearer " + env["HA_TOKEN"], "Content-Type": "application/json"}


def publish(payload):
    c = mqtt.Client(client_id="hermes-geo", clean_session=True)
    c.username_pw_set(*creds())
    c.connect(BASE, 1883, 10)
    c.loop_start()
    time.sleep(1)
    c.publish(TOPIC, json.dumps(payload), qos=1).wait_for_publish()
    time.sleep(2)
    c.loop_stop()
    c.disconnect()


def cur():
    return requests.get(f"{HA}/api/states/sensor.my_wall_panel_current_url",
                        headers=H, timeout=20).json()["state"]


publish({"eval": PROBE.strip()})
for i in range(15):
    time.sleep(4)
    u = cur()
    if "geo=" in u:
        print("DECODED:", unquote(u.split("geo=")[1]).replace("~", "\n          "))
        break
    print(f"  [{i*4}s] waiting…")
else:
    print("no report; last url:", cur())

publish({"eval": "history.replaceState({}, '', '%s')" % CLEAN})
print("\nrestored:", cur())
