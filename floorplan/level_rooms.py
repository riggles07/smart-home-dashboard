#!/usr/bin/env python3
"""Level the two doorway shots and crop them to the room.

WHY THIS IS "LEVEL + CROP" AND NOT A PERSPECTIVE WARP
-----------------------------------------------------
Both photos are handheld, wide-angle, shot from the doorway. A proper 4-point
rectification needs four known corners, and neither image has them:

  * laundry   -- the left jamb is hidden behind the open door, the sill is out of frame
  * bathroom  -- the shower curtain covers the back wall's lower-left corner

The standard fallback, measuring the room's vertical vanishing point from detected
edges, was TRIED AND REJECTED on this pair. Measured: 1786 "vertical" segments in the
bathroom gave a vanishing point 79 px below the bottom edge of the frame, i.e. a
40-degree convergence that no handheld shot of a room has. The wood-floor grain and
the door leaf dominated the fit, and applying it smeared the image into streaks.

The per-line estimates then disagreed with each other by ~20 degrees in sign:

    bathroom   Hough roll median -9.99 deg   head line -28.99 (a sloping soffit, junk)
    laundry    Hough roll median +9.02 deg   head line -11.00
                         eye on a rotation strip: bathroom +6, laundry -6

So the angles below are CHOSEN BY EYE from a rendered rotation strip, not derived --
a wrong rotation looks worse than none, and a derived-looking number here would be
invented precision. BATHROOM_DEG / LAUNDRY_DEG are the only guesses in the pipeline,
and they are isolated here so they are one-line changeable.

Crop boxes are in source pixels (3072x4080) and are measured, not guessed: they are
where the door leaf, casing and threshold stop.

Usage:
    python3 level_rooms.py <src-dir> <dst-dir>
"""
import os
import shutil
import sys

from PIL import Image

# id -> (left, top, right, bottom) in source pixels: the room, minus door/frame
CROP = {
    "bathroom": (1150, 100, 2760, 4080),
    "laundry":  (430, 760, 2440, 4080),
}
# id -> degrees, counter-clockwise (PIL convention). Chosen by eye; see docstring.
LEVEL = {
    "bathroom": 6.0,
    "laundry": -6.0,
}
MARGIN = 0.06     # crop this fraction off each side to remove rotation wedges


def main(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        if not name.lower().endswith((".jpg", ".jpeg")):
            continue
        room = os.path.splitext(name)[0]
        im = Image.open(os.path.join(src, name)).convert("RGB")
        out = os.path.join(dst, name)

        if room not in CROP:
            # byte-for-byte copy, NOT re-encoded: a lossy round-trip here changes
            # every pixel of the untouched rooms by a little, which makes the
            # output of the whole pipeline irreproducible and silently differs
            # from what is already on HA.
            shutil.copy2(os.path.join(src, name), out)
            print(f"{room}: copied unchanged")
            continue

        im = im.crop(CROP[room])
        angle = LEVEL[room]
        if angle:
            im = im.rotate(angle, resample=Image.BICUBIC, expand=False,
                           fillcolor=(0, 0, 0))
            w, h = im.size
            m = int(min(w, h) * MARGIN)
            im = im.crop((m, m, w - m, h - m))
        im.save(out, "JPEG", quality=96)
        print(f"{room}: crop {CROP[room]} -> {im.size[0]}x{im.size[1]}, "
              f"level {angle:+.1f} deg")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/tmp/rooms_orig",
         sys.argv[2] if len(sys.argv) > 2 else "/tmp/rooms_rect")
