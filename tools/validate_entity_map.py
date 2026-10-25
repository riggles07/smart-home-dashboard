#!/usr/bin/env python3
"""Validate every entity in entity_map.json against live Home Assistant.

THE BUG THIS EXISTS FOR
-----------------------
`floorplan.yaml` bound `switch.laundry_laundry_relay`, which does not exist (the live
entity is `switch.double_relay`). The user reported "doesn't allow light control" and
the cause was a dead id that nothing checked. A config write is not a verification: HA
happily stored a rule pointing at nothing, the card rendered, and the tap did nothing.

So this runs as a gate (exit 1 on any miss) and is invoked by the test suite and by
`make deploy`. It checks:
  1. every referenced entity exists in HA;
  2. every entity id in `excluded` is at least *real* (so a stale exclusion is caught
     when the entity is renamed or removed);
  3. no room's primary_light is a `switch.*` unless the room declares `switches` only
     (a "light" binding to a switch is how the laundry id slipped through).

Usage:
    python3 tools/validate_entity_map.py [--map path] [--offline]
Exit codes: 0 = all good, 1 = missing entity or contract violation, 2 = cannot reach HA.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = ROOT / "floorplan" / "cartoon" / "entity_map.json"
ENV = Path("/root/.hermes/.env")

ENTITY_KEYS = ("primary_light", "temp", "humidity", "motion", "climate",
               "front_door", "door", "weather", "sun", "alarm_primary")
ENTITY_LIST_KEYS = ("lights", "switches", "media", "appliances", "covers", "locks",
                    "alarm_secondary")


def _env() -> tuple[str, str]:
    vals = {}
    if ENV.exists():
        for line in ENV.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    url = os.environ.get("HA_URL") or vals.get("HA_URL")
    tok = os.environ.get("HA_TOKEN") or vals.get("HA_TOKEN")
    if not url or not tok:
        raise SystemExit("HA_URL / HA_TOKEN not available")
    return url.rstrip("/"), tok


def collect(m: dict) -> list[tuple[str, str]]:
    """(entity_id, where) for everything the map references."""
    out = []
    for k in ENTITY_KEYS:
        v = m.get("house", {}).get(k)
        if v:
            out.append((v, f"house.{k}"))
    for k in ENTITY_LIST_KEYS:
        for v in m.get("house", {}).get(k, []) or []:
            out.append((v, f"house.{k}"))
    for rid, room in m.get("rooms", {}).items():
        for k in ENTITY_KEYS:
            v = room.get(k)
            if v:
                out.append((v, f"rooms.{rid}.{k}"))
        for k in ENTITY_LIST_KEYS:
            for v in room.get(k, []) or []:
                out.append((v, f"rooms.{rid}.{k}"))
    # camera pins are top-level: they sit at plan coordinates, not inside a room polygon
    for c in m.get("cameras") or []:
        eid = (c or {}).get("entity")
        if eid:
            out.append((eid, f"cameras.{c.get('id')}"))
    for eid in (m.get("excluded") or {}):
        if eid != "_comment":
            out.append((eid, "excluded"))
    return out


def contract_problems(m: dict) -> list[str]:
    """Rules that are not about existence but about shape."""
    bad = []
    for rid, room in m.get("rooms", {}).items():
        pl = room.get("primary_light")
        has_lights = bool(room.get("lights"))
        has_switches = bool(room.get("switches"))
        if pl and not (has_lights or has_switches):
            bad.append(f"{rid}: primary_light set but no lights/switches listed")
        if pl and pl.startswith("switch.") and has_lights:
            bad.append(f"{rid}: primary_light is a switch but the room lists lights "
                       f"-- pick the light, or move the switch to `switches`")
        if pl and has_lights and pl not in room["lights"]:
            bad.append(f"{rid}: primary_light {pl} is not in its own lights list")
        if pl and has_switches and not has_lights and pl not in room["switches"]:
            bad.append(f"{rid}: primary_light {pl} is not in its own switches list")
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", default=str(DEFAULT_MAP))
    ap.add_argument("--offline", action="store_true", help="skip the HA call")
    a = ap.parse_args()

    m = json.loads(Path(a.map).read_text())
    refs = collect(m)
    problems = contract_problems(m)
    for p in problems:
        print(f"CONTRACT  {p}")

    if a.offline:
        print(f"offline: {len(refs)} references, {len(problems)} contract problems")
        return 1 if problems else 0

    try:
        url, tok = _env()
    except SystemExit as e:
        print(f"SKIP: {e}")
        return 2

    hdr = {"Authorization": f"Bearer {tok}"}
    missing, seen = [], {}
    for eid, where in refs:
        if eid in seen:
            continue
        r = requests.get(f"{url}/api/states/{eid}", headers=hdr, timeout=20)
        seen[eid] = r.status_code
        if r.status_code != 200:
            missing.append((eid, where, r.status_code))

    print(f"checked {len(seen)} unique entities from {len(refs)} references")
    for eid, where, code in missing:
        print(f"MISSING  {eid:<55} ({where}, HTTP {code})")
    for p in problems:
        pass
    ok = not missing and not problems
    print("RESULT:", "PASS" if ok else f"FAIL ({len(missing)} missing, {len(problems)} contract)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
