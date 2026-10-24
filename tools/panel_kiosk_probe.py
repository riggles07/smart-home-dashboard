"""Shadow-DOM-aware probe of the panel's kiosk state.

v1 searched the light DOM and reported "no sidebar / no header" -- HA's chrome lives in
nested shadow roots, so that told us nothing. The module's own element map (read out of
the shipped bundle) is what the probe now walks:

    document > home-assistant .shadowRoot
             > home-assistant-main .shadowRoot
             > ha-drawer .shadowRoot > ha-sidebar
             > ha-panel-lovelace .lovelace.config.kiosk_mode
             > partial-panel-resolver > ha-panel-lovelace > hui-root > .header

Findings are written into the URL with replaceState (no reload) and read back from the
panel's currentUrl sensor.
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
  function sr(el){ return el && el.shadowRoot ? el.shadowRoot : null; }
  function q(el, sel){ var r = sr(el); return r ? r.querySelector(sel) : (el ? el.querySelector(sel) : null); }
  function vis(el){
    if (!el) return 'noel';
    var s = getComputedStyle(el);
    return s.display + '|' + s.width;
  }
  try {
    var ha = document.querySelector('home-assistant');
    var main = q(ha, 'home-assistant-main');
    var drawer = q(main, 'ha-drawer');
    var sidebar = q(drawer, 'ha-sidebar') || q(main, 'ha-sidebar');
    var panel = q(main, 'ha-panel-lovelace');
    var lov = panel && panel.lovelace;
    var cfg = lov && lov.config && lov.config.kiosk_mode;
    var hui = q(panel, 'hui-root');
    var header = hui ? q(hui, '.header') : null;
    var styles = 0;
    try {
      var r = sr(ha) || document;
      r.querySelectorAll('style').forEach(function(s){
        if ((s.textContent || '').indexOf('kiosk') >= 0 || (s.id || '').indexOf('kiosk') >= 0) styles++;
      });
      document.querySelectorAll('style').forEach(function(s){
        if ((s.textContent || '').indexOf('kiosk') >= 0) styles++;
      });
    } catch (e) {}
    var out = [
      'ha' + (ha ? 1 : 0),
      'main' + (main ? 1 : 0),
      'panl' + (panel ? 1 : 0),
      'lov' + (lov ? 1 : 0),
      'cfg' + (cfg ? 1 : 0),
      'sb:' + vis(sidebar),
      'hd:' + vis(header),
      'sty' + styles,
      'w' + window.innerWidth
    ].join('~');
    history.replaceState({}, '', location.pathname + '?diag2=' + encodeURIComponent(out));
  } catch (e) {
    try { history.replaceState({}, '', location.pathname + '?diag2=ERR' + encodeURIComponent(e.message)); } catch (x) {}
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


def current_url():
    return requests.get(f"{HA}/api/states/sensor.my_wall_panel_current_url",
                        headers=H, timeout=20).json()["state"]


c = mqtt.Client(client_id="hermes-shadowprobe", clean_session=True)
c.username_pw_set("WallPanel", "DaHouse17!")
c.connect(BASE, 1883, 10)
c.loop_start()
time.sleep(1)
c.publish(TOPIC, json.dumps({"eval": PROBE.strip()}), qos=1).wait_for_publish()
print("probe published")
time.sleep(3)
c.loop_stop()
c.disconnect()

for i in range(15):
    time.sleep(4)
    u = current_url()
    if "diag2=" in u:
        print("\nDECODED:", unquote(u.split("diag2=")[1]))
        break
    print(f"  [{i*4}s] waiting…")
else:
    print("no report; last url:", current_url())

# put the URL back so the tablet is not left on a diagnostic query string
c = mqtt.Client(client_id="hermes-cleanup", clean_session=True)
c.username_pw_set("WallPanel", "DaHouse17!")
c.connect(BASE, 1883, 10)
c.loop_start()
time.sleep(1)
c.publish(TOPIC, json.dumps({"eval": "history.replaceState({}, '', '%s')" % CLEAN}), qos=1).wait_for_publish()
time.sleep(2)
c.loop_stop()
c.disconnect()
print("restored url ->", current_url())
