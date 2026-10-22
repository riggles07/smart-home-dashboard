#!/usr/bin/env python3
"""Point the existing /floor-plan dashboard at the cartoon card (or restore it).

The old view is backed up to floorplan/backups/floor-plan-<timestamp>.json before any
change, and `--restore` puts it back verbatim. The kiosk is the one surface that must not
be left broken, so the switch is reversible with one command.

    python3 tools/switch_floorplan_to_cartoon.py            # switch
    python3 tools/switch_floorplan_to_cartoon.py --restore  # put the old card back
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = Path("/root/.hermes/.env")
BACKUPS = ROOT / "floorplan" / "backups"
URL_PATH = "floor-plan"
CARTOON = "custom:floorplan-cartoon-card"
LEGACY = "custom:floorplan-card"


def _env() -> tuple[str, str]:
    vals = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip()
    return (os.environ.get("HA_URL") or vals["HA_URL"]).rstrip("/"), \
           (os.environ.get("HA_TOKEN") or vals["HA_TOKEN"])


async def run(restore: bool) -> dict:
    import websockets

    base, tok = _env()
    async with websockets.connect(base.replace("http", "ws") + "/api/websocket",
                                  max_size=16 * 1024 * 1024) as ws:
        await ws.recv()
        await ws.send(json.dumps({"type": "auth", "access_token": tok}))
        if json.loads(await ws.recv())["type"] != "auth_ok":
            raise SystemExit("auth failed")
        n = 0

        async def cmd(payload: dict) -> dict:
            nonlocal n
            n += 1
            payload["id"] = n
            await ws.send(json.dumps(payload))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == n and m.get("type") == "result":
                    return m

        cfg = await cmd({"type": "lovelace/config", "url_path": URL_PATH})
        if not cfg.get("success"):
            raise SystemExit(f"cannot read {URL_PATH}: {cfg}")
        config = cfg["result"]

        BACKUPS.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = BACKUPS / f"floor-plan-{stamp}.json"
        backup.write_text(json.dumps(config, indent=2))

        if restore:
            files = sorted(BACKUPS.glob("floor-plan-*.json"))
            # restoring means: drop the newest backup that is NOT this run's snapshot
            older = [f for f in files if f != backup]
            if not older:
                raise SystemExit("no earlier backup to restore from")
            config = json.loads(older[-1].read_text())
            target = older[-1].name
        else:
            changed = 0
            for view in config.get("views", []):
                for card in view.get("cards", []):
                    if card.get("type") == LEGACY:
                        card["type"] = CARTOON
                        card.pop("config", None)
                        card.pop("image", None)
                        changed += 1
            if not changed:
                raise SystemExit(f"no {LEGACY} card found to replace")
            target = CARTOON

        save = await cmd({"type": "lovelace/config/save", "url_path": URL_PATH,
                          "config": config})
        if not save.get("success"):
            raise SystemExit(f"save failed: {save}")

        check = await cmd({"type": "lovelace/config", "url_path": URL_PATH})
        types = [c.get("type") for v in check["result"].get("views", [])
                 for c in v.get("cards", [])]
        return {"action": "restore" if restore else "switch", "to": target,
                "backup": str(backup), "cards_now": types}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()
    print(json.dumps(asyncio.run(run(a.restore)), indent=2))
