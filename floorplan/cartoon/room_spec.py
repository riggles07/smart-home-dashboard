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
    # garage: bare grey concrete, deliberately lighter than the surround so the two greys
    # cannot be confused by the "outside the house" check
    "garage":      (168, 166, 162),
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

    # --- garage (markup round 3, 2026-10-22) --------------------------------
    # "Garage interior door": east wall, top, opening into the hall by the laundry.
    {"id": "garage_interior_door", "rooms": ("garage",), "kind": "door",
     "rect": (571, 448, 587, 532)},
    # exterior pedestrian door, west wall
    {"id": "garage_exterior_door", "rooms": ("garage",), "kind": "door",
     "rect": (128, 690, 144, 772)},
    # GD L / GD R: the two overhead doors on the south wall
    {"id": "garage_door_left", "rooms": ("garage",), "kind": "garage",
     "rect": (176, 876, 344, 892)},
    {"id": "garage_door_right", "rooms": ("garage",), "kind": "garage",
     "rect": (382, 876, 550, 892)},
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

    # --- garage: shelves and bikes along the side nearest the family room ----
    {"room": "garage", "kind": "shelf", "colour": "wood", "rect": (152, 444, 336, 492)},
    {"room": "garage", "kind": "bike", "colour": "dark", "rect": (352, 446, 430, 500)},
    {"room": "garage", "kind": "bike", "colour": "dark", "rect": (446, 446, 524, 500)},

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
    "fridge": (188, 194, 200), "shelf": (150, 110, 74), "bike": (72, 76, 82),
}
COLOUR_OVERRIDE = {
    "blue": (78, 110, 170), "golden": (214, 178, 96), "grey": (120, 126, 134),
    "wood": (128, 88, 52), "pale": (226, 222, 214), "steel": (176, 182, 188),
    "stone": (150, 145, 140), "white": (240, 240, 240), "glass": (196, 214, 222),
    "dark": (72, 76, 82),
}


def fill_for(item):
    return COLOUR_OVERRIDE.get(item["colour"], KIND_FILL.get(item["kind"], (150, 150, 150)))


# ===========================================================================
# Upper and lower floors (traced 2026-10-31 from sheets A-5 and A-3)
# ===========================================================================
# Same coordinate space as the main floor (see geometry.py). Extra furniture
# kinds get their fill here rather than in KIND_FILL, so the main floor's
# palette cannot drift when a bedroom is added.

TILE = (186, 196, 200)        # cool grey ceramic, same as the laundry
# The sheet shows carpet upstairs; the dashboard keeps one wood tone so the control
# image and the art prompt cannot disagree about a bedroom floor.
CARPET = WOOD
CONCRETE = (168, 166, 162)    # garage slab, same as the main garage
ROOF_FILL = (108, 100, 96)    # shingle plane, only used for roof polygons

KIND_FILL.update({
    "bed": (196, 198, 206), "nightstand": (128, 88, 52), "dresser": (128, 88, 52),
    "wardrobe": (110, 76, 46), "tub": (245, 245, 245), "vanity": (226, 222, 214),
    "desk": (128, 88, 52), "tv": (60, 62, 68), "pool_table": (46, 104, 78),
    "car": (96, 104, 116), "water_heater": (206, 206, 210),
    "furnace": (150, 152, 158), "freezer": (240, 240, 240),
    "washer": (240, 240, 240), "dryer": (240, 240, 240),
    "sofa": (120, 126, 134), "chair": (78, 110, 170), "rug": (214, 178, 96),
    "table": (128, 88, 52), "shelf": (150, 110, 74), "bookshelf": (110, 76, 46),
    "toilet": (245, 245, 245), "basin": (245, 245, 245), "shower": (196, 214, 222),
})

UPPER_FLOORS = {
    "master_bath":    TILE,
    "walk_in_closet": CARPET,
    "master_bedroom": CARPET,
    "hall_bath":      TILE,
    "jj_room":        CARPET,
    "upstairs_hall":  (156, 116, 80),
    "evie_room":      CARPET,
    "open_below":     (156, 116, 80),
    "colette_room":   CARPET,
}

UPPER_OPENINGS = [
    # master suite: bedroom -> bath, bedroom -> closet
    {"id": "mbed_mbath", "rooms": ("master_bedroom", "master_bath"), "kind": "door",
     "rect": (528, 150, 548, 230)},
    {"id": "mbed_wic", "rooms": ("master_bedroom", "walk_in_closet"), "kind": "open",
     "rect": (545, 470, 630, 500)},
    # hall doors
    {"id": "hall_mbed", "rooms": ("master_bedroom", "upstairs_hall"), "kind": "door",
     "rect": (640, 385, 720, 405)},
    {"id": "hall_hallbath", "rooms": ("hall_bath", "upstairs_hall"), "kind": "door",
     "rect": (855, 385, 905, 405)},
    {"id": "hall_jj", "rooms": ("jj_room", "upstairs_hall"), "kind": "door",
     "rect": (1020, 385, 1075, 405)},
    {"id": "hall_evie", "rooms": ("evie_room", "upstairs_hall"), "kind": "door",
     "rect": (600, 560, 660, 580)},
    {"id": "hall_colette", "rooms": ("colette_room", "upstairs_hall"), "kind": "door",
     "rect": (980, 560, 1040, 580)},
]

UPPER_FURNITURE = [
    # --- master bedroom -----------------------------------------------------
    {"room": "master_bedroom", "kind": "bed", "colour": "pale", "rect": (596, 140, 754, 330)},
    {"room": "master_bedroom", "kind": "nightstand", "colour": "wood", "rect": (556, 146, 590, 196)},
    {"room": "master_bedroom", "kind": "nightstand", "colour": "wood", "rect": (760, 146, 794, 196)},
    {"room": "master_bedroom", "kind": "dresser", "colour": "wood", "rect": (770, 300, 806, 380)},
    {"room": "master_bedroom", "kind": "chair", "colour": "grey", "rect": (560, 330, 610, 380)},
    # --- master bath --------------------------------------------------------
    {"room": "master_bath", "kind": "tub", "colour": "white", "rect": (370, 126, 440, 300)},
    {"room": "master_bath", "kind": "vanity", "colour": "pale", "rect": (452, 126, 530, 176)},
    {"room": "master_bath", "kind": "toilet", "colour": "white", "rect": (452, 210, 500, 262)},
    {"room": "master_bath", "kind": "shower", "colour": "glass", "rect": (370, 314, 470, 382)},
    # --- walk-in closet: two runs of hanging space --------------------------
    {"room": "walk_in_closet", "kind": "wardrobe", "colour": "wood", "rect": (368, 404, 530, 440)},
    {"room": "walk_in_closet", "kind": "wardrobe", "colour": "wood", "rect": (368, 452, 420, 562)},
    # --- shared bath --------------------------------------------------------
    {"room": "hall_bath", "kind": "tub", "colour": "white", "rect": (818, 126, 926, 214)},
    {"room": "hall_bath", "kind": "vanity", "colour": "pale", "rect": (818, 246, 880, 292)},
    {"room": "hall_bath", "kind": "toilet", "colour": "white", "rect": (886, 246, 926, 296)},
    # --- kid's rooms --------------------------------------------------------
    {"room": "jj_room", "kind": "bed", "colour": "blue", "rect": (996, 144, 1128, 296)},
    {"room": "jj_room", "kind": "desk", "colour": "wood", "rect": (1140, 150, 1180, 280)},
    {"room": "jj_room", "kind": "dresser", "colour": "wood", "rect": (948, 300, 986, 384)},
    {"room": "evie_room", "kind": "bed", "colour": "golden", "rect": (560, 604, 700, 764)},
    {"room": "evie_room", "kind": "desk", "colour": "wood", "rect": (706, 610, 736, 730)},
    {"room": "evie_room", "kind": "dresser", "colour": "wood", "rect": (560, 800, 690, 840)},
    {"room": "colette_room", "kind": "bed", "colour": "grey", "rect": (900, 604, 1040, 764)},
    {"room": "colette_room", "kind": "desk", "colour": "wood", "rect": (1050, 610, 1082, 730)},
    {"room": "colette_room", "kind": "dresser", "colour": "wood", "rect": (1100, 780, 1176, 824)},
    # --- hall: a console at the landing ------------------------------------
    {"room": "upstairs_hall", "kind": "console", "colour": "wood", "rect": (600, 468, 660, 520)},
]

LOWER_FLOORS = {
    "media_room":    CARPET,
    "rec_room":      CARPET,
    "garage_lower":  CONCRETE,
    "ll_bath":       TILE,
    "corridor_b":    (156, 116, 80),
    "utility":       CONCRETE,
    "office":        (156, 116, 80),
    "basement_hall": (156, 116, 80),
}

LOWER_OPENINGS = [
    {"id": "media_rec", "rooms": ("media_room", "rec_room"), "kind": "open",
     "rect": (616, 200, 636, 340)},
    {"id": "rec_hall", "rooms": ("rec_room", "corridor_b"), "kind": "open",
     "rect": (600, 535, 700, 555)},
    {"id": "hall_bath", "rooms": ("ll_bath", "corridor_b"), "kind": "door",
     "rect": (700, 560, 718, 615)},
    {"id": "utility_door", "rooms": ("utility", "corridor_b"), "kind": "door",
     "rect": (600, 620, 660, 638)},
    {"id": "office_door", "rooms": ("office", "basement_hall"), "kind": "door",
     "rect": (940, 770, 1000, 790)},
    {"id": "garage_house", "rooms": ("garage_lower", "basement_hall"), "kind": "door",
     "rect": (548, 800, 566, 856)},
    # two overhead doors, south wall -- same as the main plan's garage
    {"id": "garage_door_l", "rooms": ("garage_lower",), "kind": "garage",
     "rect": (170, 872, 330, 890)},
    {"id": "garage_door_r", "rooms": ("garage_lower",), "kind": "garage",
     "rect": (365, 872, 525, 890)},
]

LOWER_FURNITURE = [
    # --- media room: tiered seating facing the screen wall ------------------
    {"room": "media_room", "kind": "tv", "colour": "dark", "rect": (170, 128, 590, 160)},
    {"room": "media_room", "kind": "sofa", "colour": "grey", "rect": (200, 210, 400, 262)},
    {"room": "media_room", "kind": "sofa", "colour": "grey", "rect": (200, 300, 400, 352)},
    {"room": "media_room", "kind": "rug", "colour": "blue", "rect": (190, 196, 420, 366)},
    {"room": "media_room", "kind": "shelf", "colour": "wood", "rect": (440, 200, 480, 340)},
    # --- recreation room ----------------------------------------------------
    {"room": "rec_room", "kind": "pool_table", "colour": "green", "rect": (700, 180, 920, 340)},
    {"room": "rec_room", "kind": "sofa", "colour": "grey", "rect": (980, 150, 1160, 200)},
    {"room": "rec_room", "kind": "chair", "colour": "blue", "rect": (660, 430, 740, 500)},
    {"room": "rec_room", "kind": "rug", "colour": "golden", "rect": (680, 160, 940, 360)},
    # --- office -------------------------------------------------------------
    {"room": "office", "kind": "desk", "colour": "wood", "rect": (930, 600, 1090, 660)},
    {"room": "office", "kind": "chair", "colour": "grey", "rect": (980, 670, 1030, 716)},
    {"room": "office", "kind": "bookshelf", "colour": "wood", "rect": (1140, 580, 1180, 740)},
    # --- utility ------------------------------------------------------------
    {"room": "utility", "kind": "water_heater", "colour": "pale", "rect": (580, 646, 640, 706)},
    {"room": "utility", "kind": "furnace", "colour": "steel", "rect": (660, 646, 730, 716)},
    {"room": "utility", "kind": "freezer", "colour": "white", "rect": (800, 646, 880, 700)},
    {"room": "utility", "kind": "shelf", "colour": "wood", "rect": (580, 726, 880, 762)},
    # --- lower bath ---------------------------------------------------------
    {"room": "ll_bath", "kind": "tub", "colour": "white", "rect": (716, 552, 780, 622)},
    {"room": "ll_bath", "kind": "toilet", "colour": "white", "rect": (790, 552, 830, 596)},
    {"room": "ll_bath", "kind": "basin", "colour": "white", "rect": (840, 552, 888, 592)},
    # --- garage: two bays, shelves against the house wall -------------------
    {"room": "garage_lower", "kind": "car", "colour": "grey", "rect": (170, 470, 320, 700)},
    {"room": "garage_lower", "kind": "car", "colour": "grey", "rect": (360, 470, 510, 700)},
    {"room": "garage_lower", "kind": "shelf", "colour": "wood", "rect": (150, 740, 340, 790)},
]


class _FloorSpec:
    """Small namespace so make_control_image can take a floor by name."""

    def __init__(self, floors, openings, furniture, stair_direction="east"):
        self.FLOORS = floors
        self.OPENINGS = openings
        self.FURNITURE = furniture
        self.STAIR_DIRECTION = stair_direction

    def fill_for(self, item):
        return fill_for(item)


_SPECS = {
    "main": _FloorSpec(FLOORS, OPENINGS, FURNITURE, STAIR_DIRECTION),
    "upper": _FloorSpec(UPPER_FLOORS, UPPER_OPENINGS, UPPER_FURNITURE, "south"),
    "lower": _FloorSpec(LOWER_FLOORS, LOWER_OPENINGS, LOWER_FURNITURE, "south"),
}


def for_floor(floor="main"):
    return _SPECS[floor]
