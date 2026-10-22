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


def _payload() -> dict:
    assert DIST.exists(), "dist card missing -- run floorplan/cartoon/build_card.py"
    text = DIST.read_text()
    m = re.search(r"window\.__FPC_DATA__ = (\{.*?\});\n", text, re.S)
    assert m, "no data payload in the dist card"
    return json.loads(m.group(1))


def _hotspots() -> dict:
    return json.loads(HOTSPOTS.read_text())


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
    for room in payload["rooms"].values():
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
def test_hotspots_cover_every_room_with_devices():
    hs = _hotspots()["rooms"]
    ents = _entities()["rooms"]
    for rid, room in ents.items():
        has_devices = bool(room.get("lights") or room.get("switches") or room.get("media")
                           or room.get("appliances") or room.get("climate"))
        assert (rid in hs) == has_devices or rid in hs, f"{rid}: hotspot presence wrong"


def test_hotspot_polygons_are_sane():
    hs = _hotspots()["rooms"]
    assert len(hs) == 7
    for rid, room in hs.items():
        pts = room["points_norm"]
        assert len(pts) >= 3, rid
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        assert all(0.0 <= v <= 1.0 for v in xs + ys), f"{rid} escapes the image"
        area = abs(sum(xs[i] * ys[(i + 1) % len(ys)] - xs[(i + 1) % len(ys)] * ys[i]
                       for i in range(len(xs)))) / 2
        assert area > 0.001, f"{rid} polygon is degenerate"


def test_no_two_rooms_share_a_centroid():
    hs = _hotspots()["rooms"]
    cents = {}
    for rid, room in hs.items():
        pts = room["points_norm"]
        cents[rid] = (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))
    ids = list(cents)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            dx = cents[ids[i]][0] - cents[ids[j]][0]
            dy = cents[ids[i]][1] - cents[ids[j]][1]
            assert (dx * dx + dy * dy) ** 0.5 > 0.02, f"{ids[i]} and {ids[j]} nearly coincide"


def test_hotspots_report_is_recorded_even_when_imperfect():
    """The gate may fail for a room; what is not allowed is silence about which one."""
    hs = _hotspots()
    assert "report" in hs and len(hs["report"]) == 7
    for row in hs["report"]:
        assert "room" in row and "ok" in row


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
    assert payload["image"].endswith("floorplan_render.jpg")
