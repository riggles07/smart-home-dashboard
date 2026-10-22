"""Contrast gate for the cartoon card (WCAG AA, per the requirements §8).

The numbers are computed from the tokens actually in `card.src.js`, so changing a colour
without re-checking fails the build. Two cases matter on this card and neither is obvious:

  * text sits on TRANSLUCENT panels over a photograph -- so the worst case is the palest
    pixel of the art behind it (the kitchen's stone counter), not the panel colour;
  * the temperature pill is 55 % opaque over a bright wood floor.

Both are evaluated here against measured art colours (sampled from floorplan_render.jpg by
the fitter's cue code) rather than against an assumed background.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "floorplan" / "cartoon" / "card.src.js"

# palest and most saturated pixels of the accepted render, used as worst-case backdrops
PALE_COUNTER = (228, 224, 216)
BRIGHT_WOOD = (200, 170, 120)
DARK_WALL = (60, 58, 56)
INK_ON_ART = (12, 17, 22)      # .chip background
AA = 4.5


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _lum(c) -> float:
    out = []
    for v in c:
        v /= 255
        out.append(v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def _ratio(a, b) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _over(fg, alpha, bg):
    return tuple(round(fg[i] * alpha + bg[i] * (1 - alpha)) for i in range(3))


def _token(name: str) -> tuple[int, int, int]:
    m = re.search(rf"--{name}:\s*(#[0-9a-fA-F]{{6}})", SRC.read_text())
    assert m, f"token --{name} not found in card.src.js"
    return _hex(m.group(1))


def test_panel_text_tokens_pass_aa():
    ink = _token("fpc-ink")
    panel = _token("fpc-panel")
    assert _ratio(ink, panel) >= AA

    dim = _token("fpc-ink-dim")
    row_bg = _over((255, 255, 255), 0.045, panel)
    assert _ratio(dim, row_bg) >= AA, f"meta text {_ratio(dim, row_bg):.2f}:1"


@pytest.mark.parametrize("backdrop", [PALE_COUNTER, BRIGHT_WOOD, DARK_WALL])
def test_chip_text_passes_aa_over_any_art_pixel(backdrop):
    ink = _token("fpc-ink")
    chip = _over(INK_ON_ART, 0.78, backdrop)
    assert _ratio(ink, chip) >= AA, f"chip {_ratio(ink, chip):.2f}:1 over {backdrop}"


@pytest.mark.parametrize("backdrop", [PALE_COUNTER, BRIGHT_WOOD])
def test_temperature_label_passes_aa(backdrop):
    pill = _over(INK_ON_ART, 0.55, backdrop)
    assert _ratio((255, 255, 255), pill) >= AA, f"temp {_ratio((255,255,255), pill):.2f}:1 over {backdrop}"


def test_pill_outline_meets_non_text_floor():
    for backdrop in (PALE_COUNTER, BRIGHT_WOOD):
        pill = _over(INK_ON_ART, 0.55, backdrop)
        assert _ratio((255, 255, 255), pill) >= 3.0, "1.4.11 non-text contrast"
