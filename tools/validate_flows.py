#!/usr/bin/env python3
"""Validate generated Node-RED flow JSON before import."""
import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else \
    "/root/.hermes/projects/smart-home-dashboard/flows/all-flows.flow.json"

nodes = json.load(open(path))
ids = {n["id"] for n in nodes}
types = {n["id"]: n["type"] for n in nodes}
errors, warnings = [], []

# 1. duplicate ids
seen = set()
for n in nodes:
    if n["id"] in seen:
        errors.append(f"duplicate id {n['id']}")
    seen.add(n["id"])

# 2. dangling wire targets
for n in nodes:
    for out_idx, out in enumerate(n.get("wires", []) or []):
        for target in out:
            if target not in ids:
                errors.append(f"{n['type']}({n.get('name','')}) output {out_idx} -> unknown {target}")

# 3. every non-tab node has a valid z (tab)
tabs = {n["id"] for n in nodes if n["type"] == "tab"}
for n in nodes:
    if n["type"] == "tab":
        continue
    z = n.get("z")
    if z is None:
        errors.append(f"{n['type']}({n.get('name','')}) has no z tab")
    elif z not in tabs:
        errors.append(f"{n['type']}({n.get('name','')}) z={z} is not a tab")

# 4. ui_group.tab must reference a ui_tab
uitabs = {n["id"] for n in nodes if n["type"] == "ui_tab"}
for n in nodes:
    if n["type"] == "ui_group":
        if n.get("tab") not in uitabs:
            errors.append(f"ui_group({n.get('name','')}) tab={n.get('tab')} not a ui_tab")

# 5. dashboard widgets must reference a ui_group
groups = {n["id"] for n in nodes if n["type"] == "ui_group"}
WIDGETS = {"ui_gauge","ui_text","ui_chart","ui_switch","ui_slider","ui_template",
           "ui_button","ui_text_input","ui_dropdown","ui_numeric","ui_ui_control"}
for n in nodes:
    if n["type"] in WIDGETS:
        if n.get("group") not in groups:
            errors.append(f"{n['type']}({n.get('name','')}) group={n.get('group')} not a ui_group")

# 6. http request nodes use method 'use' (set by preceding function)
for n in nodes:
    if n["type"] == "http request" and n.get("method") != "use":
        warnings.append(f"http request({n.get('name','')}) method={n.get('method')} (expected 'use')")

# 7. function nodes have func body
for n in nodes:
    if n["type"] == "function" and not n.get("func"):
        errors.append(f"function({n.get('name','')}) has empty func")

print(f"nodes: {len(nodes)}  tabs: {len(tabs)}  ui_tabs: {len(uitabs)}  groups: {len(groups)}")
print("node types:", ", ".join(sorted({n['type'] for n in nodes})))
if warnings:
    print("\nWARNINGS:")
    for w in warnings: print("  ~", w)
if errors:
    print("\nERRORS:")
    for e in errors: print("  X", e)
    sys.exit(1)
print("\nOK: structure valid (no dangling wires, all refs resolve)")
