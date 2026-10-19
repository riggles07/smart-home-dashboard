#!/usr/bin/env python3
"""CSS/literal-newline sanity guard.

WHY: on 2026-10-19 the dynamic-background worker patched dashboard.css and
wrote 19 LITERAL backslash-n sequences into it (a Python/JSON escaping slip:
"\\n" landed in the file instead of a real newline). Everything from the first
occurrence onwards -- @media (prefers-reduced-motion), @media print and the new
background transitions -- became invalid CSS and silently stopped applying.

The entire pytest suite still passed (446 green), so the bug was invisible to
verification. That is the same failure shape as the alert CSS that no widget
used and the orphaned js/background.js: plausible-looking output, nothing
actually working.

This guard checks the artefact, not the intent:
  1. no literal two-character backslash-n in any css/*.css
  2. curly braces balanced per file
  3. every ui_template `format` in the generated flows is free of the same slip

Run: python3 tests/test_css_sanity.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LITERAL_NL = "\\n"          # backslash + n as two characters
CSS_DIR = ROOT / "css"
FLOWS = ROOT / "flows" / "all-flows.flow.json"


def check_css(path):
    errors = []
    text = path.read_text()
    hits = text.count(LITERAL_NL)
    if hits:
        # locate the first one so the report is actionable
        idx = text.find(LITERAL_NL)
        line_no = text[:idx].count("\n") + 1
        snippet = text[max(0, idx - 60):idx + 40].replace("\n", "|")
        errors.append(f"{path.name}: {hits} literal '\\n' sequence(s); first at "
                      f"line {line_no}: ...{snippet}...")
    if text.count("{") != text.count("}"):
        errors.append(f"{path.name}: unbalanced braces "
                      f"({text.count('{')} open vs {text.count('}')} close)")
    return errors


def check_flows():
    """ui_template bodies are HTML+JS; a literal \\n usually means a broken
    escape upstream (gen_flows.py or a hand-edit of the generated JSON)."""
    errors = []
    if not FLOWS.exists():
        return errors
    nodes = json.loads(FLOWS.read_text())
    for n in nodes:
        fmt = n.get("format")
        if n.get("type") == "ui_template" and isinstance(fmt, str):
            if LITERAL_NL in fmt and "</script>" in fmt:
                # scripts legitimately contain "\n" inside JS string literals
                # only if double-escaped; flag only the suspicious shape where
                # it appears at a line boundary with code after it
                bad = [ln for ln in fmt.split("\n")
                       if LITERAL_NL in ln and ln.strip().startswith(LITERAL_NL)]
                if bad:
                    errors.append(f"ui_template {n.get('name')!r}: {len(bad)} line(s) "
                                  f"start with a literal '\\n'")
    return errors


def main(argv):
    errors = []
    # argv[1] lets a caller point the guard at any copy (a worker worktree, a
    # /tmp mutation). Without it the guard always read ROOT/css, which made an
    # earlier "it passed" result meaningless -- it had inspected the wrong file.
    if len(argv) > 1:
        target = Path(argv[1])
        paths = sorted(target.glob("*.css")) if target.is_dir() else [target]
    else:
        paths = sorted(CSS_DIR.glob("*.css"))
    for path in paths:
        errors += check_css(path)
    errors += check_flows()
    if errors:
        for e in errors:
            print("FAIL:", e)
        return 1
    print(f"OK: {len(paths)} css file(s) free of literal newline artefacts, "
          f"braces balanced")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
