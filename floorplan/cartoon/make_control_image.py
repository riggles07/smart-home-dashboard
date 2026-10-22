#!/usr/bin/env python3
"""Render the measured plan as a flat control image for image-to-image art generation.

WHY
---
The chosen art path (decision D2 = 2b) is: generate the illustration with an image
model, then overlay traced hotspot polygons for interaction. The failure mode of
that path is a render whose rooms do not line up with the measured geometry, which
makes every hotspot a hand-fitted guess and breaks the moment the art is redone.

So the model is not asked to invent a layout. It is asked to *restyle this exact
layout*: this script emits a flat colour-block plan from `geometry.py` (the measured
cm polygons), which is fed to the image model as the input image. Hotspots can then
be derived from the same coordinates rather than traced by hand.

Colours are chosen twice over:
  * plausible as real floor materials, so the model renders floors in roughly the
    right family instead of copying garish debug colours;
  * separable in CIE-Lab, so `fit_hotspots.py` can segment the generated render back
    into rooms and verify each region against its polygon.

Output is deliberately plain: no text, no labels, no furniture, no shadows. Anything
drawn here that is not architecture is something the model will faithfully copy.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from geometry import ROOMS, STAIRS, bounds  # noqa: E402

# Room floor colours: real material families, Lab-separable neighbours.
# (Adjacent rooms in the plan must never share a family -- see palette.json.)
FLOOR = {
    "study":       (222, 205, 178),   # soft beige carpet
    "kitchen":     (206, 210, 214),   # pale stone tile
    "dining_room": (196, 172, 138),   # medium oak
    "corridor":    (214, 198, 172),   # light oak
    "laundry":     (186, 196, 200),   # cool grey tile
    "bathroom":    (176, 190, 198),   # cool blue-grey tile
    "living_room": (204, 168, 122),   # warm oak
}
WALL = (250, 250, 250)
GAP = (255, 255, 255)
PAD = 40          # px around the plan, matches the reference render's margin
SCALE = 1.6       # px per plan-cm
WALL_PX = 14      # visual wall thickness in the control image


def render(out: Path, size=(1600, 1168)) -> dict:
    x0, y0, x1, y1 = bounds()
    w = int((x1 - x0) * SCALE) + PAD * 2
    h = int((y1 - y0) * SCALE) + PAD * 2

    def T(px, py):
        return (PAD + (px - x0) * SCALE, PAD + (py - y0) * SCALE)

    im = Image.new("RGB", (w, h), GAP)
    d = ImageDraw.Draw(im)

    # Floors first.
    for rid, poly in ROOMS.items():
        d.polygon([T(*p) for p in poly], fill=FLOOR[rid])

    # Walls: stroke AFTER the fills and do not re-fill. The stroke straddles each
    # boundary, so a shared wall reads as one band of WALL_PX total, and the
    # plan keeps a continuous outline. (An earlier version re-filled the rooms to
    # hide the inner half of the stroke and erased the walls entirely.)
    for rid, poly in ROOMS.items():
        pts = [T(*p) for p in poly]
        d.line(pts + [pts[0]], fill=WALL, width=WALL_PX, joint="curve")

    # Stair treads in the foyer arm, so the model does not invent a void there.
    s = STAIRS
    sx0, sy0 = T(s["x0"], s["y0"])
    sx1, sy1 = T(s["x1"], s["y1"])
    n = s["treads"]
    for i in range(n + 1):
        y = sy0 + (sy1 - sy0) * i / n
        d.line([(sx0, y), (sx1, y)], fill=(232, 226, 214), width=5)

    # Doorways are NOT drawn here. A first attempt punched gaps by sliding a point
    # along each shared edge and left diagonal slivers in the image. The model
    # places its own openings sensibly when the wall band is clean, and hotspot
    # validation only needs room regions, not door geometry. Door-swing animation
    # is therefore driven by the art, not derived from geometry (documented in
    # docs/PHASE_CARTOON_REQUIREMENTS.md).

    im = im.resize(size, Image.LANCZOS)
    im.save(out)
    return {"control": str(out), "size": list(im.size),
            "plan_bounds": [x0, y0, x1, y1], "scale": SCALE, "pad": PAD}



if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "control_plan.png")
    print(json.dumps(render(out), indent=2))
