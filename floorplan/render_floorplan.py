#!/usr/bin/env python3
"""Turn the raw traced SVG into something presentable AND self-contained.

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

WHY THE STYLESHEET IS INLINED (2026-10-20, second feedback round)
------------------------------------------------------------------
The plan needs TWO assets when the CSS is a separate file: floorplan.svg and
floorplan.css. Only the SVG got uploaded, so the card rendered the new SVG with
the OLD stylesheet -- the photo layer simply did not exist on the device, and the
rooms that have photos were painted over by an opaque fill. That is a whole class
of failure ("I uploaded it and nothing changed") and it is not worth keeping.

So the CSS is embedded in the SVG as a <style> element. ONE file to upload. The
dashboard config no longer references a stylesheet, and floorplan.css is the
SOURCE that gets inlined here -- it is not served. tests/test_floorplan_assets.py
asserts the two agree, so they cannot drift.

Input is the immutable trace (floorplan_traced_raw.svg), never our own output:
reading and rewriting the same file is how you get duplicated layers after a
second run.
"""
import json
import re
import sys

SRC = "floorplan_traced_raw.svg"
OUT = "floorplan.svg"
OUT_MIN = "floorplan_min.svg"
CSS = "floorplan.css"

# build-time override, used to render the orientation preview from the same code
_args = sys.argv[1:]
_rot = int(_args[_args.index("--rotate") + 1]) if "--rotate" in _args else None
if "--out" in _args:
    OUT = _args[_args.index("--out") + 1]
    OUT_MIN = OUT

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

# ---- photo orientation ---------------------------------------------------
# Every photo was shot with NORTH UP. On this plan north points LEFT (the
# Roborock trace is rotated 90 deg from the house's north). SVG rotate() is
# CLOCKWISE-positive, so a -90 turn sends the photo's up vector to the left:
#   (0,-1) -- rotate(-90) --> (-1,0)      up -> left
# Rotating the <image> itself keeps its own x/y/width/height box, so the box is
# pre-swapped (w<->h) about the same centre and the -90 turn maps it exactly onto
# the room bbox -- no distortion, and nothing else on the plan moves.
# Override at build time for the orientation preview: --rotate 90 --out /tmp/x.svg
PHOTO_ROTATE = -90 if _rot is None else _rot
# Base hue per room, also written as a fill="" attribute on the path. The
# attribute is the belt to the CSS's braces: it survives ANY class change,
# including the one below.
HUE = {
    "study": "#2f6ea8", "corridor": "#2f6ea8",
    "kitchen": "#a8542f", "bathroom": "#a8542f",
    "dining_room": "#177a74",
    "laundry": "#8a6d1f", "living_room": "#8a6d1f",
}
# Visible names. The SVG ids are deliberately NOT renamed: floorplan.yaml binds
# rules by id, and renaming an id silently breaks every tap on that room.
# Only the text changes -- Study actually IS the family room, and the corridor
# IS the foyer, so the label was wrong, not the id.
LABELS = {
    "study": "Family Room",
    "corridor": "Foyer",
}

css = open(CSS).read()
# An inline <style> inside an SVG that the HTML parser builds is TEXT ONLY until
# the first '<'. A '<' anywhere in the CSS -- including in a comment -- ends the
# style text, and the CSS parser then throws away that rule AND everything after
# it, silently. Measured: "<image>" in a comment truncated the sheet at 5 rules,
# so the photo tint and every ON/OFF rule never existed in the browser.
bad = [ch for ch in "<&" if ch in css]
if bad:
    raise SystemExit(f"{CSS} must not contain {'/'.join(bad)}: it would truncate "
                     f"the inlined stylesheet at that point")

lines = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}" '
    f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet">',
    '  <!-- Traced from a Roborock map; viewBox cropped to the plan itself.',
    '       Room ids are what ha-floorplan binds to.',
    '       The stylesheet is INLINED below on purpose: one file to upload, and',
    '       it cannot go stale separately from the geometry. -->',
    '  <style>',
    css.rstrip(),
    '  </style>',
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
#
# The clip lives on a wrapper <g>, NOT on the <image>: a clip-path is resolved in
# the element's own (already transformed) user space, so putting it on the image
# would rotate the clip along with the pixels and the photo would bleed out of
# its room. With the <g> holding the clip and the <image> turning inside it, the
# crop stays welded to the room and only the pixels rotate.
for room, _cls, d in sorted(paths):
    if room not in PHOTOS:
        continue
    xs_ = [int(n) for n in re.findall(r'(-?\d+),', d)]
    ys_ = [int(n) for n in re.findall(r',(-?\d+)', d)]
    x0, y0 = min(xs_), min(ys_)
    w, h = max(xs_) - x0, max(ys_) - y0
    href = f'href="/local/floorplan/rooms/{PHOTOS[room]}?v=1"'
    lines.append(f'  <g clip-path="url(#clip_{room})">')
    if PHOTO_ROTATE % 360 == 0:
        lines.append(
            f'    <image class="room-photo" x="{x0}" y="{y0}" width="{w}" height="{h}" '
            f'preserveAspectRatio="xMidYMid slice" {href}/>')
    else:
        cx, cy = x0 + w / 2, y0 + h / 2
        # lay the image out in a box that the turn maps exactly onto the room bbox
        rw, rh = (h, w) if PHOTO_ROTATE % 180 else (w, h)
        lines.append(
            f'    <image class="room-photo" x="{cx - rw / 2:g}" y="{cy - rh / 2:g}" '
            f'width="{rw}" height="{rh}" '
            f'transform="rotate({PHOTO_ROTATE} {cx:g} {cy:g})" '
            f'preserveAspectRatio="xMidYMid slice" {href}/>')
    lines.append('  </g>')

for room, cls, d in sorted(paths):
    cls = " ".join(dict.fromkeys(cls.split()))   # regex capture already has "room"
    if room in PHOTOS:
        cls += " has-photo"
    lines.append(
        f'  <path id="{room}" class="{cls}" fill="{HUE[room]}" d="{d}"/>')
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
print(f"wrote {OUT} ({len(out)} bytes, {len(paths)} rooms, {len(cent)} labels, "
      f"{len(css)} bytes of CSS inlined)")
