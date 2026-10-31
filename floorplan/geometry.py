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
    # The bottom-left quadrant is not outside the house -- it is the two-car garage
    # (confirmed by the user's markup 2026-10-22). It was previously left as void, which
    # is what made the image model squeeze the middle of the plan: it saw empty space and
    # filled it. Abuts the family room on the north and the laundry/bathroom on the east.
    "garage": [(136, 436), (579, 436), (579, 884), (136, 884)],
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


# ---------------------------------------------------------------------------
# Upper and lower floors (traced 2026-10-31 from the builder's sheets)
# ---------------------------------------------------------------------------
# Both layers live in the SAME coordinate space as the main floor: the same
# 136..1186 x 118..884 frame, so the card can swap art layers without
# re-registering a single hotspot.
#
# Sheet -> plan mapping, fitted on the exterior walls (the sheets are scanned
# sideways and were normalised with rotate(90, expand=True) first):
#     upper  drawing x 385..1200 -> 361..1186   drawing y 265..832 -> 118..884
#     lower  drawing x 345..1180 -> 136..1186   drawing y 218..880 -> 118..884
#
# The upper floor does *not* sit over the garage. Its west wall is at 361, not
# 136, and the strip west of it is roof -- that is why sheet A-5 reads 1426 sq ft
# on a 1050 x 766 footprint. The roof strips are listed in ROOF below so the
# art prompt renders shingles instead of leaving a grey void.

UPPER_ROOMS = {
    # north band: master suite, shared bath, kid's room over the garage side
    "master_bath":    [(361, 118), (538, 118), (538, 395), (361, 395)],
    "walk_in_closet": [(361, 395), (538, 395), (538, 570), (361, 570)],
    "master_bedroom": [(538, 118), (811, 118), (811, 395), (538, 395)],
    "hall_bath":      [(811, 118), (932, 118), (932, 395), (811, 395)],
    "jj_room":        [(932, 118), (1186, 118), (1186, 395), (932, 395)],
    # middle band: the landing. The stair flight is drawn inside it.
    "upstairs_hall":  [(538, 395), (1186, 395), (1186, 570), (538, 570)],
    # south band: two kid's rooms either side of the two-storey stairwell
    "evie_room":      [(538, 570), (741, 570), (741, 884), (538, 884)],
    "open_below":     [(741, 570), (862, 570), (862, 884), (741, 884)],
    "colette_room":   [(862, 570), (1186, 570), (1186, 884), (862, 884)],
}

UPPER_STAIRS = {"x0": 1024, "y0": 400, "x1": 1135, "y1": 565,
                "treads": 9, "direction": "south", "label": "Stairs"}

LOWER_ROOMS = {
    # north band: media room and the big open recreation room
    "media_room": [(136, 118), (626, 118), (626, 404), (136, 404)],
    # L-shaped: the beam line at y 545 is where the rec room meets the bath band,
    # and it wraps the media room's south-east corner back to the stair side.
    "rec_room":   [(563, 404), (626, 404), (626, 118), (1186, 118),
                   (1186, 545), (563, 545)],
    # The sheet labels this corner GARAGE ROOM, but the garage is on the main floor --
    # this is the same corner seen from below: bare under-garage storage, entered from
    # the basement hall, no vehicles and no overhead doors on this level.
    "storage":        [(136, 404), (563, 404), (563, 884), (136, 884)],
    "ll_bath":        [(709, 545), (896, 545), (896, 629), (709, 629)],
    "corridor_b":     [(563, 545), (709, 545), (709, 629), (563, 629)],
    "utility":        [(563, 629), (896, 629), (896, 780), (563, 780)],
    "office":         [(896, 545), (1186, 545), (1186, 780), (896, 780)],
    "basement_hall":  [(563, 780), (1186, 780), (1186, 884), (563, 884)],
}

LOWER_STAIRS = {"x0": 909, "y0": 400, "x1": 1062, "y1": 545,
                "treads": 9, "direction": "south", "label": "Stairs"}

FLOOR_ROOMS = {"main": ROOMS, "upper": UPPER_ROOMS, "lower": LOWER_ROOMS}
FLOOR_STAIRS = {"main": STAIRS, "upper": UPPER_STAIRS, "lower": LOWER_STAIRS}

# Roof planes on a floor whose plate does not cover the whole footprint.
ROOF = {
    "upper": [
        [(136, 118), (361, 118), (361, 884), (136, 884)],   # over the garage
        [(361, 570), (538, 570), (538, 884), (361, 884)],   # attic knee-wall strip
    ],
}

FLOOR_LABEL = {"main": "Main", "upper": "Upper", "lower": "Lower"}


def floor_rooms(floor="main"):
    return FLOOR_ROOMS[floor]


def bounds_for(floor="main"):
    """All layers share the main floor's frame on purpose (see above)."""
    return bounds(ROOMS)


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
