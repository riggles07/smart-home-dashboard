#!/usr/bin/env python3
"""Generate the cartoon/dollhouse floorplan render from the control plan.

Pipeline position:
    geometry.py -> make_control_image.py -> [this] -> fit_hotspots.py -> render_card_svg.py

The model is instructed to RESTYLE the supplied layout, not to invent one. Any
layout freedom it takes is a defect, because every hotspot polygon is derived from
the measured coordinates and validated against the render (see fit_hotspots.py).

Usage:
    python3 generate_art.py [--model gemini-3-pro-image] [--out art/render.png]

Requires GOOGLE_API_KEY in /root/.hermes/.env. Writes the raw response JSON next to
the image so a failed generation can be diagnosed without re-billing a call.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ENV = Path("/root/.hermes/.env")

PROMPT = """\
Redraw the supplied flat floor plan as a high-quality 3D architectural "dollhouse"
visualisation, in the style of a Floorplanner top-down render.

CAMERA
- Viewed from directly above with a very slight tilt, orthographic projection.
- NOT a wide-angle perspective. NOT a 45-degree isometric.

WALLS
- Light warm grey (#E8E5DF) with visible thickness of about 12 cm, tops slightly
  lighter. The outer wall is continuous.
- Interior walls follow the white wall bands in the input exactly.
- TWO PLACES ARE OPEN PLAN and must have NO wall across them: the wide opening
  between the top-left room (family room) and the top-centre room (kitchen), and the
  wide opening between the bottom-right room (living room) and the central hall
  (foyer). There the floor runs continuously from one room into the next.

FLOORS
- Every room is MEDIUM BROWN WOOD PLANK flooring -- the same warm medium brown
  throughout, with visible plank lines and a subtle grain.
- The ONLY tiled floor in the whole plan is the laundry. Of the two small rooms on
  the left of the hall, the laundry is the UPPER one -- the room containing the white
  washer and dryer, directly below the hall's upper arm. Its floor is COOL GREY
  CERAMIC TILE with a visible square grid of grout lines.
- The bathroom is the LOWER of the two small rooms -- the one with the toilet, basin
  and glass shower, below the laundry. Its floor is MEDIUM BROWN WOOD, like every
  other room. Do not tile the bathroom.
- Do NOT create an extra tiled room. The hall floor is wood right up to the
  laundry's walls. The laundry is a single small room; do not split it in two and do
  not extend its tile into the hall.

FURNITURE, by room. Match these positions exactly; do not add large items that are
not listed, and do not remove listed items.

Top-left room (family room):
- A FIREPLACE with a stone surround and a dark firebox on the LEFT (west) wall,
  centred vertically.
- TWO BLUE ARMCHAIRS side by side along the NORTH (top) edge, facing south.
- A GREY SOFA along the SOUTH (bottom) edge, facing north.
- A GOLDEN / OCHRE area RUG in the centre, between the chairs and the sofa.

Between the family room and the kitchen:
- A WOODEN KITCHEN TABLE spanning the open boundary between the two rooms, with
  two chairs; it sits in the opening, half in the family room, half in the kitchen.

Top-centre room (kitchen):
- A white counter run along the NORTH wall only, with a stainless sink and a tall
  fridge at its east end. No island, and no counter along the east wall -- the
  kitchen floor is wood everywhere except under the north counter run.

Top-right room (dining room):
- A wooden dining table with a chair on its west and east sides.

Central hall (foyer):
- A stair flight with visible treads in the upper-right of the hall, a slim wooden
  console table against the hall's west wall. Keep the hall floor clear.

Small middle-left room (laundry):
- A white washer and a white dryer side by side against the north wall of that room.

Small lower-left room (bathroom):
- A white toilet, a white basin with a small counter, and a glass shower enclosure.

Bottom-right room (living room):
- A BLUE area RUG in the centre.
- A tall wooden BOOKSHELF against the RIGHT (east) wall.
- TWO SMALL BLUE CHAIRS side by side at the SOUTHERN (bottom) end, facing north.
- No sofa in this room.

LIGHTING
- Bright, even daylight. Soft ambient occlusion in corners, gentle contact shadows
  under furniture. No harsh spotlights, no sunbeams across the floor.

FINISH
- Clean stylised realism, slightly softened edges, like a polished mobile game
  interior. NOT photorealistic, NOT a sketch, NOT cel-shaded with heavy black
  outlines.

EXCLUDE
- Absolutely no text, no labels, no numbers, no UI, no people, no pets, no plants
  outside the rooms, no watermark, no border, no vignette, no grass or landscape
  around the house.

FRAMING
- Keep the whole plan inside the frame with a small even margin, and keep every
  room's footprint, proportions and position identical to the input. Do not merge,
  split, add or remove rooms.
"""


def api_key() -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GOOGLE_API_KEY not found in /root/.hermes/.env")


def generate(model: str, control: Path, out: Path, aspect: str = "4:3",
             size: str | None = None) -> dict:
    b64 = base64.b64encode(control.read_bytes()).decode()
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ],
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": ({"aspectRatio": aspect, "imageSize": size}
                            if size else {"aspectRatio": aspect}),
        },
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key()}")
    r = requests.post(url, json=body, timeout=300)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".response.json")
    raw.write_text(r.text[:200000])
    if r.status_code != 200:
        raise SystemExit(f"HTTP {r.status_code}: {r.text[:600]}")

    data = r.json()
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    imgs = [p for p in parts if "inlineData" in p or "inline_data" in p]
    if not imgs:
        raise SystemExit(f"no image in response; text parts: "
                         f"{[p.get('text','')[:200] for p in parts]}")
    blob = imgs[0].get("inlineData") or imgs[0].get("inline_data")
    mime = blob.get("mimeType") or blob.get("mime_type") or "image/png"
    # The model returns JPEG even when asked for PNG. Rename the target to match
    # the real payload -- a .png file holding JPEG bytes breaks tooling that
    # trusts the extension (and it already fooled one viewer).
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime, ".png")
    out = out.with_suffix(ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(blob["data"]))
    return {"model": model, "out": str(out), "bytes": out.stat().st_size, "mime": mime}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.1-flash-image")
    ap.add_argument("--control", default=str(HERE / "control_plan.png"))
    ap.add_argument("--out", default=str(HERE / "art" / "render.png"))
    ap.add_argument("--aspect", default="4:3")
    ap.add_argument("--size", default=None, help="1K | 2K | 4K (model permitting)")
    a = ap.parse_args()
    print(json.dumps(generate(a.model, Path(a.control), Path(a.out), a.aspect, a.size), indent=2))
