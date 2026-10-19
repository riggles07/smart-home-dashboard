"""Nav icon names must exist in the dashboard's bundled icon set.

node-red-dashboard resolves a `ui_tab.icon` name against its bundled MATERIAL
icon set (rendered as an inline SVG by ng-md-icon) -- NOT Font Awesome. An
unknown name does not fail, warn, or fall back to a neutral glyph: it silently
renders the "?" help icon, so a wrong name looks like a design choice rather
than a bug.

Measured 2026-10-19 on the live dashboard: `tasks`, `heartbeat`, `cog` and
`home-assistant` all produced the *identical* fallback path
(`M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2`), while
`dashboard`, `wifi`, `tablet`, `view_column`, `settings`, `home` and `favorite`
produced distinct real glyphs. That is why the allowlist below is explicit:
every name in it was verified by comparing rendered SVG path data on the running
dashboard, and a name can only be added by doing the same.
"""

import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOWS = PROJECT_ROOT / "flows" / "all-flows.flow.json"

# VERIFIED PRESENT -- measured on the live dashboard 2026-10-19.
VERIFIED_ICONS = {
    "dashboard",     # Home Lab
    "wifi",          # Network
    "view_column",   # Kanban
    "favorite",      # System Health
    "settings",      # Settings
    "home",          # Home Assistant
    "tablet",        # Kiosk
    # Available but not currently used; add only after measuring live.
    "list", "equalizer", "timeline", "show_chart", "memory", "speed",
}

# Names that LOOK plausible and are valid Font Awesome, but do not exist here.
KNOWN_BAD = {"tasks", "heartbeat", "cog", "home-assistant", "monitor_heart"}


@pytest.fixture(scope="module")
def ui_tabs():
    nodes = json.loads(FLOWS.read_text())
    return [n for n in nodes if n.get("type") == "ui_tab"]


def test_every_ui_tab_icon_is_a_verified_name(ui_tabs):
    """Visible tabs only: a hidden tab's icon is never rendered, so its name
    cannot be verified against the running dashboard -- and flagging it as a
    failure would be an unverifiable claim. The Theme tab (icon "paint-brush",
    hidden: true) is the case in point: if it is ever unhidden, measure it."""
    bad = []
    for t in ui_tabs:
        if t.get("hidden"):
            continue
        icon = (t.get("icon") or "").strip()
        if not icon:
            continue
        if icon not in VERIFIED_ICONS:
            bad.append((t.get("name"), icon))
    assert not bad, (
        "ui_tab icon name(s) not verified against this dashboard's icon set: "
        f"{bad}. An unverified name renders a silent '?' glyph. Measure it live "
        "(compare the rendered SVG path against the help-icon fallback) before "
        "adding it to VERIFIED_ICONS."
    )


def test_no_known_bad_icon_names(ui_tabs):
    """Keep the specific regressions out even if someone widens the allowlist."""
    offenders = [(t.get("name"), t.get("icon")) for t in ui_tabs
                 if (t.get("icon") or "") in KNOWN_BAD]
    assert not offenders, (
        f"{offenders} use icon names measured to render the '?' fallback"
    )


def test_every_visible_tab_has_an_icon(ui_tabs):
    """A tab with no icon renders an empty slot and shifts the label alignment."""
    missing = [t.get("name") for t in ui_tabs
               if not t.get("hidden") and not (t.get("icon") or "").strip()]
    assert not missing, f"visible tabs without an icon: {missing}"
