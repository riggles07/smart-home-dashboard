#!/usr/bin/env python3
"""Trace a Roborock-app map screenshot into an ha-floorplan SVG.

WHY THIS EXISTS
---------------
ha-floorplan binds entities to SVG ELEMENTS (`<path id="kitchen">`). A Roborock
map is a JPEG: no elements, no ids. It also offers no SVG export. So the only
path from "screenshot" to "interactive floorplan" is to recover the room shapes
as vector geometry, which is what this does.

The Roborock renderer paints each room a flat colour, which is what makes this
tractable: segment by colour, take connected components, and name them by
position. Rooms that share a colour (Study/Corridor are both blue; Kitchen/
Bathroom are both orange; Laundry/Living room are both gold) still separate
cleanly because they do not touch.

LIMITS, stated up front:
  - This is a TRACE, not the real floorplan. Doorways and wall openings come out
    as gaps wherever the renderer drew a wall, which is usually what you want,
    but it will not be survey-accurate.
  - Perspective screenshots cannot be traced at all (positions are not 2D).
  - Furniture and labels are excluded on purpose: they would become click targets.
"""
import json
import sys
from collections import defaultdict

import cv2
import numpy as np

SRC = "/root/.hermes/cache/images/img_53a0dc373869.jpg"
OUT_SVG = "/root/.hermes/projects/smart-home-dashboard/floorplan/floorplan.svg"
OUT_PREVIEW = "/root/.hermes/projects/smart-home-dashboard/floorplan/trace-preview.png"
OUT_JSON = "/root/.hermes/projects/smart-home-dashboard/floorplan/rooms.json"

# Colour classes, sampled from the quantised histogram of the actual screenshot.
# Tolerance is generous because the renderer textures the floor (brick/tile
# patterns), so a room's pixels are not one exact value.
# Colour families, MEASURED from the screenshot at the room label positions --
# not taken from a quantised histogram, which yields cluster centres rather than
# the paint actually used and produced a trace that labelled the Study "laundry".
# Sampled RGB: study (100,147,202), kitchen AND bathroom (216,125,94) -- genuinely
# identical, dining (139,197,192), laundry (168,167,145), corridor (114,167,230),
# living room (191,157,74). Rooms that share a family are separate connected
# components because they do not touch, so one mask still yields both.
CLASSES = {
    "blue":   (107, 157, 216),   # study + corridor
    "orange": (216, 125,  94),   # kitchen + bathroom
    # Dining room FLOOR is the saturated teal (35,205,195). The earlier
    # (139,197,192) was the dining TABLE -- a lighter tint of the same hue -- so
    # the trace drew a polygon around the furniture instead of the room.
    "teal":   ( 35, 205, 195),
    # Both "gold" rooms, MEASURED on bare floor rather than near the label.
    # Laundry is (228,190,89) -- the earlier (168,167,145) sample landed on the
    # dark label icon, not the floor, which is why Laundry silently vanished.
    # The two golds are ~52 apart in RGB, so one TOL=26 class cannot hold both.
    "gold": (228, 190, 89),
}
TOL = 26                        # per-channel; textures vary but families are far apart

# Room names by position. Assigned after measuring component centroids rather
# than guessed: see the printed table on each run.
def name_for(cls, cx, cy, W, H):
    fx, fy = cx / W, cy / H
    if cls == "teal":
        return "dining_room"
    if cls == "blue":
        return "study" if fy < 0.42 else "corridor"
    if cls == "orange":
        return "kitchen" if fy < 0.50 else "bathroom"
    if cls == "gold":
        # Both gold rooms fall inside one colour family -- the living room floor
        # is within TOL of the laundry's, so colour alone cannot split them.
        # They are far apart on the x axis, so position decides.
        return "laundry" if fx < 0.75 else "living_room"
    return "unknown"


def main():
    img = cv2.imread(SRC)
    if img is None:
        sys.exit(f"cannot read {SRC}")
    # OpenCV loads BGR. The classes below are RGB (sampled with PIL). Without this
    # conversion an RGB orange (216,125,94) is matched as a BGR blue, which is
    # exactly how the Study got traced as "kitchen" on the first two runs.
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    H, W = img.shape[:2]

    # The Roborock app draws its own UI over the map (rotate button, "Map
    # Details" sheet, bottom-right). Anything there would trace as a bogus room.
    overlay = (int(W * 0.855), int(H * 0.56), W, H)
    cv2.rectangle(img, overlay[:2], overlay[2:], (0, 0, 0), -1)

    paths = []
    report = []
    for cls, cls_rgb in CLASSES.items():
        lo = np.clip(np.array(cls_rgb, np.int16) - TOL, 0, 255).astype(np.uint8)
        hi = np.clip(np.array(cls_rgb, np.int16) + TOL, 0, 255).astype(np.uint8)
        mask = cv2.inRange(img, lo, hi)
        # close the texture holes, then open away speckle
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                                cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))

        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            if area < (W * H) * 0.004:      # ignore slivers < 0.4% of the image
                continue
            comp = (labels == i).astype(np.uint8) * 255
            conts, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            if not conts:
                continue
            c = max(conts, key=cv2.contourArea)
            # simplify: keep the shape, drop the pixel staircase
            eps = 0.004 * cv2.arcLength(c, True)
            poly = cv2.approxPolyDP(c, eps, True).reshape(-1, 2)
            if len(poly) < 3:
                continue
            cx, cy = cents[i]
            room = name_for(cls, cx, cy, W, H)
            d = "M " + " L ".join(f"{int(x)},{int(y)}" for x, y in poly) + " Z"
            paths.append((room, cls, d, area, (int(cx), int(cy)), len(poly)))
            report.append({"room": room, "class": cls, "area_px": int(area),
                           "centroid": [int(cx), int(cy)], "points": len(poly)})

    report.sort(key=lambda r: r["room"])
    print(f"image {W}x{H} | components kept: {len(paths)}\n")
    print(f"{'room':14}{'class':8}{'area px':>10}{'centroid':>16}{'pts':>5}")
    for r in report:
        print(f"  {r['room']:12}{r['class']:8}{r['area_px']:>10}{str(r['centroid']):>16}{r['points']:>5}")

    dupes = defaultdict(int)
    for r in report:
        dupes[r["room"]] += 1
    clashes = {k: v for k, v in dupes.items() if v > 1}
    if clashes:
        print(f"\nWARNING duplicate room names (ids would collide): {clashes}")

    # ---- SVG. viewBox is the screenshot's own pixel space, so coordinates
    # need no rescaling and the floorplan keeps the source aspect ratio.
    svg = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
        f'width="{W}" height="{H}">',
        '  <!-- Traced from a Roborock app map screenshot. Room ids are what',
        '       ha-floorplan binds to. Fill colours are the source app\'s own',
        '       palette; classes are kept so CSS can restyle state. -->',
    ]
    for room, cls, d, _area, _c, _n in sorted(paths):
        svg.append(f'  <path id="{room}" class="room {cls}" d="{d}" '
                   f'fill-opacity="0.55" stroke="#ffffff" stroke-width="1.5"/>')
    svg.append('</svg>')
    with open(OUT_SVG, "w") as fh:
        fh.write("\n".join(svg) + "\n")

    with open(OUT_JSON, "w") as fh:
        json.dump(report, fh, indent=2)

    # ---- preview: draw the recovered polygons back over the screenshot so the
    # trace can be checked by eye instead of trusted.
    prev = cv2.imread(SRC)
    cv2.rectangle(prev, overlay[:2], overlay[2:], (0, 0, 0), -1)
    for room, _cls, d, *_ in paths:
        pts = np.array([[int(v) for v in chunk.split(",")]
                        for chunk in d.replace("M ", "").replace(" Z", "").split(" L ")],
                       np.int32)
        cv2.polylines(prev, [pts], True, (0, 255, 0), 3)
        cv2.putText(prev, room, (int(pts[:, 0].mean()), int(pts[:, 1].mean())),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
    cv2.imwrite(OUT_PREVIEW, prev)

    print(f"\nwrote {OUT_SVG}")
    print(f"wrote {OUT_JSON}")
    print(f"wrote {OUT_PREVIEW}")


if __name__ == "__main__":
    main()
