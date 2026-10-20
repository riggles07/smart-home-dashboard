"""Guards for the floorplan SVG/CSS pair.

Two bugs shipped past every earlier check and both were invisible in source:

1. The card needed TWO uploaded files (floorplan.svg + floorplan.css) and only
   the SVG was uploaded. The device rendered the new geometry with the old
   stylesheet, so the photo layer did not exist and every room that has a photo
   was painted over with an opaque fill. Fix: the CSS is INLINED in the SVG, the
   dashboard no longer references a stylesheet, and here we assert the two agree.

2. An inline <style> inside an HTML-parsed SVG is text only until the first
   '<'. A '<' anywhere in the CSS -- including inside a comment -- ends the style
   text, and the CSS parser then discards that rule AND every rule after it,
   silently. Measured in a real browser: one comment containing "<image>"
   truncated the sheet at 5 of 18 rules, so the photo tint and every ON/OFF rule
   never existed. The renderer now refuses to emit such a file; this test backs
   it up.

3. floorplan.class_set in ha-floorplan 1.1.5 is `element.setAttribute('class', v)`
   -- it REPLACES the whole class attribute. Any rule that needs hue or
   "has-photo" to still be in the class list breaks on the first state update.
   So every rule that paints a room must be ID-scoped.
"""
import os
import re

FP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "floorplan")
SVG = open(os.path.join(FP, "floorplan.svg")).read()
CSS = open(os.path.join(FP, "floorplan.css")).read()
PY_SRC = open(os.path.join(FP, "render_floorplan.py")).read()

ROOMS = ["bathroom", "corridor", "dining_room", "kitchen", "laundry", "living_room", "study"]
BOUND = ["study", "corridor", "living_room", "laundry"]


def _inline_css():
    m = re.search(r"<style>\n(.*?)\n\s*</style>", SVG, re.S)
    assert m, "floorplan.svg has no inline <style> block"
    return m.group(1)


def _strip_comments(text):
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _rules_with(prop):
    """Yield (selector_list, declarations) for every CSS rule setting `prop`."""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", _strip_comments(CSS)):
        sel, decl = m.group(1).strip(), m.group(2)
        if re.search(r"(^|[\s;])" + prop + r"\s*:", decl):
            out.append((sel, decl))
    return out


# ---------------------------------------------------------------- inlining
def test_stylesheet_is_inlined_verbatim():
    assert _inline_css().strip() == CSS.strip(), (
        "floorplan.svg inline CSS differs from floorplan.css -- "
        "run `python3 floorplan/render_floorplan.py`"
    )


def test_renderer_reads_the_stylesheet_and_the_geometry():
    assert 'CSS = "floorplan.css"' in PY_SRC
    assert "import geometry" in PY_SRC, "layout must come from geometry.py"
    assert 'SRC = "floorplan_traced_raw.svg"' not in PY_SRC, (
        "the renderer must not read its own output -- that is how layers duplicate "
        "and how the raw, ragged trace creeps back in")


def test_stylesheet_has_no_markup_characters():
    # '<' truncates the inlined sheet inside an HTML-parsed SVG; '&' starts an
    # entity in XML contexts. Neither belongs in a stylesheet served this way.
    assert "<" not in CSS, "a '<' in floorplan.css truncates the inlined stylesheet"
    assert "&" not in CSS, "an '&' in floorplan.css can be parsed as an entity"
    assert "<" not in _inline_css()


# ------------------------------------------------------- class_set survival
def test_every_room_painting_rule_is_id_scoped():
    """class_set replaces the class attribute -- selectors must not need it.

    .room-photo and .room-label are exempt: they style the <image> and <text>
    children, which no rule ever hands to class_set. Only the room <path>
    elements get their class attribute rewritten.
    """
    exempt = (".room-photo", ".room-label", ".stairs")
    offenders = []
    for prop in ("fill", "fill-opacity", "stroke-opacity", "filter"):
        for sel, _decl in _rules_with(prop):
            for part in [s.strip() for s in sel.split(",") if s.strip()]:
                if part.startswith("@") or part.startswith(exempt):
                    continue
                if not part.startswith("#"):
                    offenders.append(f"{part} (sets {prop})")
    assert not offenders, (
        "these rules style rooms without an id selector, so floorplan.class_set "
        "wiping the class attribute breaks them: " + "; ".join(offenders))


def test_no_rule_depends_on_hue_or_photo_classes():
    for sel, _decl in _rules_with("fill"):
        assert "has-photo" not in sel and "blue" not in sel and "gold" not in sel


def test_state_rules_exist_for_every_bound_room():
    for room in BOUND:
        assert f"#{room}.room-on" in CSS, f"{room} has no lit state"
        assert f"#{room}.room-off" in CSS, f"{room} has no unlit state"


def test_unbound_rooms_stay_inert():
    # any rule naming all three unbound rooms must be the inertness block
    hits = [(m.group(1), m.group(2)) for m in
            re.finditer(r"([^{}]+)\{([^{}]*)\}", _strip_comments(CSS))
            if all(r in m.group(1) for r in ("#kitchen", "#dining_room", "#bathroom"))]
    assert hits, "no rule covers the three unbound rooms"
    assert any("pointer-events: none" in d and "stroke-dasharray" in d for _s, d in hits), \
        "unbound rooms must look inert: pointer-events:none + dashed stroke"


# ------------------------------------------------------------- svg geometry
def test_every_room_path_carries_its_own_fill():
    paths = re.findall(r'<path id="(\w+)" class="([^"]*)" fill="(#[0-9a-f]{6})"', SVG)
    assert sorted(p[0] for p in paths) == sorted(ROOMS)
    assert len(paths) == 7
    for _id, _cls, fill in paths:
        assert fill not in ("#000000", "#000"), "SVG default fill would win if CSS failed"


def test_photos_are_clipped_and_tinted():
    """Each photo must be clipped to its own room, and the clip must be on the
    WRAPPER: a clip-path is resolved in the element's own transformed space, so a
    clip on a rotated <image> would rotate with the pixels and bleed."""
    groups = re.findall(r'<g clip-path="url\(#clip_(\w+)\)">\s*(<image[^>]*>)', SVG)
    assert sorted(g[0] for g in groups) == ["bathroom", "corridor", "dining_room",
                                            "kitchen", "laundry", "living_room", "study"]
    for room, img in groups:
        assert f'id="clip_{room}"' in SVG, f"{room} photo is not clipped"
        assert "clip-path" not in img, f"{room}: clip belongs on the <g>, not the <image>"
    assert ".room-photo" in CSS and "blur(" in CSS


def test_every_photo_is_rotated_the_same_way():
    """'Each one needs rotated' -- one unrotated room is the bug to catch."""
    want = re.search(r"PHOTO_ROTATE = (-?\d+)", PY_SRC).group(1)
    imgs = re.findall(r"<image class=\"room-photo\"[^>]*>", SVG)
    assert len(imgs) == 7
    angles = []
    for img in imgs:
        m = re.search(r'transform="rotate\((-?\d+) ', img)
        assert m, f"photo missing rotation: {img[:90]}"
        angles.append(m.group(1))
    assert set(angles) == {want}, f"rotations {set(angles)} != PHOTO_ROTATE {want}"


def test_rotation_keeps_the_photo_inside_the_room_box():
    """Turn about the box centre with w/h swapped, or the crop drifts off the room.

    Checks the turned box lands EXACTLY back on the room polygon's bbox -- that is
    what makes `slice` crop the same way before and after the rotation.
    """
    groups = re.findall(r'<g clip-path="url\(#clip_(\w+)\)">\s*(<image[^>]*>)', SVG)
    for room, img in groups:
        d = re.search(rf'<clipPath id="clip_{room}"><path d="([^"]+)"', SVG).group(1)
        pts = [(float(a), float(b)) for a, b in
               re.findall(r'(-?[\d.]+),(-?[\d.]+)', d)]
        rx0, ry0 = min(p[0] for p in pts), min(p[1] for p in pts)
        rx1, ry1 = max(p[0] for p in pts), max(p[1] for p in pts)
        w = float(re.search(r'width="([\d.]+)"', img).group(1))
        h = float(re.search(r'height="([\d.]+)"', img).group(1))
        ang, cx, cy = (float(v) for v in
                       re.search(r"rotate\((-?\d+) ([\-\d.]+) ([\-\d.]+)\)", img).groups())
        swap = int(ang) % 180 != 0
        bw, bh = (h, w) if swap else (w, h)
        assert abs((cx - bw / 2) - rx0) < 1.0, f"{room}: left edge off by {abs((cx-bw/2)-rx0):.2f}"
        assert abs((cy - bh / 2) - ry0) < 1.0, f"{room}: top edge off by {abs((cy-bh/2)-ry0):.2f}"
        assert abs((cx + bw / 2) - rx1) < 1.0, f"{room}: right edge off"
        assert abs((cy + bh / 2) - ry1) < 1.0, f"{room}: bottom edge off"


def test_labels_never_intercept_a_tap():
    labels = re.findall(r"<text [^>]*>", SVG)
    assert labels and all('pointer-events="none"' in t for t in labels)


def test_hazard_entities_are_not_bound():
    """Sirens and appliance power must never be a floorplan tap target."""
    yaml = open(os.path.join(FP, "floorplan.yaml")).read()
    for banned in ("siren", "washer_power", "dryer_power", "express_mode"):
        assert banned not in yaml, f"{banned} must not appear in floorplan.yaml"


# ------------------------------------------------- normalised geometry (2nd pass)
# The plan used to be a colour-segmentation of a Roborock screenshot: jigsaw
# notches wherever colour bled, and two rectangular holes punched by the app's
# own overlay buttons. geometry.py is the hand-set replacement. These are the
# properties that make it "normalised" rather than "rough".
import sys

sys.path.insert(0, FP)
import geometry as G  # noqa: E402


def _inside(poly, x, y):
    res = False
    for i in range(len(poly)):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % len(poly)]
        if (y0 > y) != (y1 > y):
            if x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
                res = not res
    return res


def test_every_room_is_rectilinear():
    for rid, poly in G.ROOMS.items():
        for i in range(len(poly)):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % len(poly)]
            assert x0 == x1 or y0 == y1, (
                f"{rid}: edge ({x0},{y0})->({x1},{y1}) is not axis-aligned")


def test_rooms_do_not_overlap():
    """Two rooms claiming the same floor means a tap target is ambiguous."""
    clashes = []
    for x in range(130, 1195, 4):
        for y in range(110, 895, 4):
            hits = [rid for rid, p in G.ROOMS.items() if _inside(p, x, y)]
            if len(hits) > 1:
                clashes.append((x, y, hits))
    assert not clashes, f"overlapping rooms at {clashes[:5]} ({len(clashes)} points)"


def test_neighbours_share_one_wall_coordinate():
    """A gap between two rooms renders as a black sliver that reads as a defect."""
    def edge(rid, side):
        xs = [p[0] for p in G.ROOMS[rid]]
        ys = [p[1] for p in G.ROOMS[rid]]
        return {"left": min(xs), "right": max(xs),
                "top": min(ys), "bottom": max(ys)}[side]

    assert edge("kitchen", "right") == edge("dining_room", "left")
    assert edge("dining_room", "right") == edge("living_room", "right")
    assert edge("corridor", "bottom") == edge("living_room", "bottom")
    # the foyer body's east wall IS the living room's west wall
    assert 980 in [x for x, _y in G.ROOMS["corridor"]]
    assert edge("living_room", "left") == 980


def test_living_room_fills_its_rectangle():
    """The trace cut it short and punched two button holes through it."""
    poly = G.ROOMS["living_room"]
    assert len(poly) == 4, "living room must be a plain rectangle"
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    assert (max(xs) - min(xs)) * (max(ys) - min(ys)) == G.area(poly)


def test_stairs_sit_inside_the_foyer_corner():
    s = G.STAIRS
    corners = [(s["x0"], s["y0"]), (s["x1"], s["y0"]),
               (s["x1"], s["y1"]), (s["x0"], s["y1"])]
    for x, y in corners:
        assert _inside(G.ROOMS["corridor"], x, y), f"stair corner ({x},{y}) outside the foyer"
    # top-RIGHT corner: over the middle-right of the plan, above the living room
    assert s["x0"] > 900 and s["y0"] < 500 and s["y1"] <= 590


def test_stairs_are_drawn_and_inert():
    assert 'class="stairs"' in SVG, "stairs missing from the plan"
    treads = SVG.count("<line ")
    assert treads == G.STAIRS["treads"] - 1
    block = SVG.split('class="stairs"')[1].split("</g>")[0]
    assert 'pointer-events="none"' in block, "stairs must not be a tap target"
    assert ".stairs" in CSS and "pointer-events: none" in CSS.split(".stairs")[1][:300]


# ------------------------------------------------------------------ photo weight
def test_photo_urls_are_cache_busted():
    """/local/ caches for 31 days; replacing a JPEG in place is invisible without this."""
    v = re.search(r"PHOTO_V = (\d+)", PY_SRC).group(1)
    hrefs = re.findall(r"rooms/(\w+)\.jpg\?v=(\d+)", SVG)
    assert len(hrefs) == 7, hrefs
    assert {h[1] for h in hrefs} == {v}, f"photo versions {hrefs} != PHOTO_V {v}"


def test_downscaled_photos_exist_and_are_small():
    """The originals are 1.6-2.3 MB each -- 9 MB the kiosk re-checks by URL."""
    d = os.path.join(FP, "rooms_small")
    names = sorted(os.listdir(d))
    assert names == ["bathroom.jpg", "corridor.jpg", "dining_room.jpg", "kitchen.jpg",
                     "laundry.jpg", "living_room.jpg", "study.jpg"], names
    total = 0
    for n in names:
        size = os.path.getsize(os.path.join(d, n))
        total += size
        assert size <= 130 * 1024, f"{n} is {size / 1024:.0f} kB, over the 130 kB budget"
    assert total <= 800 * 1024, f"rooms_small totals {total / 1024:.0f} kB"
