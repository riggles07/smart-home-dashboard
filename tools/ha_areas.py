#!/usr/bin/env python3
"""Print HA areas with their controllable entities and temperature sensors.

Uses the template API: areas()/area_entities() are server-side, so this is the
authoritative area->entity mapping and not a guess from entity_id prefixes.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

ENV = Path(os.environ.get("HERMES_ENV", "/root/.hermes/.env"))
DOMAINS = ("light", "switch", "fan", "climate", "cover", "lock", "media_player",
           "humidifier", "water_heater", "vacuum")

TPL = """
{%- for a in areas() -%}
{{ a }}|{{ area_name(a) }}|{{ area_entities(a)
   | select('match', '^(' ~ domains ~ ')\\.') | list | join(',') }}|{{ area_entities(a)
   | select('match', '^sensor\\.') | select('search', 'temperature')
   | list | join(',') }}
{% endfor -%}
"""


def env(key: str) -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit(f"{key} not in {ENV}")


def main() -> int:
    url, tok = env("HA_URL").rstrip("/"), env("HA_TOKEN")
    body = json.dumps({"template": TPL.replace("(' ~ domains ~ ')", "|".join(DOMAINS))}).encode()
    req = urllib.request.Request(f"{url}/api/template", data=body, method="POST",
                                 headers={"Authorization": f"Bearer {tok}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode()
    if "--json" in sys.argv:
        print(text.strip())
        return 0
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("|")
        if len(parts) < 4:
            continue
        aid, name, ents, temps = parts[0], parts[1], parts[2], parts[3]
        if not ents and not temps:
            continue
        print(f"\n## {name}  ({aid})")
        for e in [x for x in ents.split(",") if x]:
            print(f"   {e}")
        for t in [x for x in temps.split(",") if x]:
            print(f"   ~ {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
