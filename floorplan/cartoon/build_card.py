#!/usr/bin/env python3
"""Build the deployable custom card from the fitted hotspots + entity map.

Why a build step at all, when the card is "no build step"?

Because the polygons MUST match the image they were fitted to. Fetching hotspots.json at
runtime lets a cached JSON and a new image drift apart silently -- the exact class of bug
this project keeps hitting (a dead entity id, a stale `?v=`). So the polygons, the entity
map and the image version are baked into one file, and the version is a hash of the exact
inputs: change the art, the file changes, HA reloads it.

Three layers are built: main / upper / lower. They were traced and fitted in ONE plan
frame (136..1186 x 118..884) and every render is 2400x1792, so the card swaps the image
and the room set without touching the projection.

Outputs floorplan/cartoon/dist/floorplan-cartoon-card.js and prints the version.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENTITIES = HERE / "entity_map.json"
SRC = HERE / "card.src.js"
OUT_DIR = HERE / "dist"
IMAGE_DIR = "/local/floorplan/cartoon"

# floor id -> fitted hotspot file. The art file per floor comes from entity_map.json so
# the payload and the deploy script cannot disagree about which file is which floor.
HOTSPOTS = {
    "main": HERE / "hotspots.json",
    "upper": HERE / "hotspots_upper.json",
    "lower": HERE / "hotspots_lower.json",
}
TEXTURE_KEYS = ("lights", "switches", "media", "appliances", "covers", "locks")


def build(require_pass: bool = True) -> dict:
    ents = json.loads(ENTITIES.read_text())

    floors, art_bytes, problems = [], {}, []
    for cfg in ents["floors"]:
        fid, art_name = cfg["id"], cfg["art"]
        art_path = HERE / "art" / art_name
        hs_path = HOTSPOTS[fid]
        missing = [p.name for p in (art_path, hs_path) if not p.exists()]
        if missing:
            problems.append(f"{fid}: missing {', '.join(missing)}")
            continue
        hotspots = json.loads(hs_path.read_text())
        if require_pass and not hotspots.get("pass"):
            failed = [r["room"] for r in hotspots.get("report", []) if not r.get("ok")]
            print(f"WARNING: {fid} hotspot gate not fully passing; failing rooms: {failed}")

        rooms = {}
        for rid, room in ents["rooms"].items():
            if room.get("floor", "main") != fid:
                continue
            hs = hotspots["rooms"].get(rid)
            if not hs:
                problems.append(f"{fid}/{rid}: in entity_map but no hotspot")
                continue
            lists = {k: (room.get(k) or []) for k in TEXTURE_KEYS}
            rooms[rid] = {
                "label": room["label"],
                "points_norm": hs["points_norm"],
                **lists,
                "temp": room.get("temp"),
                "humidity": room.get("humidity"),
                "motion": room.get("motion"),
                "climate": room.get("climate"),
                "device_count": (sum(len(v) for v in lists.values())
                                 + (1 if room.get("climate") else 0)),
            }

        if not rooms:
            problems.append(f"{fid}: no bindable rooms")
        # Rooms present on the plan but not in HA stay draw-only. Report them so a typo in
        # entity_map.json cannot silently drop a room from the dashboard.
        draw_only = sorted(set(hotspots["rooms"]) - set(rooms))
        art_bytes[fid] = art_path.read_bytes()
        floors.append({"id": fid, "label": cfg["label"],
                       "image": f"{IMAGE_DIR}/{art_name}",
                       "art": art_name, "rooms": rooms, "draw_only": draw_only})

    if problems:
        raise SystemExit("build failed:\n  " + "\n  ".join(problems))

    cams = []
    for c in (ents.get("cameras") or []):
        eid = c.get("entity") or ""
        if not eid.startswith("camera."):
            raise SystemExit(f"camera entry {c.get('id')!r} is not a camera.* entity: {eid!r}")
        # clamp into the art: the two exterior pins were drawn just past the bottom edge
        cams.append({"id": c["id"], "label": c.get("label", c["id"]), "entity": eid,
                     "x": min(0.99, max(0.01, float(c["x"]))),
                     "y": min(0.99, max(0.01, float(c["y"])))})

    digest = hashlib.sha256()
    for fid in sorted(art_bytes):
        digest.update(art_bytes[fid])
    for f in floors:
        digest.update(json.dumps({k: f[k] for k in ("id", "image", "rooms")},
                                 sort_keys=True).encode())
    digest.update(json.dumps(ents["house"], sort_keys=True).encode())
    digest.update(json.dumps(cams, sort_keys=True).encode())
    # The card's own source must be part of the version too. It was not, so changing
    # the JS/CSS produced the SAME ?v= and Home Assistant kept serving the cached
    # bundle for up to 31 days -- the change simply never reached the tablet.
    digest.update(SRC.read_bytes())
    version = digest.hexdigest()[:8]

    from PIL import Image
    sizes = {}
    for f in floors:
        with Image.open(HERE / "art" / f["art"]) as im:
            sizes[f["id"]] = im.size
    art_w, art_h = sizes["main"] if "main" in sizes else next(iter(sizes.values()))
    for fid, wh in sizes.items():
        if wh != (art_w, art_h):
            raise SystemExit(f"{fid} art is {wh}, expected {(art_w, art_h)}: "
                             "all layers must share one projection")

    data = {"version": version, "art_w": art_w, "art_h": art_h,
            "floors": floors, "house": ents["house"], "cameras": cams}

    js = SRC.read_text()
    banner = (f"/* built {sum(len(b) for b in art_bytes.values())} B art over "
              f"{len(floors)} floors, version {version};\n"
              f" * regenerate with floorplan/cartoon/build_card.py -- do not hand-edit the dist file */\n")
    out = (banner
           + "window.__FPC_DATA__ = " + json.dumps(data, separators=(",", ":")) + ";\n"
           + js)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    target = OUT_DIR / "floorplan-cartoon-card.js"
    target.write_text(out)

    return {"version": version, "out": str(target), "bytes": target.stat().st_size,
            "floors": {f["id"]: len(f["rooms"]) for f in floors},
            "draw_only": {f["id"]: f["draw_only"] for f in floors},
            "art_kb": {fid: round(len(b) / 1024) for fid, b in art_bytes.items()},
            "hotspot_pass": all(json.loads(p.read_text()).get("pass") for p in HOTSPOTS.values())}


if __name__ == "__main__":
    r = build(require_pass="--allow-fail" not in sys.argv)
    print(json.dumps(r, indent=2))
