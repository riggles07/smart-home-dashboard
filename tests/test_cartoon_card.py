"""Gates for the cartoon floorplan card.

These are the checks that would have caught the failures this phase actually produced:
a dead entity id (the laundry relay), a hotspot that drifted off its room, a card whose
SVG viewBox made every label 10,000 px wide, and a payload that no longer matches the
art it was fitted to.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CARTOON = ROOT / "floorplan" / "cartoon"
DIST = CARTOON / "dist" / "floorplan-cartoon-card.js"
HOTSPOTS = CARTOON / "hotspots.json"
ENTITIES = CARTOON / "entity_map.json"
ART = CARTOON / "art" / "floorplan_render.jpg"

# Art filename per floor. The main floor keeps its original name, so the deployed
# path for it never changes; every other floor is `render_<floor>.jpg`.
FLOOR_ART = {"main": "floorplan_render.jpg", "upper": "render_upper.jpg",
             "lower": "render_lower.jpg"}
# Rooms that are drawn but deliberately not tappable: a stairwell void has no floor
# to stand on, and the lower garage is not bound so the GDO doors cannot appear on
# two floors at once.
UNBOUND_OK = {
    "open_below",      # stairwell void: no floor to stand on
    "garage_lower",    # drawn but unbound so the GDO doors cannot appear on two floors
    "corridor_b",      # passage, no devices
    "hall_bath",       # upstairs shared bath: no light/switch in HA
    "walk_in_closet",  # no light/switch in HA
    "ll_bath",         # lower bath: no light/switch in HA
    "utility",         # leak sensor only: nothing switchable
}


def _payload() -> dict:
    assert DIST.exists(), "dist card missing -- run floorplan/cartoon/build_card.py"
    text = DIST.read_text()
    m = re.search(r"window\.__FPC_DATA__ = (\{.*?\});\n", text, re.S)
    assert m, "no data payload in the dist card"
    return json.loads(m.group(1))


def _hotspots(floor: str = "main") -> dict:
    path = HOTSPOTS if floor == "main" else CARTOON / f"hotspots_{floor}.json"
    assert path.exists(), f"no hotspots for {floor}: {path}"
    return json.loads(path.read_text())


def _floors() -> dict:
    """id -> floor record from the baked payload."""
    return {f["id"]: f for f in _payload()["floors"]}


def _entity_rooms() -> dict:
    """room id -> entity record, with the floor it belongs to."""
    return _entities()["rooms"]


def _entities() -> dict:
    return json.loads(ENTITIES.read_text())


# --- the original bug ---------------------------------------------------------------
def test_dead_laundry_entity_is_gone():
    """`switch.laundry_laundry_relay` never existed; the live id is `switch.double_relay`."""
    raw = ENTITIES.read_text() + DIST.read_text() + (ROOT / "floorplan" / "floorplan.yaml").read_text()
    assert "switch.laundry_laundry_relay" not in raw


def test_every_payload_entity_is_in_the_map():
    ents = _entities()
    known = set()
    for key in ("alarm_primary", "weather", "sun"):
        v = ents["house"].get(key)
        if v:
            known.add(v)
    known.update(ents["house"].get("alarm_secondary") or [])
    for room in ents["rooms"].values():
        for key in ("primary_light", "temp", "humidity", "motion", "climate", "front_door", "door"):
            if room.get(key):
                known.add(room[key])
        for key in ("lights", "switches", "media", "appliances"):
            known.update(room.get(key) or [])
    payload = _payload()
    used = set()
    for floor in payload["floors"]:
        for room in floor["rooms"].values():
            for key in ("temp", "humidity", "motion", "climate"):
                if room.get(key):
                    used.add(room[key])
            for key in ("lights", "switches", "media", "appliances"):
                used.update(room.get(key) or [])
    for key in ("alarm_primary", "weather", "sun"):
        if payload["house"].get(key):
            used.add(payload["house"][key])
    assert used <= known, f"card uses entities missing from entity_map.json: {used - known}"


def test_entity_map_contract():
    """A 'primary_light' that is a switch while the room lists lights is how the laundry id slipped."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("vem", ROOT / "tools" / "validate_entity_map.py")
    vem = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vem)
    problems = vem.contract_problems(_entities())
    assert not problems, problems


# --- hotspots -----------------------------------------------------------------------
def test_camera_pins_are_declared_and_inside_the_art():
    """Every camera the markup pointed at must be a pin with in-range plan coordinates.

    The pins are positioned by hand from an annotated screenshot, so the two ways this
    breaks are silent: a typo'd entity (pin opens nothing) and a coordinate outside
    0..1 (pin renders off the art, or under the HUD).
    """
    cams = _payload().get("cameras")
    assert cams, "no camera pins in the payload"
    assert len(cams) == 6, f"expected 6 camera pins, got {len(cams)}"
    assert len({c["id"] for c in cams}) == len(cams), "duplicate camera ids"
    for c in cams:
        assert c["entity"].startswith("camera."), c
        assert 0.0 <= c["x"] <= 1.0 and 0.0 <= c["y"] <= 1.0, f"{c['id']} off the art: {c}"
        assert c["label"], f"{c['id']} has no label"


def test_camera_pins_come_from_the_entity_map():
    """The payload must not invent cameras: the map is the single source."""
    mapped = {c["entity"] for c in _entities().get("cameras") or []}
    baked = {c["entity"] for c in _payload().get("cameras") or []}
    assert baked == mapped, f"payload/map camera mismatch: {baked ^ mapped}"


def test_hotspots_cover_every_room_with_devices():
    """Every room the map gives devices to must be tappable on the floor it sits on.

    Rooms may be drawn without being bound (the stairwell void, the lower garage), but
    the reverse -- a device with no hotspot -- is a dead button. Checked per floor,
    because each floor has its own independently fitted polygon set.
    """
    per_floor: dict[str, dict] = {}
    for rid, room in _entity_rooms().items():
        floor = room.get("floor")
        assert floor in FLOOR_ART, f"{rid} has floor={floor!r}, not one of {sorted(FLOOR_ART)}"
        per_floor.setdefault(floor, {})[rid] = room
    assert set(per_floor) == set(FLOOR_ART), f"floors without rooms: {set(FLOOR_ART) - set(per_floor)}"
    for floor, rooms in per_floor.items():
        hs = _hotspots(floor)
        assert hs["floor"] == floor, f"{floor} hotspot file is mislabelled as {hs['floor']}"
        for rid, room in rooms.items():
            assert rid in hs["rooms"], f"{floor}/{rid} is bound but has no hotspot"


def test_draw_only_rooms_are_not_tappable() -> None:
    """Drawn but unbound is legitimate; bound with nothing to control is not."""
    ents = _entity_rooms()
    for floor in FLOOR_ART:
        for rid in _hotspots(floor)["rooms"]:
            if rid not in ents:
                assert rid in UNBOUND_OK, f"{floor}/{rid} is drawn but never bound -- typo?"
                continue
            room = ents[rid]
            # Readings count too: a room with only a temperature still opens a sheet worth
            # reading, so "no light switch" is not the same as "nothing to show".
            has_devices = bool(room.get("lights") or room.get("switches") or room.get("media")
                               or room.get("appliances") or room.get("climate")
                               or room.get("covers") or room.get("locks")
                               or room.get("temp") or room.get("humidity")
                               or room.get("motion"))
            assert has_devices, f"{floor}/{rid} has a hotspot but nothing to control"


def test_hotspot_polygons_are_sane():
    total = 0
    for floor in FLOOR_ART:
        hs = _hotspots(floor)["rooms"]
        total += len(hs)
        assert len(hs) >= 3, f"{floor} has only {len(hs)} hotspots"
        for rid, room in hs.items():
            pts = room["points_norm"]
            assert len(pts) >= 3, f"{floor}/{rid}"
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            assert all(0.0 <= v <= 1.0 for v in xs + ys), f"{floor}/{rid} escapes the image"
            area = abs(sum(xs[i] * ys[(i + 1) % len(ys)] - xs[(i + 1) % len(ys)] * ys[i]
                           for i in range(len(xs)))) / 2
            assert area > 0.001, f"{floor}/{rid} polygon is degenerate"
    assert total >= 20, f"only {total} hotspots across {len(FLOOR_ART)} floors"


def test_no_two_rooms_share_a_centroid():
    for floor in FLOOR_ART:
        hs = _hotspots(floor)["rooms"]
        cents = {}
        for rid, room in hs.items():
            pts = room["points_norm"]
            cents[rid] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
        ids = list(cents)
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                dx = cents[ids[i]][0] - cents[ids[j]][0]
                dy = cents[ids[i]][1] - cents[ids[j]][1]
                assert (dx * dx + dy * dy) ** 0.5 > 0.02, \
                    f"{floor}: {ids[i]} and {ids[j]} nearly coincide"


def test_hotspots_report_is_recorded_even_when_imperfect():
    """The gate may fail for a room; what is not allowed is silence about which one."""
    for floor in FLOOR_ART:
        hs = _hotspots(floor)
        assert "report" in hs, f"{floor}: no fit report"
        assert len(hs["report"]) == len(hs["rooms"]), f"{floor}: report/hotspot count differs"
        for row in hs["report"]:
            assert "room" in row and "ok" in row, f"{floor}: malformed report row {row}"


# --- card code ----------------------------------------------------------------------
def test_card_has_no_svg_filters():
    """Perf budget: filters are banned, glow is a gradient (see requirements §7)."""
    text = DIST.read_text()
    assert "feGaussianBlur" not in text
    assert "feDropShadow" not in text


def test_card_sizes_svg_in_art_pixels():
    """A 1x1 viewBox turned a 13px label into 13 user units (10,400 screen px)."""
    text = DIST.read_text()
    assert 'viewBox="0 0 ${ART_W} ${ART_H}"' in text or "viewBox" in text
    assert "ART_W / w" in text, "no --k scaling hook"
    assert not re.search(r'viewBox="0 0 1 1"', text), "1x1 viewBox regression"


def test_card_never_treats_unavailable_as_off():
    text = DIST.read_text()
    assert "unavailable" in text
    assert "disabled" in text, "a dead entity must disable its control, not read as off"


# --- art asset ----------------------------------------------------------------------
def test_art_asset_is_present_and_big_enough():
    assert ART.exists(), "art render missing"
    data = ART.read_bytes()
    assert data[:2] == b"\xff\xd8", "art is not a JPEG (the model returns JPEG even when asked for PNG)"
    assert len(data) < 4 * 1024 * 1024, f"art is {len(data)/1024/1024:.1f} MB"
    from PIL import Image
    with Image.open(ART) as im:
        assert im.size[0] >= 2400, f"art is only {im.size[0]} px wide; kiosk needs >= 2400"


def test_payload_version_matches_art_and_hotspots():
    payload = _payload()
    assert payload["version"], "no version in payload"
    assert payload["art_w"] == 2400 and payload["art_h"] == 1792
    for floor in payload["floors"]:
        fid = floor["id"]
        assert floor["image"].endswith(FLOOR_ART[fid]), \
            f"{fid}: payload points at {floor['image']}, expected {FLOOR_ART[fid]}"
        assert floor["art"], f"{fid}: no hotspots baked in"
        assert (CARTOON / "art" / FLOOR_ART[fid]).exists(), f"missing art file for {fid}"


def test_every_floor_has_art_and_rooms():
    """The switcher is only honest if each tab leads somewhere."""
    payload = _payload()
    ids = [f["id"] for f in payload["floors"]]
    assert ids[0] == "main", "the default floor must be the main floor"
    assert len(set(ids)) == len(ids), f"duplicate floor ids: {ids}"
    labels = [f["label"] for f in payload["floors"]]
    assert len(set(labels)) == len(labels), f"duplicate floor labels: {labels}"
    for f in payload["floors"]:
        assert f.get("label"), f"{f['id']} has no label for the tab"
        assert 2 <= len(f["label"]) <= 9, f"{f['id']} label {f['label']!r} will not fit the tab"
        assert f["rooms"], f"{f['id']} has no rooms"


def test_no_room_id_appears_on_two_floors():
    """`rooms` is flat in the entity map, so an id clash silently moves a room."""
    seen: dict[str, str] = {}
    for rid, room in _entity_rooms().items():
        floor = room["floor"]
        assert rid not in seen, f"{rid} appears on both {seen.get(rid)} and {floor}"
        seen[rid] = floor


def test_art_for_every_floor_matches_the_payload_size():
    from PIL import Image
    for fid, name in FLOOR_ART.items():
        path = CARTOON / "art" / name
        assert path.exists(), f"missing {name}"
        with Image.open(path) as im:
            assert im.size == (2400, 1792), f"{fid} art is {im.size}, expected (2400, 1792)"
            assert im.format == "JPEG", f"{fid} art is {im.format}"


def test_geometry_covers_exactly_the_payload_floors():
    """Geometry, control guides and the card must agree on the floor set.

    A floor added to one and not the other renders an empty layer: a tab that leads
    to nothing.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("geom", ROOT / "floorplan" / "geometry.py")
    geom = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(geom)
    assert set(geom.FLOOR_ROOMS) == set(FLOOR_ART), \
        f"geometry floors {set(geom.FLOOR_ROOMS)} != payload floors {set(FLOOR_ART)}"
    for fid, rooms in geom.FLOOR_ROOMS.items():
        assert rooms, f"{fid} has no geometry"
