"""Per-room art spec for the cartoon plan: floors, openings, furniture.

This is the file the user edits when the drawing is wrong. It is deliberately
separate from `geometry.py`, which holds *measured* architecture and must not be
touched to make a picture look better.

Coordinate space: plan centimetres, north is up (-y), origin at the source map's
top-left. Furniture is drawn as flat blocks into the control image so the image
model has unambiguous placement, and described in the prompt so it renders them in
3D rather than copying the blocks.

DIRECTIONS, as the user phrased them (2026-10-22):
    family room  -- fireplace LEFT (west) wall, two blue chairs NORTH edge,
                    sofa at the BOTTOM (south) edge, golden rug
    kitchen      -- table BETWEEN family room and kitchen, i.e. on the opening
    living room  -- blue rug, bookshelf on the RIGHT (east) wall,
                    two small blue chairs at the SOUTHERN end
"""

# Every floor is medium brown wood except the laundry, which keeps its cool tile.
WOOD = (156, 116, 80)
FLOORS = {
    "study":       WOOD,
    "kitchen":     WOOD,
    "dining_room": WOOD,
    "corridor":    WOOD,
    "living_room": WOOD,
    "bathroom":    WOOD,
    "laundry":     (186, 196, 200),   # stays as set: cool grey tile
}

# Open plan: these shared walls are not walls. Each rect is painted in the floor
# colour so the model renders a continuous opening rather than a doorway.
# (x0, y0, x1, y1) in plan cm, plus the two rooms it joins -- asserted at build time.
OPENINGS = [
    # family room <-> kitchen: study's east edge is x=454, kitchen's west edge is
    # x=457, so the opening spans that 3 cm gap and runs most of the shared length.
    {"rooms": ("study", "kitchen"), "rect": (447, 150, 464, 375)},
    # living room <-> foyer: both polygons share x=980 from y 590 to 884.
    {"rooms": ("living_room", "corridor"), "rect": (972, 630, 988, 850)},
]

# kind: used only for colour/shape language in the control image and the prompt.
# colour names are the user's words, kept verbatim so the prompt can echo them.
FURNITURE = [
    # --- family room (plan id "study") -------------------------------------
    {"room": "study", "kind": "fireplace", "colour": "stone", "rect": (140, 245, 186, 335)},
    {"room": "study", "kind": "chair", "colour": "blue", "rect": (205, 132, 255, 186)},
    {"room": "study", "kind": "chair", "colour": "blue", "rect": (300, 132, 350, 186)},
    {"room": "study", "kind": "sofa", "colour": "grey", "rect": (196, 372, 404, 424)},
    {"room": "study", "kind": "rug", "colour": "golden", "rect": (205, 225, 398, 358)},
    # table between family room and kitchen, straddling the opening
    {"room": "study", "kind": "table", "colour": "wood", "rect": (404, 236, 505, 322)},

    # --- kitchen ------------------------------------------------------------
    {"room": "kitchen", "kind": "counter", "colour": "pale", "rect": (470, 126, 900, 172)},
    {"room": "kitchen", "kind": "sink", "colour": "steel", "rect": (620, 130, 690, 168)},

    # --- dining room --------------------------------------------------------
    {"room": "dining_room", "kind": "table", "colour": "wood", "rect": (985, 190, 1115, 330)},
    {"room": "dining_room", "kind": "chair", "colour": "wood", "rect": (950, 225, 980, 295)},
    {"room": "dining_room", "kind": "chair", "colour": "wood", "rect": (1120, 225, 1150, 295)},

    # --- foyer / corridor ---------------------------------------------------
    {"room": "corridor", "kind": "console", "colour": "wood", "rect": (770, 640, 830, 800)},

    # --- laundry ------------------------------------------------------------
    {"room": "laundry", "kind": "washer", "colour": "white", "rect": (600, 545, 664, 610)},
    {"room": "laundry", "kind": "dryer", "colour": "white", "rect": (672, 545, 736, 610)},

    # --- bathroom -----------------------------------------------------------
    {"room": "bathroom", "kind": "toilet", "colour": "white", "rect": (595, 700, 640, 760)},
    {"room": "bathroom", "kind": "basin", "colour": "white", "rect": (660, 692, 730, 730)},
    {"room": "bathroom", "kind": "shower", "colour": "glass", "rect": (595, 745, 700, 775)},

    # --- living room --------------------------------------------------------
    {"room": "living_room", "kind": "rug", "colour": "blue", "rect": (1012, 660, 1148, 820)},
    {"room": "living_room", "kind": "bookshelf", "colour": "wood", "rect": (1150, 640, 1182, 800)},
    {"room": "living_room", "kind": "chair", "colour": "blue", "rect": (1016, 830, 1058, 878)},
    {"room": "living_room", "kind": "chair", "colour": "blue", "rect": (1090, 830, 1132, 878)},
]

# Control-image fills for furniture (the render gets its own materials from the prompt).
KIND_FILL = {
    "fireplace": (150, 145, 140), "chair": (78, 110, 170), "sofa": (120, 126, 134),
    "rug": (214, 178, 96), "table": (128, 88, 52), "counter": (226, 222, 214),
    "sink": (176, 182, 188), "console": (128, 88, 52), "washer": (240, 240, 240),
    "dryer": (240, 240, 240), "toilet": (245, 245, 245), "basin": (245, 245, 245),
    "shower": (196, 214, 222), "bookshelf": (110, 76, 46),
}
# The user said "blue chairs" and "golden rug"/"blue rug"; the control colour must
# follow the *word*, not the kind, or the model renders a grey chair.
COLOUR_OVERRIDE = {
    "blue": (78, 110, 170),
    "golden": (214, 178, 96),
    "grey": (120, 126, 134),
    "wood": (128, 88, 52),
    "pale": (226, 222, 214),
    "steel": (176, 182, 188),
    "stone": (150, 145, 140),
    "white": (240, 240, 240),
    "glass": (196, 214, 222),
}


def fill_for(item):
    return COLOUR_OVERRIDE.get(item["colour"], KIND_FILL.get(item["kind"], (150, 150, 150)))
