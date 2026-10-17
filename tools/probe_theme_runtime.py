#!/usr/bin/env python3
"""Inspect the LIVE Node-RED at sh-dashboard:1880 (read-only Admin API).

Answers one question the docs cannot: does a templateScope:'global'
ui_template node receive INPUT messages on the dashboard socket, or is
it a pure one-way style/behaviour injection? The Theme Manager design
depends on it (programmatic msg-driven theme switching).

Usage: python3 tools/probe_theme_runtime.py [host]
Dumps /flows, finds the Theme tab nodes, prints their scope + wires,
and prints the dashboard version info. NEVER modifies anything.
"""
import json
import sys
import urllib.request

HOST = sys.argv[1] if len(sys.argv) > 1 else "sh-dashboard"


def get(path):
    url = f"http://{HOST}:1880{path}"
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read().decode("utf-8", "replace")


def main():
    flows = json.loads(get("/flows"))
    print(f"live flow nodes: {len(flows)}")
    for n in flows:
        t = n.get("type", "")
        if t in ("ui_template", "ui_button", "ui_ui_control", "ui_toast"):
            print(f"  {t:14} name={n.get('name','')!r} "
                  f"scope={n.get('templateScope','-')} "
                  f"group={n.get('group','-')} wires={n.get('wires','-')} "
                  f"fwdIn={n.get('fwdInMessages','-')} "
                  f"storeOut={n.get('storeOutMessages','-')} "
                  f"resend={n.get('resendOnRefresh','-')}")
    # installed dashboard version, from the /packages admin endpoint if present
    try:
        pkgs = json.loads(get("/packages"))
        for kind in ("nodes", "modules"):
            items = pkgs.get(kind, {}) or {}
            if isinstance(items, dict):
                for name in items:
                    if "dashboard" in name or "ui" == name:
                        print(f"  installed: {name} -> {items[name].get('version')}")
            elif isinstance(items, list):
                for it in items:
                    nm = it.get("name", "")
                    if "dashboard" in nm:
                        print(f"  installed: {nm} -> {it.get('version')}")
    except Exception as exc:  # endpoint optional; probe is best-effort
        print(f"  (packages endpoint unavailable: {exc})")


if __name__ == "__main__":
    main()