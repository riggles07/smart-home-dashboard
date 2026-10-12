"""System Health tab (Grafana observability) wiring guards.

REQUIREMENTS_V2 §2 requires a "System Health" tab that embeds Grafana panels
for Proxmox node resources, LXC/VM health, and network latency. A tab that
exists but is not WIRED to Grafana (or whose server-side prerequisites are
undocumented) renders empty -- these checks pin the whole chain offline:

  1. the tab + its four groups exist in the generated flow JSON
  2. six Grafana embed templates exist, each an <iframe> whose src is set
     imperatively from the format's own <script> via a scope.$watch on
     msg.p.<key> -- NOT via ng-src: in Angular 1.8 an iframe src is a $sce
     RESOURCE_URL context and the uiTemplate directive compiles the format
     before any msg arrives, so ng-src's interpolation evaluates undefined
     and the attribute is stripped (live-verified: all six frames rendered
     with an empty src before this fix)
  3. the embed URLs use the /d-solo single-panel route with kiosk + dark theme
  4. the native summary path exists (inject -> query builder -> parse -> widgets)
  5. the env vars the builders read are documented in deploy/.env.example
  6. the iframe CSS classes exist in the theme (else the frames render as
     collapsed 150px strips)
  7. the Grafana-side prerequisites are documented (allow_embedding etc.)

Run:  python3 tests/test_system_health.py     (exit 1 = wiring broken)
Also imported by pytest as part of the suite.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "flows" / "all-flows.flow.json"
CSS = ROOT / "css" / "dashboard.css"
ENV_TEMPLATE = ROOT / "deploy" / ".env.example"
GRAFANA_DOC = ROOT / "docs" / "GRAFANA_INTEGRATION.md"

EMBED_PANELS = {  # msg.p key -> (template node name, Grafana panel id)
    "cpu": ("Grafana: PVE CPU", 1),
    "mem": ("Grafana: PVE Memory", 2),
    "io": ("Grafana: PVE Disk IO", 3),
    "health": ("Grafana: Service Health", 4),
    "latency": ("Grafana: ICMP Latency", 6),
    "loss": ("Grafana: Packet Loss", 7),
}


def _nodes():
    return json.loads(FLOWS.read_text())


def main():
    failures = 0

    def ok(label):
        print(f"  PASS  {label}")

    def fail(msg):
        nonlocal failures
        failures += 1
        print(f"  FAIL  {msg}")

    if not FLOWS.exists():
        print("missing flows/all-flows.flow.json (run tools/gen_flows.py)")
        return 1
    nodes = _nodes()
    by_name = {n.get("name"): n for n in nodes if n.get("name")}
    by_type = {}
    for n in nodes:
        by_type.setdefault(n["type"], []).append(n)

    # 1. the tab and its groups
    tabs = [t for t in by_type.get("ui_tab", []) if t.get("name") == "System Health"]
    if not tabs:
        fail("no ui_tab named 'System Health'")
        return 1
    tab = tabs[0]
    ok(f"System Health ui_tab present (order={tab.get('order')})")
    if tab.get("hidden"):
        fail("System Health tab is hidden -- it will never show in the UI")
    if tab.get("order") != 5:
        fail(f"System Health tab order={tab.get('order')} (expected 5, between Kanban and Settings)")

    group_names = {g.get("name") for g in by_type.get("ui_group", [])
                   if g.get("tab") == tab["id"]}
    for expected in ("Health Summary", "Proxmox Node Resources",
                     "LXC / VM Health", "Network Latency"):
        if expected in group_names:
            ok(f"group {expected!r} present")
        else:
            fail(f"missing ui_group {expected!r} on the System Health tab")

    # 2. six embed templates with script-driven src assignment
    for key, (tpl_name, panel_id) in EMBED_PANELS.items():
        tpl = by_name.get(tpl_name)
        if not tpl or tpl.get("type") != "ui_template":
            fail(f"no ui_template named {tpl_name!r}")
            continue
        fmt = tpl.get("format", "")
        if "<iframe" not in fmt:
            fail(f"{tpl_name}: no <iframe> in the template")
            continue
        if "ng-src" in fmt:
            fail(f"{tpl_name}: iframe still uses ng-src -- Angular 1.8 strips "
                 f"untrusted RESOURCE_URL bindings, so the frame renders empty "
                 f"(live-verified); src must be set from the <script>")
            continue
        if "<script>" not in fmt:
            fail(f"{tpl_name}: no <script> block to set the iframe src")
            continue
        # the script must watch msg.p.<key> on the template's live scope and
        # assign src imperatively, or the iframe never receives the URL
        if f"msg.p[key]" not in fmt or key not in fmt:
            fail(f"{tpl_name}: script does not watch msg.p.{key}")
            continue
        if f"frame.src = url" not in fmt:
            fail(f"{tpl_name}: script never assigns frame.src")
            continue
        # the reload-storm guard: re-pushing the same URL must not reload
        if "getAttribute('src') !== url" not in fmt:
            fail(f"{tpl_name}: no same-URL guard -- the 60s inject would "
                 f"reload every frame and tear down the Grafana SPA")
            continue
        # the frame lookup must use a static per-panel id (jQuery's DOMEval
        # runs the script in <head>, so DOM-relative lookups cannot work)
        if f'id="shd-frame-{key}"' not in fmt or \
                f"getElementById('shd-frame-{key}')" not in fmt:
            fail(f"{tpl_name}: iframe id/getElementById mismatch -- the "
                 f"watcher cannot find its frame")
            continue
        if 'loading="lazy"' not in fmt:
            fail(f"{tpl_name}: iframe is not loading=lazy (six eager Grafana "
                 f"SPAs will hammer the A7 Lite)")
            continue
        ok(f"embed {tpl_name!r} -> script $watch on msg.p.{key}, lazy")

    # 3. the URL builder produces d-solo kiosk URLs for the right panel ids
    builder = by_name.get("Build Grafana embeds")
    if not builder or builder.get("type") != "function":
        fail("no function node 'Build Grafana embeds'")
    else:
        code = builder.get("func", "")
        if "/d-solo/" not in code:
            fail("embed URLs do not use the /d-solo single-panel route")
        if "kiosk" not in code:
            fail("embed URLs do not pass kiosk (Grafana nav shows inside frames)")
        if "theme=dark" not in code:
            fail("embed URLs do not pin theme=dark (light flash against the dark theme)")
        if "GRAFANA_URL" not in code or "GRAFANA_DASH_UID" not in code:
            fail("builder does not read GRAFANA_URL/GRAFANA_DASH_UID from env")
        for key, (_, panel_id) in EMBED_PANELS.items():
            if re.search(rf"\b{key}:\s*solo\({panel_id}\)", code):
                ok(f"panelId {panel_id} wired to {key}")
            else:
                fail(f"msg.p.{key} not built from panelId {panel_id}")
        # every embed template must be a wire target of the builder
        wired = set()
        for out in builder.get("wires", []) or []:
            wired.update(out)
        for key, (tpl_name, _) in EMBED_PANELS.items():
            tpl = by_name.get(tpl_name)
            if tpl and tpl["id"] in wired:
                ok(f"{tpl_name} receives msgs from the builder")
            else:
                fail(f"{tpl_name} is not wired to 'Build Grafana embeds'")

    # 4. native summary path
    for needed in ("Build health query", "Parse health summary"):
        if by_name.get(needed, {}).get("type") == "function":
            ok(f"function {needed!r} present")
        else:
            fail(f"missing function {needed!r} (native summary path)")
    parse = by_name.get("Parse health summary")
    if parse:
        outs = parse.get("wires", []) or []
        if len(outs) == 5:
            ok("Parse health summary feeds 5 widgets")
        else:
            fail(f"Parse health summary has {len(outs)} outputs (expected 5)")
        if "targets_up" in parse.get("func", "") and "pve_uptime_days" in parse.get("func", ""):
            ok("parser maps stat-labelled metrics")
        else:
            fail("parser does not map the stat-labelled metrics")

    # 5. env vars documented
    tmpl = ENV_TEMPLATE.read_text() if ENV_TEMPLATE.exists() else ""
    for var in ("PROMETHEUS_URL", "GRAFANA_URL", "GRAFANA_DASH_UID"):
        if re.search(rf"^\s*{var}=", tmpl, re.M):
            ok(f"{var} documented in deploy/.env.example")
        else:
            fail(f"{var} missing from deploy/.env.example (env-drift guard will fail)")

    # 6. iframe CSS
    css = CSS.read_text() if CSS.exists() else ""
    for cls in (".shd-embed", ".shd-grafana-frame"):
        if cls in css:
            ok(f"{cls} styled in css/dashboard.css")
        else:
            fail(f"{cls} missing from the theme -- frames render collapsed")
    if "overscroll-behavior: contain" not in css:
        fail("iframe overscroll not contained (page jitters when scrolling inside a frame)")

    # 7. Grafana-side prerequisites documented
    doc = GRAFANA_DOC.read_text() if GRAFANA_DOC.exists() else ""
    for needle in ("allow_embedding", "GF_SECURITY_ALLOW_EMBEDDING",
                   "anonymous", "d-solo"):
        if needle in doc:
            ok(f"Grafana config {needle!r} documented")
        else:
            fail(f"{needle!r} not documented in docs/GRAFANA_INTEGRATION.md")

    print(f"\n{'OK' if not failures else str(failures) + ' FAILURES'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())