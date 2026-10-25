"""Turn the hand-annotated camera markup into normalised art coordinates.

The dots were drawn on a screenshot of the rendered card, so their pixel positions mean
nothing until they are mapped onto the art's own coordinate space. Two steps:

  1. find the art's bounding box in the screenshot (the plan is bright, the page behind it
     is near-black), then normalise each dot's centroid against that box;
  2. validate: the four INDOOR dots must fall inside their room's hotspot polygon (from
     hotspots.json). If a dot lands in the wrong room the mapping is wrong, and that is
     checked rather than assumed. The two exterior dots (driveway, front door) are allowed
     to sit outside the house.
"""
import json
import pathlib
import sys

import numpy as np
from PIL import Image

IMG = pathlib.Path("/root/.hermes/cache/images/img_139829408e4a.jpg")
HOT = pathlib.Path("floorplan/cartoon/hotspots.json")

im = Image.open(IMG).convert("RGB")
a = np.asarray(im).astype(int)
h, w, _ = a.shape
print(f"annotated image: {w}x{h}")

# --- 1. art bounding box ------------------------------------------------------
lum = a.sum(axis=2)
# the page background is very dark; the plan (floors, walls, concrete) is bright
bright = lum > 210
cols = np.where(bright.sum(axis=0) > h * 0.10)[0]
rows = np.where(bright.sum(axis=1) > w * 0.10)[0]
x0, x1 = int(cols.min()), int(cols.max())
y0, y1 = int(rows.min()), int(rows.max())
print(f"art bbox: x {x0}..{x1}  y {y0}..{y1}   ({x1-x0}x{y1-y0}, aspect {(x1-x0)/(y1-y0):.3f})")

# --- 2. red dot detection -----------------------------------------------------
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
red = (r > 150) & (g < 90) & (b < 90)
print(f"red pixels: {int(red.sum())}")

# flood-fill style clustering without cv2: label by scanning with a simple union-find
seen = np.zeros_like(red, dtype=bool)
blobs = []
ys, xs = np.where(red)
pts = set(zip(ys.tolist(), xs.tolist()))
for (yy, xx) in list(pts):
    if (yy, xx) not in pts or seen[yy, xx]:
        continue
    stack = [(yy, xx)]
    group = []
    seen[yy, xx] = True
    while stack:
        cy, cx = stack.pop()
        group.append((cy, cx))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = cy + dy, cx + dx
                if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx] and red[ny, nx]:
                    seen[ny, nx] = True
                    stack.append((ny, nx))
    if len(group) >= 25:                      # ignore stray anti-aliased pixels
        blobs.append(group)

blobs.sort(key=lambda gg: len(gg), reverse=True)
print(f"blobs >=25px: {len(blobs)}  sizes={[len(x) for x in blobs[:10]]}")

centroids = []
for gg in blobs[:6]:
    cy = sum(p[0] for p in gg) / len(gg)
    cx = sum(p[1] for p in gg) / len(gg)
    centroids.append((cx, cy))
centroids.sort(key=lambda c: (round(c[1] / 40), c[0]))

labels = ["driveway?", "garage?", "backyard_upper?", "kitchen?", "front_door?", "living_room?"]

# --- 3. normalise + validate against room polygons ----------------------------
def inside(poly, x, y):
    res = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            res = not res
    return res

rooms = {}
if HOT.exists():
    rooms = json.loads(HOT.read_text()).get("rooms", {})

print("\n=== dots, normalised to the art ===")
for (cx, cy) in centroids:
    nx = (cx - x0) / (x1 - x0)
    ny = (cy - y0) / (y1 - y0)
    hit = [rid for rid, r in rooms.items() if inside(r["points_norm"], nx, ny)]
    print(f"  px({cx:6.1f},{cy:6.1f})  norm({nx:.4f},{ny:.4f})  inside: {hit or 'outside the house'}")
