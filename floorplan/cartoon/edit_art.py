#!/usr/bin/env python3
"""Targeted correction pass on an existing render.

Full regeneration is non-deterministic: v4 had the bathroom right and a marble patch in
the kitchen, v5 fixed the kitchen and re-tiled the bathroom. Re-rolling the whole image
to change one surface is how art pipelines become unreliable, so corrections are applied
as *edits* -- the model is told to change one region and leave every other pixel alone.

Usage:
    python3 edit_art.py IN.jpg OUT.jpg "instruction ..." [--model gemini-3-pro-image]

The input image is sent as the reference; the instruction must name the region and say
explicitly what to leave untouched. Same API/auth as generate_art.py.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from generate_art import api_key  # noqa: E402

GUARD = (
    "\n\nKeep EVERYTHING else pixel-identical: same camera, same walls, same furniture "
    "positions, same lighting, same colours elsewhere. Change only what the instruction "
    "names. No text, no watermark, no border."
)


def edit(model: str, src: Path, out: Path, instruction: str, size: str | None = None) -> dict:
    mime = "image/png" if src.suffix.lower() == ".png" else "image/jpeg"
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": instruction + GUARD},
                {"inline_data": {"mime_type": mime,
                                 "data": base64.b64encode(src.read_bytes()).decode()}},
            ],
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            **({"imageConfig": {"imageSize": size}} if size else {}),
        },
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key()}")
    r = requests.post(url, json=body, timeout=300)
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.with_suffix(".response.json")).write_text(r.text[:100000])
    if r.status_code != 200:
        raise SystemExit(f"HTTP {r.status_code}: {r.text[:500]}")

    parts = (r.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    imgs = [p for p in parts if "inlineData" in p or "inline_data" in p]
    if not imgs:
        raise SystemExit(f"no image returned: {[p.get('text','')[:200] for p in parts]}")
    blob = imgs[0].get("inlineData") or imgs[0].get("inline_data")
    m = blob.get("mimeType") or blob.get("mime_type") or "image/jpeg"
    out = out.with_suffix({ "image/jpeg": ".jpg", "image/png": ".png"}.get(m, ".jpg"))
    out.write_bytes(base64.b64decode(blob["data"]))
    return {"out": str(out), "bytes": out.stat().st_size, "mime": m}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("instruction")
    ap.add_argument("--model", default="gemini-3-pro-image")
    ap.add_argument("--size", default=None)
    a = ap.parse_args()
    print(json.dumps(edit(a.model, Path(a.src), Path(a.out), a.instruction, a.size), indent=2))
