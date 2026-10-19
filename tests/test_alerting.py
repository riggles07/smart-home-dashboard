#!/usr/bin/env python3
"""Guard the alert layer: severity ladder applied to REAL widgets + error visibility.

The alert CSS once shipped while no widget used it, and the suite stayed green.
This asserts the wiring offline (against flows/all-flows.flow.json):
  1. every tab with an Alerts group has one banner that applies the ladder
  2. no Alerts group is collapsible (a critical banner must never be hideable)
  3. every evaluator is reachable from a catch node and handles msg.error,
     so a failed integration shows CRITICAL instead of silently keeping its
     template default ("Awaiting first result")
  4. every alert colour pair clears WCAG AA 4.5:1

Run: python3 tests/test_alerting.py [flows.json]
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "flows" / "all-flows.flow.json"
CSS = ROOT / "css" / "dashboard.css"
SEVERITIES = ["critical", "warning", "info", "ok"]
CLASSES = ["alert-ok", "alert-info", "alert-warning", "alert-critical"]


def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def check(nodes):
    errors = []
    tabs = {n["id"]: n.get("label", "") for n in nodes if n.get("type") == "tab"}
    groups = [n for n in nodes if n.get("type") == "ui_group" and n.get("name") == "Alerts"]
    banners = [n for n in nodes if n.get("type") == "ui_template"
               and "alert-" in (n.get("format") or "")
               and "severity" in (n.get("format") or "")]
    evals = {n["id"]: n for n in nodes
             if n.get("type") == "function" and n.get("name") == "Evaluate alerts"}
    catches = [n for n in nodes if n.get("type") == "catch"]

    if len(groups) < 4:
        errors.append(f"expected an Alerts group on >=4 tabs, found {len(groups)}")

    for g in groups:
        if g.get("collapse") is not False:
            errors.append(f"Alerts group {g['id']} is collapsible -- a critical "
                          f"banner must never be hideable")
        if g.get("order") != 1:
            errors.append(f"Alerts group {g['id']} order={g.get('order')}, expected 1")
        owned = [b for b in banners if b.get("group") == g["id"]]
        if len(owned) != 1:
            errors.append(f"Alerts group {g['id']} has {len(owned)} banners, expected 1")
        for b in owned:
            if b.get("resendOnRefresh") is not True:
                errors.append(f"banner {b['id']} must resendOnRefresh")

    for b in banners:
        for sev in SEVERITIES:
            if f"alert-{sev}" not in (b.get("format") or ""):
                errors.append(f"banner {b['id']} never applies alert-{sev}")

    if len(evals) < 4:
        errors.append(f"expected >=4 alert evaluators, found {len(evals)}")
    caught = set()
    for c in catches:
        if c.get("scope") is not None:
            errors.append(f"catch node {c['id']} scope must be null (cover whole tab)")
        for group in c.get("wires") or []:
            for t in group or []:
                caught.add(t)
                if t not in evals:
                    errors.append(f"catch {c['id']} wires to {t}, not an evaluator")
    for eid, e in evals.items():
        if eid not in caught:
            errors.append(f"evaluator {eid} on tab {tabs.get(e.get('z'))!r} has NO catch "
                          f"node -- an http failure would never reach the banner")
        body = e.get("func") or ""
        if "msg.error" not in body:
            errors.append(f"evaluator {eid} ignores msg.error")
        if "'critical'" not in body:
            errors.append(f"evaluator {eid} never emits critical")

    css = strip_comments(CSS.read_text())
    tokens = dict(re.findall(r"--(shd-[\w-]+):\s*([^;]+);", css))
    for cls in CLASSES:
        rule = re.search(rf"\.{cls}\s*\{{(.*?)\}}", css, re.S)
        if not rule:
            errors.append(f"no .{cls} rule")
            continue
        if "var(--shd-" not in rule.group(1):
            errors.append(f".{cls} does not use --shd-* tokens")

    def lum(h):
        h = h.strip().lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        rgb = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        rgb = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in rgb]
        return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

    def resolve(name, depth=0):
        val = tokens.get(name, "").strip()
        m = re.match(r"var\(--([\w-]+)\)", val)
        return resolve(m.group(1), depth + 1) if m and depth < 5 else val

    for cls in CLASSES:
        rule = re.search(rf"\.{cls}\s*\{{(.*?)\}}", css, re.S)
        if not rule:
            continue
        bg = re.search(r"background:\s*var\(--([\w-]+)\)", rule.group(1))
        fg = re.search(r"color:\s*var\(--([\w-]+)\)", rule.group(1))
        if not (bg and fg):
            errors.append(f".{cls} missing background/color token")
            continue
        a, b = lum(resolve(bg.group(1))), lum(resolve(fg.group(1)))
        ratio = (max(a, b) + 0.05) / (min(a, b) + 0.05)
        if ratio < 4.5:
            errors.append(f".{cls} contrast {ratio:.2f}:1 below WCAG AA 4.5:1")
    return errors


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else FLOWS
    errors = check(json.loads(path.read_text()))
    for e in errors:
        print("FAIL:", e)
    if errors:
        return 1
    print("OK: alert groups/banners/catch wiring + AA contrast all verified")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
