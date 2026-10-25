#!/usr/bin/env python3
"""Build the deployable custom card from the fitted hotspots + entity map.

Why a build step at all, when the card is "no build step"?

Because the polygons MUST match the image they were fitted to. Fetching hotspots.json at
runtime lets a cached JSON and a new image drift apart silently -- the exact class of bug
this project keeps hitting (a dead entity id, a stale `?v=`). So the polygons, the entity
map and the image version are baked into one file, and the version is a hash of the exact
inputs: change the art, the file changes, HA reloads it.

Outputs floorplan/cartoon/dist/floorplan-cartoon-card.js and prints the version.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ART = HERE / "art" / "floorplan_render.jpg"
HOTSPOTS = HERE / "hotspots.json"
ENTITIES = HERE / "entity_map.json"
SRC = HERE / "card.src.js"
OUT_DIR = HERE / "dist"
IMAGE_URL = "/local/floorplan/cartoon/floorplan_render.jpg"


def build(require_pass: bool = True) -> dict:
    hotspots = json.loads(HOTSPOTS.read_text())
    ents = json.loads(ENTITIES.read_text())

    if require_pass and not hotspots.get("pass"):
        failed = [r["room"] for r in hotspots.get("report", []) if not r.get("ok")]
        print(f"WARNING: hotspot gate not fully passing; failing rooms: {failed}")

    rooms = {}
    for rid, room in ents["rooms"].items():
        hs = hotspots["rooms"].get(rid)
        if not hs:
            print(f"  skip {rid}: no hotspot")
            continue
        lights = room.get("lights") or []
        switches = room.get("switches") or []
        media = room.get("media") or []
        appliances = room.get("appliances") or []
        covers = room.get("covers") or []
        locks = room.get("locks") or []
        rooms[rid] = {
            "label": room["label"],
            "points_norm": hs["points_norm"],
            "lights": lights,
            "switches": switches,
            "media": media,
            "appliances": appliances,
            "covers": covers,
            "locks": locks,
            "temp": room.get("temp"),
            "humidity": room.get("humidity"),
            "motion": room.get("motion"),
            "climate": room.get("climate"),
            "device_count": (len(lights) + len(switches) + len(media) + len(appliances)
                             + len(covers) + len(locks)
                             + (1 if room.get("climate") else 0)),
        }

    cams = []
    for c in (ents.get("cameras") or []):
        eid = c.get("entity") or ""
        if not eid.startswith("camera."):
            raise SystemExit(f"camera entry {c.get('id')!r} is not a camera.* entity: {eid!r}")
        # clamp into the art: the two exterior pins were drawn just past the bottom edge
        cams.append({"id": c["id"], "label": c.get("label", c["id"]), "entity": eid,
                     "x": min(0.99, max(0.01, float(c["x"]))),
                     "y": min(0.99, max(0.01, float(c["y"])))})

    art_bytes = ART.read_bytes()
    digest = hashlib.sha256()
    digest.update(art_bytes)
    digest.update(json.dumps(rooms, sort_keys=True).encode())
    digest.update(json.dumps(ents["house"], sort_keys=True).encode())
    digest.update(json.dumps(cams, sort_keys=True).encode())
    # The card's own source must be part of the version too. It was not, so changing
    # the JS/CSS produced the SAME ?v= and Home Assistant kept serving the cached
    # bundle for up to 31 days -- the change simply never reached the tablet.
    digest.update(SRC.read_bytes())
    version = digest.hexdigest()[:8]

    from PIL import Image
    with Image.open(ART) as im:
        art_w, art_h = im.size
    data = {"version": version, "image": IMAGE_URL, "art_w": art_w, "art_h": art_h,
            "rooms": rooms, "house": ents["house"], "cameras": cams}

    js = SRC.read_text()
    banner = (f"/* built {len(art_bytes)} B art, version {version};\n"
              f" * regenerate with floorplan/cartoon/build_card.py -- do not hand-edit the dist file */\n")
    out = (banner
           + "window.__FPC_DATA__ = " + json.dumps(data, separators=(",", ":")) + ";\n"
           + js)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / "floorplan-cartoon-card.js"
    target.write_text(out)

    return {"version": version, "out": str(target), "bytes": target.stat().st_size,
            "rooms": len(rooms), "art_kb": round(len(art_bytes) / 1024),
            "hotspot_pass": hotspots.get("pass")}


if __name__ == "__main__":
    r = build(require_pass="--allow-fail" not in sys.argv)
    print(json.dumps(r, indent=2))
