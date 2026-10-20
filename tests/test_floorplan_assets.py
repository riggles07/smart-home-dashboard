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


def test_renderer_reads_the_stylesheet_and_the_raw_trace():
    assert 'CSS = "floorplan.css"' in PY_SRC
    assert 'SRC = "floorplan_traced_raw.svg"' in PY_SRC, \
        "renderer must not rewrite its own output; that is how layers duplicate"


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
    exempt = (".room-photo", ".room-label")
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
    assert [p[0] for p in paths] == ROOMS
    for _id, _cls, fill in paths:
        assert fill not in ("#000000", "#000"), "SVG default fill would win if CSS failed"


def test_photos_are_clipped_and_tinted():
    images = re.findall(r'<image class="room-photo"[^>]*clip-path="url\(#clip_(\w+)\)"', SVG)
    assert sorted(images) == ["corridor", "dining_room", "kitchen", "living_room", "study"]
    for room in ROOMS:
        if room in images:
            assert f'id="clip_{room}"' in SVG, f"{room} photo is not clipped"
    assert ".room-photo" in CSS and "blur(" in CSS


def test_labels_never_intercept_a_tap():
    labels = re.findall(r"<text [^>]*>", SVG)
    assert labels and all('pointer-events="none"' in t for t in labels)


def test_hazard_entities_are_not_bound():
    """Sirens and appliance power must never be a floorplan tap target."""
    yaml = open(os.path.join(FP, "floorplan.yaml")).read()
    for banned in ("siren", "washer_power", "dryer_power", "express_mode"):
        assert banned not in yaml, f"{banned} must not appear in floorplan.yaml"
