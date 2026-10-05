#!/usr/bin/env python3
"""Colour-drift guard: generator <-> CSS must agree on every duplicated colour.

Rebuilds the 2026-10-04 worker deliverable as real pytest tests with a pure
guard() oracle so mutation tests run against TEMP COPIES and never mutate
the live tree.

Semantics (per card t_62fb0845/t_62fb2845 acceptance):
- KNOWN_PAIRS: every hex colour currently duplicated between tools/gen_flows.py
  and css/dashboard.css is mapped and asserted EQUAL.
- any single-side mutation of a paired colour breaks that pair -> violation.
- a NEW duplicated colour appearing unmapped -> violation (drift can add too).
"""
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parent.parent
GEN_FLOWS = ROOT / "tools" / "gen_flows.py"
CSS = ROOT / "css" / "dashboard.css"

_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_CSSVAR = re.compile(r"(--[a-zA-Z][\w-]*)\s*:\s*(#(?:[0-9a-fA-F]{6}|[0-9a-fA-F]{3}))\b")

# Derived empirically from live files:
#   gen hex set includes 667EEA (baseColor, gen_flows.py:339), 1F2B47 (card bg),
#   EEE (text); css vars --shd-accent/--shd-card/--shd-text hold the same values.
KNOWN_PAIRS = {
    "--shd-accent": "667EEA",
    "--shd-card": "1F2B47",
    "--shd-text": "EEEEEE",  # css: #eee (3-digit), gen: #eee -> both normalize here
}


def _norm(h: str) -> str:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return h.upper()


def _duplicated_vars(gen_text: str, css_text: str) -> dict:
    """{css_var: normalized_value} for hex colours present in BOTH texts."""
    gen_hex = {_norm(m) for m in _HEX.findall(gen_text)}
    css_vars = {name: _norm(val) for name, val in _CSSVAR.findall(css_text)}
    return {name: val for name, val in css_vars.items() if val in gen_hex}


def guard(gen_path: Path = GEN_FLOWS, css_path: Path = CSS):
    """Return a list of drift violations (empty list == clean)."""
    gen_text = gen_path.read_text(encoding="utf-8")
    css_text = css_path.read_text(encoding="utf-8")
    dup = _duplicated_vars(gen_text, css_text)
    v = []

    for var, expected in sorted(KNOWN_PAIRS.items()):
        actual = dup.get(var)
        if actual is None:
            v.append(f"{var} ({expected}) no longer duplicated/equal across "
                     f"{gen_path.name} and {css_path.name} — single-side drift")
        elif actual != expected:
            v.append(f"{var} value changed: now {actual} (expected {expected})")

    unmapped = set(dup) - set(KNOWN_PAIRS)
    if unmapped:
        v.append(f"new duplicated colour(s) not in KNOWN_PAIRS: {sorted(unmapped)} "
                 f"(add them to the pair table or de-duplicate the sources)")
    return v


def _gen_hex_set(gen_text: str) -> set:
    return {_norm(m) for m in _HEX.findall(gen_text)}


def test_guard_clean_on_current_tree():
    assert guard() == [], f"colour drift on current tree: {guard()}"


def test_all_known_pairs_cover_every_current_duplicate():
    """The pair table must map EVERY duplicated colour (no blind spots)."""
    dup = _duplicated_vars(GEN_FLOWS.read_text(encoding="utf-8"),
                           CSS.read_text(encoding="utf-8"))
    missing = set(dup) - set(KNOWN_PAIRS)
    assert not missing, f"duplicated colours missing from KNOWN_PAIRS: {sorted(missing)}"
    stale = set(KNOWN_PAIRS) - set(dup)
    assert not stale, f"KNOWN_PAIRS entries no longer duplicated: {sorted(stale)}"


def test_mutation_of_generator_is_detected(tmp_path):
    gen_copy = tmp_path / "gen_flows.py"
    gen_copy.write_text(
        GEN_FLOWS.read_text(encoding="utf-8").replace("#667eea", "#9900ff"),
        encoding="utf-8")
    v = guard(gen_copy, CSS)
    assert v, "generator colour mutation was NOT detected"
    assert any("--shd-accent" in x for x in v), f"mutation detected but wrong pair: {v}"


def test_mutation_of_css_is_detected(tmp_path):
    css_copy = tmp_path / "dashboard.css"
    css_copy.write_text(
        CSS.read_text(encoding="utf-8").replace("#667eea", "#9900ff"),
        encoding="utf-8")
    v = guard(GEN_FLOWS, css_copy)
    assert v, "CSS colour mutation was NOT detected"
    assert any("--shd-accent" in x for x in v), f"mutation detected but wrong pair: {v}"


def test_new_duplicate_colour_is_detected_as_unmapped(tmp_path):
    """Drift can also ADD a colour: mutate gen to duplicate an existing css-only value."""
    gen_copy = tmp_path / "gen_flows.py"
    gen_text = GEN_FLOWS.read_text(encoding="utf-8").replace("#667eea", "#764ba2")
    gen_copy.write_text(gen_text, encoding="utf-8")
    v = guard(gen_copy, CSS)
    assert any("--shd-accent-2" in x for x in v), f"added duplication not flagged: {v}"
