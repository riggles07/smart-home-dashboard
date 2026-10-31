"""Prove which card bundle the wall panel is actually running, and what it drew.

A resource URL change only takes effect on a full document reload, and the tablet is the one
client that cannot be inspected from here -- so the panel is asked to report on itself: an
eval command over MQTT walks the shadow roots, finds the card, records the baked version,
the floor tabs, the active layer's room ids and the art it loaded, writes that into the URL
with replaceState (no navigation), and the HA sensor hands the string back.

The floor is switched to the basement and then restored, so the room list can show whether
the lower layer still has a garage hotspot. The last thing this script does is put the URL
and the chosen floor back where they were.
"""
from __future__ import annotations

import json
import sys
import time
from urllib.parse import unquote

import paho.mqtt.client as mqtt
import requests

from mqtt_creds import creds

BROKER = "100.104.204.118"
TOPIC = "wallpanel/mywallpanel/command"

PROBE = r"""
(function(){
  function all(root, sel, out){
    var q = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (var i=0;i<q.length;i++){
      var el = q[i];
      if (sel && el.tagName && el.tagName.toLowerCase() === sel) out.push(el);
      if (el.shadowRoot) all(el.shadowRoot, sel, out);
    }
    return out;
  }
  try {
    var cards = all(document, 'floorplan-cartoon-card', []);
    var el = cards[0];
    if (!el) {
      history.replaceState({}, '', location.pathname + '?fpc=' + encodeURIComponent('NOCARD'));
      return;
    }
    function deep(sel){ var o=[]; var walk=function(r){ r.querySelectorAll(sel).forEach(function(x){o.push(x)}); r.querySelectorAll('*').forEach(function(x){ if(x.shadowRoot) walk(x.shadowRoot) }); }; walk(el.shadowRoot || el); return o; }
    var tabs = deep('.floors button');
    var act = tabs.filter(function(b){ return b.classList.contains('on') }).map(function(b){ return b.dataset.floor });
    var img = deep('.stage img')[0];
    var rooms = deep('.room').map(function(r){ return r.dataset.room || r.id });
    var stage = deep('.stage')[0];
    var out = [
      'ver:' + (el._ver || (el.constructor && el.constructor.VERSION) || '?'),
      'tabs:' + tabs.length,
      'act:' + (act[0] || '-'),
      'art:' + (img ? String(img.src).split('/').pop() : '-'),
      'rooms:' + rooms.length,
      'ids:' + rooms.join(','),
      'stage:' + (stage ? Math.round(stage.getBoundingClientRect().width) + 'x' + Math.round(stage.getBoundingClientRect().height) : '-'),
      'win:' + window.innerWidth + 'x' + window.innerHeight
    ].join('|');
    history.replaceState({}, '', location.pathname + '?fpc=' + encodeURIComponent(out));
  } catch (e) {
    try { history.replaceState({}, '', location.pathname + '?fpc=' + encodeURIComponent('ERR ' + e.message)); } catch (x) {}
  }
})()
"""

SWITCH = r"""
(function(){
  function all(root, out){
    var q = root.querySelectorAll ? root.querySelectorAll('*') : [];
    for (var i=0;i<q.length;i++){
      var el=q[i];
      if (el.tagName && el.tagName.toLowerCase()==='floorplan-cartoon-card') out.push(el);
      if (el.shadowRoot) all(el.shadowRoot, out);
    }
    return out;
  }
  var el = all(document, [])[0];
  var b = el && el.shadowRoot && el.shadowRoot.querySelector('.floors button[data-floor="%s"]');
  if (b) b.click();
  return !!b;
})()
"""


def ha_headers(env: dict) -> dict:
    return {"Authorization": "Bearer " + env["HA_TOKEN"], "Content-Type": "application/json"}


def load_env() -> dict:
    return {k: v for k, v in (l.strip().split("=", 1) for l in open("/root/.hermes/.env") if "=" in l)}


def pub(payload: dict) -> None:
    c = mqtt.Client(client_id="hermes-cardprobe", clean_session=True)
    c.username_pw_set(*creds())
    c.connect(BROKER, 1883, 10)
    c.loop_start()
    time.sleep(1)
    c.publish(TOPIC, json.dumps(payload), qos=1).wait_for_publish()
    time.sleep(2)
    c.loop_stop()
    c.disconnect()


def current_url(env: dict) -> str:
    return requests.get(env["HA_URL"].rstrip("/") + "/api/states/sensor.my_wall_panel_current_url",
                        headers=ha_headers(env), timeout=20).json()["state"]


def wait_report(env: dict, tag: str, timeout: int = 60) -> str | None:
    for _ in range(timeout // 4):
        time.sleep(4)
        u = current_url(env)
        if tag in u:
            return unquote(u.split(tag + "=", 1)[1].split("&")[0])
    return None


def main() -> int:
    env = load_env()
    if "--no-reload" not in sys.argv:
        print("reloading the panel …")
        requests.post(env["HA_URL"].rstrip("/") + "/api/services/button/press",
                      headers=ha_headers(env), json={"entity_id": "button.my_wall_panel_reload_page"},
                      timeout=30).raise_for_status()
        time.sleep(20)

    print("probing current layer …")
    pub({"eval": PROBE.strip()})
    first = wait_report(env, "fpc=")
    print("  ", first)

    orig = None
    if first:
        for part in first.split("|"):
            if part.startswith("act:"):
                orig = part[4:]

    print("switching to the basement …")
    pub({"eval": SWITCH.strip() % "2"})
    time.sleep(4)
    pub({"eval": PROBE.strip()})
    lower = wait_report(env, "fpc=")
    print("  ", lower)

    if orig and orig not in ("-", "2"):
        print("restoring floor", orig)
        pub({"eval": SWITCH.strip() % orig})
        time.sleep(3)
    pub({"eval": "history.replaceState({}, '', '%s')" % "/cartoon-plan/cartoon-plan"})
    time.sleep(2)
    print("url now:", current_url(env))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
