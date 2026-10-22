"""Per-room art spec for the cartoon plan: floors, openings, furniture.

This is the file the user edits when the drawing is wrong. It is deliberately
separate from `geometry.py`, which holds *measured* architecture and must not be
touched to make a picture look better.

Coordinate space: plan centimetres, north is up (-y).

Markup round 2 (2026-10-22, image annotations) drove the kitchen and circulation
changes below. Each entry names the annotation it came from so a future reader can
trace why a block sits where it does.
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

# Open plan / doorways. Each rect is painted in the floor colour so the model renders
# an opening instead of a wall. `kind` distinguishes a cased opening from a door leaf.
OPENINGS = [
    # family room <-> kitchen: the user's first message ("open room between family room
    # and kitchen, kitchen table between them"). Kept wide.
    {"id": "family_kitchen", "rooms": ("study", "kitchen"), "kind": "open",
     "rect": (447, 150, 464, 375)},

    # "Kitchen Door" (red ellipse, north wall at the kitchen's west end): a doorway in
    # the NORTH wall, so the counter cannot start until east of it.
    {"id": "kitchen_north_door", "rooms": ("kitchen",), "kind": "door",
     "rect": (498, 126, 592, 168)},

    # "Open doorway" (green, lower-left of the kitchen): kitchen -> hall.
    {"id": "kitchen_hall", "rooms": ("kitchen", "corridor"), "kind": "open",
     "rect": (520, 430, 640, 462)},

    # unlabelled green marks at the kitchen/dining wall: kitchen -> dining room.
    {"id": "kitchen_dining", "rooms": ("kitchen", "dining_room"), "kind": "open",
     "rect": (906, 285, 928, 400)},

    # living room <-> foyer (first message: "living room should also be open to foyer")
    {"id": "living_foyer", "rooms": ("living_room", "corridor"), "kind": "open",
     "rect": (972, 630, 988, 850)},

    # "Front door" (red, bottom edge): door in the south wall of the foyer.
    {"id": "front_door", "rooms": ("corridor",), "kind": "door",
     "rect": (800, 872, 884, 890)},
]

# kind: shape language in the control image and in the prompt.
FURNITURE = [
    # --- family room (plan id "study") -------------------------------------
    {"room": "study", "kind": "fireplace", "colour": "stone", "rect": (140, 245, 186, 335)},
    {"room": "study", "kind": "chair", "colour": "blue", "rect": (205, 132, 255, 186)},
    {"room": "study", "kind": "chair", "colour": "blue", "rect": (300, 132, 350, 186)},
    {"room": "study", "kind": "sofa", "colour": "grey", "rect": (196, 372, 404, 424)},
    {"room": "study", "kind": "rug", "colour": "golden", "rect": (205, 225, 398, 358)},
    # table between family room and kitchen, straddling the opening
    {"room": "study", "kind": "table", "colour": "wood", "rect": (404, 236, 505, 322)},

    # --- kitchen: annotation-driven ----------------------------------------
    # "Island" (black box, kitchen centre)
    {"room": "kitchen", "kind": "island", "colour": "pale", "rect": (665, 275, 795, 370)},
    # "Counter" (thick black line): north run, then a return down the east wall
    {"room": "kitchen", "kind": "counter", "colour": "pale", "rect": (600, 126, 900, 172)},
    {"room": "kitchen", "kind": "counter", "colour": "pale", "rect": (858, 172, 900, 330)},
    {"room": "kitchen", "kind": "sink", "colour": "steel", "rect": (700, 132, 790, 168)},
    # "Fridge" (black outline, south wall of the kitchen)
    {"room": "kitchen", "kind": "fridge", "colour": "steel", "rect": (700, 398, 785, 448)},

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

# "Stair direction" (arrow, pointing east): the flight ascends toward +x, so treads are
# drawn perpendicular to travel -- vertical lines -- and the arrow points east.
STAIR_DIRECTION = "east"

KIND_FILL = {
    "fireplace": (150, 145, 140), "chair": (78, 110, 170), "sofa": (120, 126, 134),
    "rug": (214, 178, 96), "table": (128, 88, 52), "counter": (226, 222, 214),
    "sink": (176, 182, 188), "console": (128, 88, 52), "washer": (240, 240, 240),
    "dryer": (240, 240, 240), "toilet": (245, 245, 245), "basin": (245, 245, 245),
    "shower": (196, 214, 222), "bookshelf": (110, 76, 46), "island": (222, 218, 210),
    "fridge": (188, 194, 200),
}
COLOUR_OVERRIDE = {
    "blue": (78, 110, 170), "golden": (214, 178, 96), "grey": (120, 126, 134),
    "wood": (128, 88, 52), "pale": (226, 222, 214), "steel": (176, 182, 188),
    "stone": (150, 145, 140), "white": (240, 240, 240), "glass": (196, 214, 222),
}


def fill_for(item):
    return COLOUR_OVERRIDE.get(item["colour"], KIND_FILL.get(item["kind"], (150, 150, 150)))
