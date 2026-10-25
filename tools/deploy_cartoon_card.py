#!/usr/bin/env python3
"""Wire the cartoon card into Home Assistant -- after the two files are uploaded.

Order of operations, and why:

  1. VERIFY THE FILES ARE ACTUALLY SERVED. Registering a Lovelace resource for a file
     that is not on disk gives a silent 404 in the browser and an empty card; a green
     config write proves nothing (this project has already shipped a rule bound to a
     non-existent entity). So step one is an HTTP GET of both files from HA itself.
  2. Register/refresh the resource (type=module) -- idempotent.
  3. Create a SEPARATE dashboard 'cartoon' rather than editing /floor-plan. The existing
     plan stays working on the kiosk while the new one is reviewed; switching is then a
     one-line decision, not a deploy.

Usage:
    python3 tools/deploy_cartoon_card.py --check-only     # just report what is missing
    python3 tools/deploy_cartoon_card.py                  # register resource + dashboard
Exit codes: 0 done, 1 files missing, 2 HA unreachable.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
ENV = Path("/root/.hermes/.env")

ART = "/local/floorplan/cartoon/floorplan_render.jpg"
_CARD_BASE = "/local/floorplan/cartoon/floorplan-cartoon-card.js"
# Append the payload version: /local files are served with max-age=31 days, so a card
# registered without a query string can be served from a stale cache. Every HACS resource
# on this install does the same (?hacstag=...).
try:
    _ver = re.search(r'"version":"([0-9a-f]{8})"',
                     (ROOT / "floorplan" / "cartoon" / "dist" / "floorplan-cartoon-card.js").read_text())
    CARD = f"{_CARD_BASE}?v={_ver.group(1)}" if _ver else _CARD_BASE
except FileNotFoundError:
    CARD = _CARD_BASE
URL_PATH = "cartoon-plan"   # HA requires a hyphen in url_path
TITLE = "Cartoon Plan"


def _env() -> tuple[str, str]:
    vals = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return (os.environ.get("HA_URL") or vals["HA_URL"]).rstrip("/"), \
           (os.environ.get("HA_TOKEN") or vals["HA_TOKEN"])


def check_files(base: str) -> list[str]:
    missing = []
    for path in (ART, CARD):
        try:
            r = requests.get(base + path, timeout=25)
            ok = r.status_code == 200 and len(r.content) > 1000
            print(f"  {'OK  ' if ok else 'MISS'} {path}  "
                  f"({r.status_code}, {len(r.content)/1024:.0f} kB)")
            if not ok:
                missing.append(path)
        except Exception as e:                      # noqa: BLE001
            print(f"  ERR  {path}: {e}")
            missing.append(path)
    return missing


VIEW = {
    "title": "Cartoon",
    "path": "cartoon-plan",
    "icon": "mdi:home-floor-a",
    "cards": [
        {
            "type": "custom:floorplan-cartoon-card",
            "image": "/local/floorplan/cartoon/floorplan_render.jpg",
        }
    ],
}


async def wire(base: str, token: str) -> dict:
    import websockets

    ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + "/api/websocket"
    result = {"resource": None, "dashboard": None}
    async with websockets.connect(ws_url, max_size=8 * 1024 * 1024) as ws:
        hello = json.loads(await ws.recv())
        assert hello["type"] == "auth_required", hello
        await ws.send(json.dumps({"type": "auth", "access_token": token}))
        auth = json.loads(await ws.recv())
        if auth["type"] != "auth_ok":
            raise SystemExit(f"auth failed: {auth}")
        n = 0

        async def cmd(payload: dict) -> dict:
            nonlocal n
            n += 1
            payload["id"] = n
            await ws.send(json.dumps(payload))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == n and msg.get("type") == "result":
                    return msg

        # --- resource -------------------------------------------------------
        res = await cmd({"type": "lovelace/resources/list"})
        base_path = CARD.split("?")[0]
        same_file = [r for r in res["result"] if r.get("url", "").split("?")[0] == base_path]
        if same_file:
            # keep one, update it in place, delete any duplicates left by earlier runs
            # (a duplicate module re-runs customElements.define and throws)
            keep = same_file[0]
            r = await cmd({"type": "lovelace/resources/update", "resource_id": keep["id"],
                           "res_type": "module", "url": CARD})
            result["resource"] = "updated" if r.get("success") else f"error {r}"
            for dup in same_file[1:]:
                d = await cmd({"type": "lovelace/resources/delete", "resource_id": dup["id"]})
                result.setdefault("deleted_duplicates", []).append(
                    {"url": dup["url"], "ok": bool(d.get("success"))})
        else:
            r = await cmd({"type": "lovelace/resources/create",
                           "res_type": "module", "url": CARD})
            result["resource"] = "created" if r.get("success") else f"error {r}"

        # --- dashboard ------------------------------------------------------
        dash = await cmd({"type": "lovelace/dashboards/list"})
        have = next((d for d in dash["result"] if d.get("url_path") == URL_PATH), None)
        if not have:
            r = await cmd({"type": "lovelace/dashboards/create",
                           "url_path": URL_PATH, "title": TITLE, "icon": "mdi:home-floor-a",
                           "show_in_sidebar": True, "require_admin": False})
            if not r.get("success"):
                result["dashboard"] = f"error {r}"
                return result
            have = {"id": r["result"]["id"]}
            result["dashboard"] = "created"
        else:
            result["dashboard"] = "exists"

        # Never overwrite an existing dashboard's config. It carries state this script
        # does not own -- kiosk_mode, panel:true, icon -- and re-seeding it from VIEW
        # silently reverted kiosk mode and the panel layout on every single deploy.
        if result["dashboard"] == "created":
            save = await cmd({"type": "lovelace/config/save", "url_path": URL_PATH,
                              "config": {"title": "Cartoon", "views": [VIEW]}})
            if not save.get("success"):
                result["dashboard"] += f" (config seed failed: {save})"
        else:
            existing = await cmd({"type": "lovelace/config", "url_path": URL_PATH})
            cfg = existing.get("result") or {}
            views = cfg.get("views") or []
            has_card = any(cd.get("type") == "custom:floorplan-cartoon-card"
                           for v in views for cd in (v.get("cards") or []))
            keep = sorted(k for k in cfg if k not in ("title", "views"))
            result["dashboard"] += " (config preserved"
            result["dashboard"] += f"; kept {keep}" if keep else ""
            result["dashboard"] += ")" if has_card else \
                "; WARNING card not found in the existing config)"
        return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check-only", action="store_true")
    a = ap.parse_args()
    base, token = _env()

    print(f"checking {base} for the two card files:")
    missing = check_files(base)
    if missing:
        print("\nBLOCKED: upload these to /config/www/floorplan/cartoon/ first:")
        for m in missing:
            print("   ", m.replace("/local/", "/config/www/"))
        print("   bundle: floorplan/cartoon/dist/cartoon_deploy.zip")
        return 1
    if a.check_only:
        print("files present; run without --check-only to wire the dashboard")
        return 0

    print("\nwiring Lovelace resource + dashboard …")
    out = asyncio.run(wire(base, token))
    print(json.dumps(out, indent=2))
    print(f"\nopen {base}/lovelace/{URL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
