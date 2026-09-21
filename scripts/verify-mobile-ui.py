"""Cross-check: theme file and dashboard config agree on mobile breakpoints,
and the Galaxy A7 Lite portrait viewport (800px) falls in a covered band."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'flows'))
import dashboard_configuration as dc  # noqa: E402

dash = dc.dashboard_configuration(None)
css = (ROOT / 'css' / 'dashboard.css').read_text()

css_max = sorted(int(w) for w in re.findall(r'@media[^{]*max-width:\s*(\d+)px', css))
print("CSS max-width breakpoints:", css_max)
print("Config mobile breakpoints:", dash['mobile']['breakpoints'])
print("Touch target:", dash['mobile']['min_touch_target'], "px")
print("Layout:", dash['layout'], "| CSS:", dash['css'])

A7_PORTRAIT = 800
bands = {k: v for k, v in dash['mobile']['breakpoints'].items() if v >= A7_PORTRAIT}
assert bands, "A7 Lite portrait not covered!"
applies = [w for w in css_max if w >= A7_PORTRAIT]
assert applies, "No CSS media query covers 800px!"
print(f"A7 Lite portrait ({A7_PORTRAIT}px): covered by config band(s) {list(bands)}, CSS query at {applies}")
print("OK: mobile profile consistent and A7 Lite portrait is fully covered")