#!/usr/bin/env python3
"""Guard the dynamic background engine: it must be WIRED, not just present.

History: the first attempt at this card shipped `js/background.js` as a file that
nothing loaded. A grep for its name across the generated flows returned zero
hits, so the engine never ran in the browser -- while the file itself looked
complete and reasonable. The card was failed for exactly that.

So these assertions are about DELIVERY, not existence:
  1. the engine is inlined into a GLOBAL-scope ui_template (runs in <head>, so
     the first paint already has the right background -- no flash)
  2. every alert banner hands its severity to window.SHDBackground, which is
     the state-based trigger
  3. CSS paints body from the derived token with a transition, and the
     reduced-motion blanket rule is still there
  4. the engine writes ONLY --shd-bg-effective; it must never overwrite the
     palette's --shd-bg or a theme switch and a time-of-day state would fight

Override the flows file with SHD_FLOWS_OVERRIDE to point these at a mutation
(that is how the orphan case was reproduced).
"""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "js" / "background.js"
CSS = ROOT / "css" / "dashboard.css"
FLOWS = Path(os.environ.get("SHD_FLOWS_OVERRIDE", ROOT / "flows" / "all-flows.flow.json"))
HARNESS = ROOT / "tests" / "background_engine_harness.js"


def flows():
    return json.loads(Path(FLOWS).read_text())


def engine_src():
    return ENGINE.read_text()


def test_engine_file_defines_states_and_triggers():
    src = engine_src()
    assert src.count("rgba(") >= 4, "expected at least the 4 time-of-day tints"
    for marker in ["night", "dawn", "day", "dusk"]:
        assert f"{marker}:" in src, f"missing background state {marker}"
    assert "setInterval" in src, "no time-based trigger"
    assert "setSeverity" in src, "no state-based trigger"


def test_engine_is_inlined_into_a_global_template():
    """THE ORPHAN TEST: presence on disk is not delivery."""
    src = engine_src()
    marker = "SHDBackground"          # public API name must reach the JSON
    global_tpls = [n for n in flows()
                   if n.get("type") == "ui_template"
                   and n.get("templateScope") == "global"
                   and marker in (n.get("format") or "")]
    assert global_tpls, ("js/background.js is NOT inlined into any global-scope "
                         "ui_template -- the engine would never run (this is the "
                         "orphan defect the card was failed for)")
    body = global_tpls[0]["format"]
    assert "Dynamic Background Engine" in body, (
        "the inlined template does not contain the engine source (only a "
        "reference to its API would leave the implementation unloaded)")
    assert "SHDThemeManager" in body, ("engine should share the theme-manager "
                                       "template so --shd-bg exists before the "
                                       "derived token is computed")


def test_every_alert_banner_feeds_severity_into_the_engine():
    banners = [n for n in flows()
               if n.get("type") == "ui_template"
               and "alert-" in (n.get("format") or "")
               and "severity" in (n.get("format") or "")]
    assert banners, "no alert banners found"
    for b in banners:
        assert "SHDBackground" in b["format"], (
            f"banner {b.get('name')} does not call SHDBackground.setSeverity -- "
            "the state-based trigger is unwired for this tab")


def test_engine_never_overwrites_the_palette_token():
    src = engine_src()
    assert "setProperty('--shd-bg-effective'" in src.replace('"', "'"), \
        "engine must write the derived token"
    written = re.findall(r"setProperty\(\s*['\"](--shd-[\w-]+)['\"]", src)
    assert written == ["--shd-bg-effective"], (
        f"engine writes {written}; writing --shd-bg would fight the Theme Manager")


def test_css_paints_from_the_derived_token_and_animates():
    css = CSS.read_text()
    assert "var(--shd-bg-effective, var(--shd-bg))" in css, (
        "body must fall back to the palette colour when the engine has not run")

    # The rule that ACTUALLY wins is `body.nr-dashboard-theme` (0,1,1), generated
    # into the theme template by gen_flows.py. Checking only the plain `body`
    # rule is not enough: measured live, the engine computed rgb(13,14,28) for
    # night while the page still painted the palette rgb(26,26,46) because this
    # more specific rule was untouched.
    theme_tpls = [n for n in flows() if n.get("type") == "ui_template"
                  and n.get("templateScope") == "global"
                  and "body.nr-dashboard-theme" in (n.get("format") or "")]
    assert theme_tpls, "no global template carries the body.nr-dashboard-theme override"
    fmt = theme_tpls[0]["format"]
    m = re.search(r"body\.nr-dashboard-theme\s*\{(.*?)\}", fmt, re.S)
    assert m, "malformed theme override rule"
    assert "var(--shd-bg-effective, var(--shd-bg))" in m.group(1), (
        "the specificity-winning body.nr-dashboard-theme rule still paints "
        "--shd-bg, so the background engine's colour never reaches the page")
    body_rule = re.search(r"(?m)^body\s*\{(.*?)^\}", css, re.S)
    assert body_rule and "transition: background-color" in body_rule.group(1), \
        "body needs a background-color transition for a smooth state change"
    assert "prefers-reduced-motion: reduce" in css and "transition-duration" in css, \
        "the reduced-motion blanket rule must survive (motion is opt-out)"


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_engine_behaviour_under_node():
    """Period mapping, compositing, severity release and cadence -- real logic,
    not just presence. Runs the harness against js/background.js."""
    assert HARNESS.exists(), "behaviour harness missing"
    r = subprocess.run(["node", str(HARNESS)], capture_output=True, text=True,
                       cwd=str(ROOT), timeout=60)
    assert r.returncode == 0, f"{r.stdout}\n{r.stderr}"
    assert "behaviour OK" in r.stdout
