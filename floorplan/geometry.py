"""Normalised main-floor geometry -- the source of truth for the plan.

WHY THIS FILE EXISTS
--------------------
`floorplan_traced_raw.svg` was machine-segmented from a Roborock phone screenshot.
That trace is honest but rough: wherever the vacuum's floor colour bled into a
doorway it carved a jigsaw notch, and the app's own "90 deg" / "layers" buttons
punched rectangular holes straight through the living room. Rooms also failed to
share walls, so black slivers showed between neighbours.

This module replaces it with hand-set **rectilinear** polygons. Every edge was
re-measured off `source-map-flat.jpg` by colour segmentation (orange/teal/gold/
blue masks, per-row min/max) rather than invented -- the numbers below are what
the map actually contains:

    study    x 136..454 (to 474 below y 384)   y 118..436
    kitchen  x 457..915                        y 118..453 (428 below x 690,
                                                         384 on the far left)
    dining   x 915..1186                       y 118..423 (438 from x 1058)
    corridor x 585..1162 top arm, 748..980 body, y 428..884
    laundry  x 586..744                        y 533..622
    bathroom x 579..744                        y 680..782
    living   x 980..1186                       y 590..884

Normalisation rules applied:
  * every edge is axis-aligned (a test enforces this);
  * neighbours share one coordinate -- kitchen 915 / dining 920 is the wall, and
    the foyer body's right edge IS the living room's left edge (980);
  * the two overlay-button holes in the living room are gone, so it fills its
    rectangle: "living room should fill out the square area";
  * the living room's right edge lines up with the dining room's (1186) and its
    bottom with the foyer's (884).

Ids are unchanged -- `floorplan.yaml` binds every rule by id, and renaming one
silently kills that room's tap.
"""

# id -> [(x, y), ...] clockwise, in the map's own pixel space (1 unit ~= 1 cm)
ROOMS = {
    "study": [
        (136, 118), (454, 118), (454, 384), (474, 384), (474, 436), (136, 436),
    ],
    "kitchen": [
        (457, 118), (915, 118), (915, 453), (690, 453), (690, 428),
        (478, 428), (478, 384), (457, 384),
    ],
    "dining_room": [
        (915, 118), (1186, 118), (1186, 438), (1058, 438), (1058, 423), (915, 423),
    ],
    "corridor": [
        # top arm under the kitchen then the dining room, right arm (the stair
        # landing), down the west side of the living room, then the body.
        (585, 428), (690, 428), (690, 453), (915, 453), (915, 438), (1162, 438),
        (1162, 590), (980, 590), (980, 884), (748, 884), (748, 533), (585, 533),
    ],
    "laundry": [(586, 533), (744, 533), (744, 622), (586, 622)],
    "bathroom": [(579, 680), (744, 680), (744, 782), (579, 782)],
    "living_room": [(980, 590), (1186, 590), (1186, 884), (980, 884)],
}

# The stair flight sits in the top-right corner of the foyer, i.e. inside the
# corridor's right arm (x 980..1162, y 438..590). Drawn in plan view: two strings
# plus evenly spaced treads.
STAIRS = {
    "x0": 986, "y0": 444, "x1": 1156, "y1": 584,
    "treads": 8,
    "label": "Stairs",
}


def bounds(rooms=None):
    pts = [p for poly in (rooms or ROOMS).values() for p in poly]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def centroid(poly):
    """Area centroid (shoelace) -- labels land inside the shape, not on a bbox."""
    a = cx = cy = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:                      # degenerate: fall back to the mean
        return (sum(p[0] for p in poly) / len(poly),
                sum(p[1] for p in poly) / len(poly))
    return cx / (6 * a), cy / (6 * a)


def area(poly):
    a = 0.0
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        a += x0 * y1 - x1 * y0
    return abs(a) * 0.5


def to_path(poly):
    return "M " + " L ".join(f"{x},{y}" for x, y in poly) + " Z"


if __name__ == "__main__":
    x0, y0, x1, y1 = bounds()
    print(f"bounds {x0},{y0} .. {x1},{y1}  ({x1 - x0} x {y1 - y0})")
    for rid, poly in ROOMS.items():
        cx, cy = centroid(poly)
        rect = all(poly[i][0] == poly[(i + 1) % len(poly)][0] or
                   poly[i][1] == poly[(i + 1) % len(poly)][1]
                   for i in range(len(poly)))
        print(f"  {rid:<12} area={area(poly):8.0f}  centroid=({cx:.0f},{cy:.0f})  "
              f"rectilinear={rect}")
