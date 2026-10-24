"""Deep shadow-DOM geometry probe for the panel.

In panel mode the card is not where the masonry probe looked, so this walks every shadow
root (bounded) to find the custom card and its <img>, then reports the boxes that decide
whether the plan fills the screen:

    card  height vs viewport height  -> is the card taller than the screen?
    img   rendered size vs natural   -> is the art letterboxed or scaled down?
    stage height                     -> the hotspot overlay's coordinate space
"""
import json
import time
from urllib.parse import unquote

import paho.mqtt.client as mqtt
import requests

BASE = "100.104.204.118"
TOPIC = "wallpanel/mywallpanel/command"
CLEAN = "/cartoon-plan/cartoon-plan"

PROBE = r"""
(function(){
  function deepFind(sel, maxDepth){
    var found = null;
    (function walk(root, d){
      if (found || !root || d > maxDepth) return;
      var hit = root.querySelector ? root.querySelector(sel) : null;
      if (hit) { found = hit; return; }
      var all = root.querySelectorAll ? root.querySelectorAll('*') : [];
      for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) { walk(all[i].shadowRoot, d + 1); if (found) return; }
      }
    })(document, 0);
    return found;
  }
  function box(el){
    if (!el) return 'noel';
    var r = el.getBoundingClientRect(), s = getComputedStyle(el);
    return [Math.round(r.width), Math.round(r.height), Math.round(r.top)].join(',')
         + '|' + s.maxHeight + '|' + s.objectFit;
  }
  try {
    var card = deepFind('floorplan-cartoon-card', 6);
    var img = card && card.shadowRoot ? card.shadowRoot.querySelector('img') : null;
    var stage = card && card.shadowRoot ? card.shadowRoot.querySelector('.stage') : null;
    var wrap = card && card.shadowRoot ? card.shadowRoot.querySelector('.wrap') : null;
    var svg = card && card.shadowRoot ? card.shadowRoot.querySelector('.stage svg') : null;
    var out = [
      'vw' + window.innerWidth + 'x' + window.innerHeight,
      'card:' + box(card),
      'wrap:' + box(wrap),
      'stage:' + box(stage),
      'img:' + box(img),
      'nat' + (img ? img.naturalWidth + 'x' + img.naturalHeight : 0),
      'par' + (svg ? (svg.getAttribute('preserveAspectRatio') || 'default') : 'none'),
      'scroll' + document.documentElement.scrollHeight
    ].join('~');
    history.replaceState({}, '', location.pathname + '?geo2=' + encodeURIComponent(out));
  } catch (e) {
    try { history.replaceState({}, '', location.pathname + '?geo2=ERR' + encodeURIComponent(e.message)); } catch (x) {}
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
    c = mqtt.Client(client_id="hermes-geo2", clean_session=True)
    c.username_pw_set("WallPanel", "DaHouse17!")
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
    if "geo2=" in u:
        print("DECODED:")
        for part in unquote(u.split("geo2=")[1]).split("~"):
            print("   ", part)
        break
    print(f"  [{i*4}s] waiting…")
else:
    print("no report; last url:", cur())

publish({"eval": "history.replaceState({}, '', '%s')" % CLEAN})
print("restored:", cur())
