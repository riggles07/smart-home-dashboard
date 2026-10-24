"""Ask the wall panel to report its own DOM state, over the MQTT channel it already has.

Why: kiosk mode is a client-side CSS effect, and the dashboard config + module both
verify fine server-side. To find out WHY the chrome is back, the only useful witness is
the page itself. WallPanel accepts {"eval": "<js>"} on <base>/command, so we run a small
probe in the tablet's WebView that writes its findings into the URL with replaceState()
(no navigation, no reload) and then read them back from the panel's currentUrl sensor,
which the app publishes over MQTT.

Probe answers, in one compact string:
  k<0|n>   how many kiosk-mode resource requests the page made
  cfg<0|1> whether hass.lovelace.config.kiosk_mode is visible to the card layer
  sb:...   computed style of ha-sidebar (display/visibility/width)
  hd:...   same for the header element
  w<N>     viewport width, so a mobile-only branch can be ruled in/out
"""
import json
import time

import paho.mqtt.client as mqtt
import requests

BASE = "100.104.204.118"
TOPIC = "wallpanel/mywallpanel/command"

PROBE = """
(function(){
  try {
    var ha = document.querySelector('home-assistant');
    var lov = ha && ha.hass && ha.hass.lovelace;
    var cfg = lov && lov.config && lov.config.kiosk_mode;
    var res = performance.getEntriesByType('resource')
      .filter(function(r){ return r.name.indexOf('kiosk-mode') >= 0; }).length;
    var ce = (window.customElements && customElements.get) ? !!customElements.get('kiosk-mode') : null;
    function vis(el){
      if (!el) return 'noel';
      var s = getComputedStyle(el);
      return s.display + '/' + s.visibility + '/' + s.width;
    }
    var sb = document.querySelector('ha-sidebar');
    var hdr = document.querySelector('app-header') || document.querySelector('div.header');
    var out = 'k' + res + '~cfg' + (cfg ? 1 : 0) + '~ce' + (ce ? 1 : 0)
            + '~sb:' + vis(sb) + '~hd:' + vis(hdr) + '~w' + window.innerWidth;
    history.replaceState({}, '', location.pathname + '?diag=' + encodeURIComponent(out));
  } catch (e) {
    try { history.replaceState({}, '', location.pathname + '?diag=ERR' + encodeURIComponent(e.message)); } catch (x) {}
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

print("url before:", requests.get(f"{HA}/api/states/sensor.my_wall_panel_current_url",
                                  headers=H, timeout=20).json()["state"][-60:])

c = mqtt.Client(client_id="hermes-domprobe", clean_session=True)
c.username_pw_set("WallPanel", "DaHouse17!")
c.connect(BASE, 1883, 10)
c.loop_start()
time.sleep(1)
info = c.publish(TOPIC, json.dumps({"eval": PROBE.strip()}), qos=1)
info.wait_for_publish()
print(f"eval published (mid={info.mid}, rc={info.rc})")
time.sleep(3)
c.loop_stop()
c.disconnect()

for i in range(15):
    time.sleep(4)
    url = requests.get(f"{HA}/api/states/sensor.my_wall_panel_current_url",
                       headers=H, timeout=20).json()["state"]
    if "diag=" in url:
        print(f"\nRESULT after {(i+1)*4}s:")
        print("  url:", url)
        from urllib.parse import unquote
        print("  decoded:", unquote(url.split("diag=")[1]))
        break
    print(f"  [{i*4}s] no diag yet: {url[-40:]}")
else:
    print("\nno diag reported -- eval may not have executed, or state publish is slow")
