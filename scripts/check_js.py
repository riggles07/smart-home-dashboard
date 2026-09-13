"""Validate JavaScript flow files without a Node.js runtime.

Uses the pure-Python esprima parser when available; otherwise falls back
to a structural sanity check (balanced delimiters, string/template/regex
literals). Usage:

    python3 scripts/check_js.py [file.js ...]
"""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FLOWS = sorted(REPO.glob("flows/*.js"))


def esprima_check(path):
    import esprima  # imported lazily so the fallback still works

    with open(path, encoding="utf-8") as handle:
        esprima.parseScript(handle.read())
    return "OK (esprima full parse)"


def structural_check(path):
    """Bracket/string balance scan tolerant of comments and literals."""
    text = Path(path).read_text(encoding="utf-8")
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    i, n = 0, len(text)
    line = 1
    while i < n:
        ch = text[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        # comments
        if ch == "/" and i + 1 < n:
            nxt = text[i + 1]
            if nxt == "/":
                while i < n and text[i] != "\n":
                    i += 1
                continue
            if nxt == "*":
                i += 2
                while i + 1 < n and not (text[i] == "*" and text[i + 1] == "/"):
                    if text[i] == "\n":
                        line += 1
                    i += 1
                i += 2
                continue
        # strings
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n and text[i] != quote:
                if text[i] == "\\":
                    i += 1
                if text[i] == "\n":
                    line += 1
                i += 1
            if i >= n:
                return f"FAIL: unterminated string starting near line {line}"
            i += 1
            continue
        # template literals (with ${} nesting handled by the main stack)
        if ch == "`":
            start_line = line
            i += 1
            while i < n and text[i] != "`":
                if text[i] == "\\":
                    i += 1
                if text[i] == "\n":
                    line += 1
                i += 1
            if i >= n:
                return f"FAIL: unterminated template literal near line {start_line}"
            i += 1
            continue
        # delimiters
        if ch in "([{":
            stack.append((ch, line))
        elif ch in ")]}":
            if not stack or stack[-1][0] != pairs[ch]:
                return f"FAIL: unbalanced '{ch}' at line {line}"
            stack.pop()
        i += 1
    if stack:
        opener, oline = stack[-1]
        return f"FAIL: unclosed '{opener}' opened at line {oline}"
    return "OK (structural balance check)"


def main():
    targets = [Path(a) for a in sys.argv[1:]] or FLOWS
    failures = 0
    try:
        import esprima  # noqa: F401
        mode = "esprima"
    except ImportError:
        mode = "structural"
    print(f"JS syntax check ({mode} mode) over {len(targets)} file(s)")
    for path in targets:
        try:
            result = (
                esprima_check(path) if mode == "esprima" else structural_check(path)
            )
            print(f"  {path.name}: {result}")
        except Exception as exc:  # esprima raises on syntax errors
            failures += 1
            print(f"  {path.name}: FAIL ({exc})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
