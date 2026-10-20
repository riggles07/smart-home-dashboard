#!/usr/bin/env python3
"""Render floorplan.svg -- geometry + inline stylesheet + photos + stairs.

Inputs (all in this directory):
  geometry.py   normalised rectilinear room polygons + the stair flight
  floorplan.css the stylesheet, INLINED into the SVG (see below)
  rooms/*.jpg   served from /local/floorplan/rooms/ by HA

WHY THE STYLESHEET IS INLINED (2026-10-20)
-----------------------------------------
The plan needs TWO assets when the CSS is a separate file: floorplan.svg and
floorplan.css. Only the SVG got uploaded, so the card rendered the new SVG with
the OLD stylesheet -- the photo layer simply did not exist on the device, and the
rooms that have photos were painted over by an opaque fill. One file to upload is
worth more than the tidy separation; floorplan.css stays the SOURCE that gets
inlined here and is no longer served. tests/test_floorplan_assets.py asserts the
two agree, so they cannot drift.

GEOMETRY (2026-10-20, second pass)
---------------------------------
The plan used to come from a colour-segmented Roborock screenshot: jigsaw notches
where colours bled, and two rectangular holes punched by the app's own overlay
buttons. It is now built from geometry.py, which is hand-set, rectilinear, and
re-measured off the map -- see that file's docstring for the numbers. The stairs
are drawn in the foyer's top-right corner (the right arm of the corridor polygon)
because they were never in the robot's map at all: a vacuum cannot climb them.

The viewBox is still cropped to the union of the room polygons, and labels come
from the polygons' area centroids, so neither has to be maintained by hand.
"""
import re
import sys

import geometry

OUT = "floorplan.svg"
OUT_MIN = "floorplan_min.svg"
CSS = "floorplan.css"

# build-time override, used to render the orientation preview from the same code
_args = sys.argv[1:]
_rot = int(_args[_args.index("--rotate") + 1]) if "--rotate" in _args else None
if "--out" in _args:
    OUT = _args[_args.index("--out") + 1]
    OUT_MIN = OUT

ROOMS = geometry.ROOMS
PATHS = {rid: geometry.to_path(poly) for rid, poly in ROOMS.items()}

# ---- 1. tight bounding box over every room -------------------------------
minx, miny, maxx, maxy = geometry.bounds()
pad = 18
vb = (minx - pad, miny - pad, (maxx - minx) + pad * 2, (maxy - miny) + pad * 2)
print(f"bounds {maxx-minx}x{maxy-miny} -> viewBox {vb[2]}x{vb[3]} "
      f"({100 * vb[2] * vb[3] / (1280 * 1048):.0f}% of the raw screenshot area)")

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

# Cache-buster for the JPEGs. /local/ is served with max-age=2678400 (31 days), so
# replacing a photo in place is invisible until the URL changes. Bump this whenever
# the files behind rooms/ are replaced -- the filename stays the same on purpose,
# so the SVG is the only thing that has to be re-uploaded alongside them.
PHOTO_V = 2

# Base hue per room, also written as a fill="" attribute on the path. The
# attribute is the belt to the CSS's braces: it survives ANY class change,
# including the one floorplan.class_set performs.
HUE = {
    "study": "#2f6ea8", "corridor": "#2f6ea8",
    "kitchen": "#a8542f", "bathroom": "#a8542f",
    "dining_room": "#177a74",
    "laundry": "#8a6d1f", "living_room": "#8a6d1f",
}
CLASS = {
    "study": "room blue", "corridor": "room blue",
    "kitchen": "room orange", "bathroom": "room orange",
    "dining_room": "room teal",
    "laundry": "room gold", "living_room": "room gold",
}
# Visible names. The SVG ids are deliberately NOT renamed: floorplan.yaml binds
# rules by id, and renaming an id silently breaks every tap on that room.
# Only the text changes -- Study actually IS the family room, and the corridor
# IS the foyer, so the label was wrong, not the id.
LABELS = {
    "study": "Family Room",
    "corridor": "Foyer",
    "dining_room": "Dining Room",
    "kitchen": "Kitchen",
    "laundry": "Laundry",
    "bathroom": "Bathroom",
    "living_room": "Living Room",
}

css = open(CSS).read()
# An inline <style> inside an SVG that the HTML parser builds is TEXT ONLY until
# the first '<'. A '<' anywhere in the CSS -- including in a comment -- ends the
# style text, and the CSS parser then throws away that rule AND everything after
# it, silently. Measured: "<image>" in a comment truncated the sheet at 5 of 18
# rules, so the photo tint and every ON/OFF rule never existed in the browser.
bad = [ch for ch in "<&" if ch in css]
if bad:
    raise SystemExit(f"{CSS} must not contain {'/'.join(bad)}: it would truncate "
                     f"the inlined stylesheet at that point")

order = ["study", "kitchen", "dining_room", "corridor", "laundry", "bathroom",
         "living_room"]
assert set(order) == set(ROOMS), "order list out of sync with geometry.ROOMS"

lines = [
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{vb[0]} {vb[1]} {vb[2]} {vb[3]}" '
    f'width="100%" height="100%" preserveAspectRatio="xMidYMid meet">',
    '  <!-- Normalised main floor. Geometry: geometry.py (rectilinear, shared walls).',
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
for rid in order:
    if rid in PHOTOS:
        lines.append(f'  <clipPath id="clip_{rid}"><path d="{PATHS[rid]}"/></clipPath>')

# photos sit UNDER the room path. preserveAspectRatio="slice" crops to fill the
# polygon instead of stretching it, so a portrait phone photo does not distort.
#
# The clip lives on a wrapper <g>, NOT on the <image>: a clip-path is resolved in
# the element's own (already transformed) user space, so putting it on the image
# would rotate the clip along with the pixels and the photo would bleed out of
# its room. With the <g> holding the clip and the <image> turning inside it, the
# crop stays welded to the room and only the pixels rotate.
for rid in order:
    if rid not in PHOTOS:
        continue
    xs = [p[0] for p in ROOMS[rid]]
    ys = [p[1] for p in ROOMS[rid]]
    x0, y0 = min(xs), min(ys)
    w, h = max(xs) - x0, max(ys) - y0
    href = f'href="/local/floorplan/rooms/{PHOTOS[rid]}?v={PHOTO_V}"'
    lines.append(f'  <g clip-path="url(#clip_{rid})">')
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

for rid in order:
    cls = CLASS[rid] + (" has-photo" if rid in PHOTOS else "")
    lines.append(
        f'  <path id="{rid}" class="{cls}" fill="{HUE[rid]}" d="{PATHS[rid]}"/>')

# ---- stairs (never in the robot's map: a vacuum cannot climb them) -------
st = geometry.STAIRS
sx0, sy0, sx1, sy1 = st["x0"], st["y0"], st["x1"], st["y1"]
lines.append('  <!-- Stair flight in the top-right corner of the foyer. Drawn in plan')
lines.append('       view: two strings + evenly spaced treads. Not a tap target. -->')
lines.append('  <g class="stairs" pointer-events="none">')
lines.append(f'    <rect x="{sx0}" y="{sy0}" width="{sx1 - sx0}" height="{sy1 - sy0}"/>')
n = st["treads"]
for i in range(1, n):
    x = sx0 + (sx1 - sx0) * i / n
    lines.append(f'    <line x1="{x:.1f}" y1="{sy0}" x2="{x:.1f}" y2="{sy1}"/>')
# direction hint: a chevron pointing along the run
mid = (sy0 + sy1) / 2
lines.append(f'    <polyline points="{sx0 + 14:.1f},{mid - 11:.1f} '
             f'{sx0 + 26:.1f},{mid:.1f} {sx0 + 14:.1f},{mid + 11:.1f}"/>')
lines.append('  </g>')

# labels last => drawn on top of everything, but never clickable
for rid in order:
    cx, cy = geometry.centroid(ROOMS[rid])
    lines.append(
        f'  <text x="{cx:.0f}" y="{cy:.0f}" class="room-label" '
        f'text-anchor="middle" dominant-baseline="middle" '
        f'pointer-events="none">{LABELS[rid]}</text>')
lines.append('</svg>')

out = "\n".join(lines) + "\n"
open(OUT, "w").write(out)
open(OUT_MIN, "w").write(out)
print(f"wrote {OUT} ({len(out)} bytes, {len(ROOMS)} rooms, {len(PHOTOS)} photos, "
      f"{len(css)} bytes of CSS inlined, stairs {sx1 - sx0}x{sy1 - sy0} with {n} treads)")
