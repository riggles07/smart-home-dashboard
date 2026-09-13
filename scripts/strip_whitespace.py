"""One-shot cleanup: strip trailing whitespace from recovered Python files.

Mechanical, whitespace-only transform (W291/W293 fixes); does not touch
code logic. Verifies each file still compiles after the rewrite.
"""

import py_compile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

targets = sorted(REPO.glob("app/*.py")) + sorted(REPO.glob("tests/*.py"))
for path in targets:
    text = path.read_text(encoding="utf-8")
    cleaned = "\n".join(line.rstrip() for line in text.split("\n"))
    if cleaned and not cleaned.endswith("\n"):
        cleaned += "\n"
    if cleaned != text:
        path.write_text(cleaned, encoding="utf-8")
        print(f"cleaned: {path.relative_to(REPO)}")
    py_compile.compile(str(path), doraise=True)

print(f"verified: {len(targets)} files compile")
