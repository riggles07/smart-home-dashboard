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
visualisation, the style of a Floorplanner top-down render:

- Camera: viewed from directly above with a very slight tilt, orthographic
  projection. NOT a wide-angle perspective, NOT isometric at 45 degrees.
- Walls: light warm grey (#E8E5DF) with visible thickness (about 12 cm), tops
  slightly lighter. The outer wall is continuous. Interior walls follow the white
  wall bands in the input exactly.
- Floors, room by room, matching the input's floor colours: soft beige carpet
  (top-left room), pale stone tile (top-centre), medium oak (top-right), light oak
  (the central L-shaped hall), cool grey tile (small room, middle-left), cool
  blue-grey tile (small room, lower-left), warm oak (bottom-right room).
- Furniture: simple, modern, blocky. One bed or desk+shelf in the top-left room;
  kitchen counters, sink and island in the top-centre; a dining table with four
  chairs in the top-right; a sofa, rug and side table in the bottom-right living
  room; a washer and dryer in the middle-left room; a toilet, basin and shower in
  the lower-left room; a console table and a stair flight with visible treads in
  the central hall.
- Lighting: bright, even, daylight. Soft ambient occlusion in corners, gentle
  contact shadows under furniture. No harsh spotlights, no dramatic shadows, no
  sunbeams across the floor.
- Finish: clean stylised realism, slightly softened edges, like a polished mobile
  game interior. NOT photorealistic, NOT sketched, NOT cel-shaded with heavy black
  outlines.
- Absolutely no text, no labels, no numbers, no UI, no people, no pets, no plants
  outside the rooms, no watermark, no border, no vignette.
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
