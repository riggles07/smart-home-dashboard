#!/usr/bin/env python3
"""
Verify the mobile theme is actually WIRED INTO the deployed flows.

tests/test_mobile_ui.py only checks that css/dashboard.css is well-formed on
disk. That is necessary but not sufficient: the theme can be perfectly valid and
still never reach the browser -- which is exactly what happened (the file existed,
nothing referenced it, and the dashboard rendered stock/light on the tablet).

This checks the wiring, offline, against the committed flow JSON:
  1. a ui_template node carries the theme (an inlined <style> block)
  2. it contains the theme's CSS custom properties
  3. it re-asserts body.nr-dashboard-theme (the dashboard's own rule is
     body.nr-dashboard-theme { background-color: #eee } -- specificity (0,1,1)
     beats a plain `body` rule, so without this the theme silently loses)
  4. the theme's tab is hidden (the Theme tab must not show up in the UI)
  5. the theme targets the selectors that ACTUALLY render in legacy dashboard
     3.x (md-list-item / button.md-icon-button), not only .ui_tab .tab-link,
     which matches nothing in this version

Run:  python3 tests/test_theme_wiring.py     (exit 1 = theme not wired)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "flows" / "all-flows.flow.json"
CSS = ROOT / "css" / "dashboard.css"


def fail(msg):
    print(f"  FAIL  {msg}")
    return 1


def main():
    failures = 0

    if not FLOWS.exists():
        print(f"missing {FLOWS}")
        return 1
    nodes = json.loads(FLOWS.read_text())
    by_id = {n["id"]: n for n in nodes}
    css = CSS.read_text() if CSS.exists() else ""

    # 1. a ui_template must carry the theme
    tpl = [n for n in nodes
           if n.get("type") == "ui_template"
           and "<style" in (n.get("format") or "")]
    if not tpl:
        failures += fail("no ui_template contains a <style> block -- "
                         "the theme is not injected, so it cannot reach the browser")
    else:
        print(f"  PASS  theme ui_template present: {tpl[0].get('name')!r}")
        fmt = tpl[0]["format"]

        # 2. the theme's own custom properties survived
        css_vars = set(re.findall(r"(--shd-[a-z0-9-]+)\s*:", css))
        missing = sorted(v for v in css_vars if v not in fmt)
        if css_vars and not missing:
            print(f"  PASS  all {len(css_vars)} theme CSS variables present")
        else:
            failures += fail(f"missing CSS variables in injected theme: {missing}")

        # 3. specificity override for the dashboard's own body rule
        if "body.nr-dashboard-theme" in fmt:
            print("  PASS  re-asserts body.nr-dashboard-theme "
                  "(beats the dashboard's own #eee rule)")
        else:
            failures += fail("no body.nr-dashboard-theme override -- the "
                             "dashboard's own (0,1,1) rule will win and the "
                             "page will render light grey")

        # 4. the theme's tab must be hidden
        grp = by_id.get(tpl[0].get("group"))
        tab = by_id.get(grp.get("tab")) if grp else None
        if tab and tab.get("hidden") is True:
            print(f"  PASS  theme tab {tab.get('name')!r} is hidden")
        else:
            failures += fail("the theme's ui_tab is not hidden -- it will show "
                             "up as a tab in the dashboard UI")

        # 5. target selectors that actually exist in legacy dashboard 3.x
        for sel in ("md-list-item", "md-icon-button"):
            if sel in fmt:
                print(f"  PASS  targets real rendered selector {sel!r}")
            else:
                failures += fail(f"theme does not target {sel!r} -- in legacy "
                                 f"dashboard 3.x the tab entries and toolbar "
                                 f"button are Angular Material elements, so "
                                 f".ui_tab .tab-link matches nothing")

        # 6. a stray terminator would break out of the <style> block
        if fmt.count("</style") == 1:
            print("  PASS  exactly one </style> terminator")
        else:
            failures += fail(f"{fmt.count('</style')} '</style' occurrences -- "
                             "the block terminates early and CSS spills as text")

        # 7. landscape / wide-screen layout.
        # The dashboard masonry JS writes INLINE pixel widths (measured: 318px
        # for a width-12 group => ~53.3px per unit) and inline left/top, so a
        # 2166px screen shows a ~320px column with the rest empty. Inline styles
        # outrank normal CSS, so these overrides MUST carry !important. Assert
        # both the !important and the specific properties that do the reflow.
        required = {
            ".nr-dashboard-cardcontainer": ["width: 100% !important"],
            "ui-card-panel": ["left: auto !important", "width: auto !important"],
            ".nr-dashboard-cardtitle": ["width: auto !important"],
            ".masonry-container": ["width: 100% !important"],
        }
        for sel, needles in required.items():
            if sel in fmt:
                missing = [n for n in needles if n not in fmt]
                if missing:
                    failures += fail(f"landscape rule for {sel!r} is missing "
                                     f"{missing} -- inline styles will win and "
                                     f"the tab stays a narrow column")
                else:
                    print(f"  PASS  landscape override for {sel!r} uses !important")
            else:
                failures += fail(f"no landscape override for {sel!r}")
        if "@media (min-width: 900px)" in fmt:
            print("  PASS  landscape media query present")
        else:
            failures += fail("no @media (min-width: 900px) -- wide screens get "
                             "the fixed narrow column")
        # Widget cards must be returned to normal flow, or the container has no
        # height and the panel collapses to a strip.
        for prop in ("position: static !important", "top: auto !important"):
            if prop in fmt:
                print(f"  PASS  widget cards reflowed ({prop})")
            else:
                failures += fail(f"widget cards are not reflowed ({prop} missing)"
                                 " -- they stay position:absolute with an inline "
                                 "top, so the card has zero height")
        # Guard: no rule may set width:100% on md-card. The dashboard sizes each
        # widget's height for the original ~318px column, so a 100%-width widget
        # stretches its canvas (measured 2144x221) into an unreadable shape.
        # Comments are stripped first: the rules above *describe* this bad
        # pattern in prose, and matching that prose would be a false positive.
        # The lookbehind is also load-bearing -- without it the pattern matches
        # `max-width: 100% !important`, which is legitimate.
        fmt_code = re.sub(r"/\*.*?\*/", "", fmt, flags=re.S)
        bad = re.findall(
            r"[^{}]*md-card[^{}]*\{[^}]*(?<![-\w])width:\s*100%\s*!important",
            fmt_code)
        if bad:
            failures += fail("a rule sets `width: 100% !important` on md-card -- "
                             "that stretches gauge/chart canvases. Let widgets "
                             "keep their content width and wrap instead.")
        else:
            print("  PASS  no width:100% on widget cards (canvases keep aspect)")
        # A non-auto `right` on a relatively-positioned box shifts it left by its
        # own width. Guard against re-introducing that.
        # NOTE: the negative lookbehind is load-bearing -- without it the pattern
        # also matches `margin-right: 0`, which is legitimate.
        if re.search(r"ui-card-panel[^{]*\{[^}]*(?<![-\w])right:\s*0\s*!important",
                     fmt):
            failures += fail("ui-card-panel sets `right: 0 !important` with "
                             "position: relative -- that shifts the panel left "
                             "by its own width")
        else:
            print("  PASS  no self-offsetting `right: 0` on the panel")

    print()
    if failures:
        print(f"{failures} problem(s): the theme is not correctly wired.")
    else:
        print("OK: theme is wired into the deployed flows.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
