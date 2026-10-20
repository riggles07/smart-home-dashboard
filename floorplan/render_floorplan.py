#!/usr/bin/env python3
"""Turn the raw traced SVG into something presentable.

Three defects fixed here, all visible in the first on-device screenshot:

1. DEAD SPACE. The trace kept the screenshot's own viewBox (0 0 1280 1048), but
   the plan only occupies the middle of that frame. ha-floorplan renders the SVG
   as-is, so the floorplan floated small in a sea of black. Fix: crop the viewBox
   to the union of the room paths.
2. NEAR-BLACK ROOMS. With a dark page behind them, a 0.32-opacity navy room is
   indistinguishable from the background. Fix: a background plate plus opaque
   base fills, so rooms read as rooms.
3. NO LABELS. The trace intentionally drops the app's own text (it would become a
   click target), which left an unlabelled plan. Fix: <text> labels from the
   measured centroids, with pointer-events:none so they never intercept a tap.
"""
import json
import re

SRC = "floorplan.svg"
OUT = "floorplan.svg"
OUT_MIN = "floorplan_min.svg"
ROOMS = json.load(open("rooms.json"))

svg = open(SRC).read()
paths = re.findall(r'<path id="([^"]+)" class="([^"]+)" d="([^"]+)"', svg)
if not paths:
    raise SystemExit("no paths found in " + SRC)

# ---- 1. tight bounding box over every room -------------------------------
xs, ys = [], []
for _id, _cls, d in paths:
    for num in re.findall(r'(-?\d+),(-?\d+)', d):
        xs.append(int(num[0]))
        ys.append(int(num[1]))
minx, maxx = min(xs), max(xs)
miny, maxy = min(ys), max(ys)
pad = 18
vb = (minx - pad, miny - pad, (maxx - minx) + pad * 2, (maxy - miny) + pad * 2)
print(f"bbox {maxx-minx}x{maxy-miny} -> viewBox {vb[2]}x{vb[3]} "
      f"(was 1280x1048: {100*(vb[2]*vb[3])/(1280*1048):.0f}% of the old area)")

cent = {r["room"]: r["centroid"] for r in ROOMS}

# Room photos, measured 2026-10-20. Filenames as uploaded to
# /config/www/floorplan/rooms/. laundry + bathroom have none yet.
PHOTOS = {
    "study":       "study.jpg",
    "kitchen":     "kitchen.jpg",
    "dining_room": "dining_room.jpg",
    "corridor":    "corridor.jpg",
    "living_room": "living_room.jpg",
}
# Visible names. The SVG ids are deliberately NOT renamed: floorplan.yaml binds
# rules by id, and renaming an id silently breaks every tap on that room.
# Only the text changes -- Study actually IS the family room, and the corridor
# IS the foyer, so the label was wrong, not the id.
LABELS = {
    "study": "Family Room",
    "corridor": "Foyer",
}

lines = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}" '
    f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet">',
    '  <!-- Traced from a Roborock map; viewBox cropped to the plan itself.',
    '       Room ids are what ha-floorplan binds to. -->',
    # background plate: gives the dark fills something to contrast against
    f'  <rect x="{vb[0]}" y="{vb[1]}" width="{vb[2]}" height="{vb[3]}" '
    f'fill="#101a26" pointer-events="none"/>',
]
# clip paths first: each photo is clipped to exactly its own room polygon, so it
# cannot bleed into a neighbour -- which is what happens when a living-room photo
# contains the open-plan foyer behind it.
for room, _cls, d in sorted(paths):
    if room in PHOTOS:
        lines.append(f'  <clipPath id="clip_{room}"><path d="{d}"/></clipPath>')

# photos sit UNDER the room path. preserveAspectRatio="slice" crops to fill the
# polygon instead of stretching it, so a portrait phone photo does not distort.
for room, _cls, d in sorted(paths):
    if room not in PHOTOS:
        continue
    xs_ = [int(n) for n in re.findall(r'(-?\d+),', d)]
    ys_ = [int(n) for n in re.findall(r',(-?\d+)', d)]
    x0, y0 = min(xs_), min(ys_)
    w, h = max(xs_) - x0, max(ys_) - y0
    lines.append(
        f'  <image class="room-photo" x="{x0}" y="{y0}" width="{w}" height="{h}" '
        f'preserveAspectRatio="xMidYMid slice" clip-path="url(#clip_{room})" '
        f'href="/local/floorplan/rooms/{PHOTOS[room]}?v=1"/>')

for room, cls, d in sorted(paths):
    cls = " ".join(dict.fromkeys(cls.split()))   # regex capture already has "room"
    if room in PHOTOS:
        cls += " has-photo"
    lines.append(f'  <path id="{room}" class="{cls}" d="{d}"/>')
# labels last => drawn on top, but never clickable
for room, cls, _d in sorted(paths):
    c = cent.get(room)
    if not c:
        continue
    label = LABELS.get(room, room.replace("_", " ").title())
    lines.append(
        f'  <text x="{c[0]}" y="{c[1]}" class="room-label" '
        f'text-anchor="middle" dominant-baseline="middle" '
        f'pointer-events="none">{label}</text>')
lines.append('</svg>')

out = "\n".join(lines) + "\n"
open(OUT, "w").write(out)
open(OUT_MIN, "w").write(out)
print(f"wrote {OUT} ({len(out)} bytes, {len(paths)} rooms, {len(cent)} labels)")
