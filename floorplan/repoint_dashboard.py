#!/usr/bin/env python3
"""Point the floor-plan dashboard at the self-contained SVG (?v=6, no stylesheet).

The stylesheet is now inlined inside floorplan.svg, so the dashboard must NOT
reference a separate CSS asset -- a second asset is a second thing that can go
stale, which is exactly the bug that produced "I uploaded it and nothing
changed". Bumping ?v= is mandatory either way: /local/ is served with
Cache-Control: max-age=2678400 (31 days), so an unchanged URL is never re-fetched.
"""
import json
import sys

sys.path.insert(0, "/root/.hermes/tools")
from ha_ws import HA

URL_PATH = "floor-plan"
NEW_V = 6

with HA() as ha:
    cfg = ha.call("lovelace/config", url_path=URL_PATH)
    view = cfg["views"][0]
    card = view["cards"][0]
    inner = card["config"]
    print("before:", json.dumps({"image": inner.get("image"),
                                 "stylesheet": inner.get("stylesheet"),
                                 "rules": len(inner.get("rules", []))}))
    inner["image"] = {"location": f"/local/floorplan/floorplan.svg?v={NEW_V}",
                      "cache": False}
    inner.pop("stylesheet", None)
    ha.call("lovelace/config/save", url_path=URL_PATH, config=cfg)

    # read back -- never trust the save
    back = ha.call("lovelace/config", url_path=URL_PATH)
    b = back["views"][0]["cards"][0]["config"]
    print("after :", json.dumps({"image": b.get("image"),
                                 "stylesheet": b.get("stylesheet"),
                                 "rules": len(b.get("rules", [])),
                                 "keys": sorted(b)}))
    assert b["image"]["location"].endswith(f"?v={NEW_V}"), b["image"]
    assert "stylesheet" not in b, "stylesheet still referenced"
    assert len(b.get("rules", [])) == 4, "rules changed!"
    print("OK: saved and read back")
