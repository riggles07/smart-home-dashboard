#!/usr/bin/env python3
"""Downscale the room photos for the floorplan card.

Why bother: the five originals are 1.6-2.3 MB each (9 MB total) because they are
straight-off-the-phone shots. The plan never shows them larger than ~300 CSS px
wide (the kitchen is 458 plan units of a 1086-unit viewBox, and the card is ~700 px
on a phone), and floorplan.css blurs them 5 px before they are drawn. So ~1100 px
on the long edge is already more than the screen can show.

Target: <= 120 kB per file, long edge 1100, quality 78, progressive, no EXIF, no
colour profile. Written to floorplan/rooms_small/ under the same filenames so the
SVG only needs a cache-busting ?v bump, not a rename.
"""
import os
import shutil

from PIL import Image

SRC = os.environ.get("ROOMS_SRC", "/tmp/rooms_orig")   # originals are NOT in the repo
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rooms_small")
MAX_EDGE = 1100
QUALITY = 78
BUDGET = 120 * 1024

os.makedirs(OUT, exist_ok=True)
rows = []
for name in sorted(os.listdir(SRC)):
    if not name.lower().endswith((".jpg", ".jpeg")):
        continue
    src = os.path.join(SRC, name)
    im = Image.open(src)
    im = im.convert("RGB")
    before = os.path.getsize(src)
    w0, h0 = im.size

    q = QUALITY
    while True:
        im2 = im.copy()
        im2.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
        dst = os.path.join(OUT, os.path.splitext(name)[0] + ".jpg")
        im2.save(dst, "JPEG", quality=q, optimize=True, progressive=True,
                 subsampling=2)          # 4:2:0: invisible after a 5 px blur
        after = os.path.getsize(dst)
        if after <= BUDGET or q <= 55:
            break
        q -= 6                                    # only give up quality if needed

    rows.append((name, (w0, h0), im.size, before, im2.size, after, q))

print(f"{'file':<18}{'original px':>14}{'new px':>13}{'before':>11}{'after':>10}"
      f"{'q':>4}{'saved':>8}")
for name, o, n, b, _, a, q in rows:
    print(f"{name:<18}{o[0]:>7}x{o[1]:<6}{n[0]:>6}x{n[1]:<6}"
          f"{b/1024:>9.0f} kB{a/1024:>8.0f} kB{q:>4}{100*(1-a/b):>7.1f}%")
tb = sum(r[3] for r in rows)
ta = sum(r[5] for r in rows)
print(f"{'TOTAL':<18}{'':>27}{tb/1024/1024:>9.2f} MB{ta/1024:>8.0f} kB"
      f"{'':>4}{100*(1-ta/tb):>7.1f}%")
