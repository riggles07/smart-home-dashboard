import json
import subprocess
import pytest
import os

def run_validator(flow_data):
    flow_file = "temp_test_flow.json"
    with open(flow_file, "w") as f:
        json.dump(flow_data, f)
    
    result = subprocess.run(
        ["python3", "tools/validate_flows.py", flow_file],
        capture_output=True,
        text=True
    )
    
    if os.path.exists(flow_file):
        os.remove(flow_file)
        
    return result.returncode, result.stdout, result.stderr

def test_wire_validation():
    # Wire target references a node id that does not exist
    flow = [
        {"id": "node1", "type": "inject", "wires": [["missing_node"]]},
        {"id": "tab1", "type": "tab"}
    ]
    # Node1 needs a z tab to not fail earlier in validator
    flow[0]["z"] = "tab1"
    
    rc, stdout, stderr = run_validator(flow)
    assert rc != 0
    assert "wire target missing_node does not exist" in stdout

def test_tab_resolution():
    # Every node's z references a real tab node
    flow = [
        {"id": "node1", "type": "inject", "z": "missing_tab", "wires": []},
    ]
    
    rc, stdout, stderr = run_validator(flow)
    assert rc != 0
    assert "z=missing_tab is not a tab" in stdout

def test_widget_groups():
    # Every widget's group references a real ui_group
    flow = [
        {"id": "tab1", "type": "tab"},
        {"id": "node1", "type": "ui_gauge", "z": "tab1", "group": "missing_group", "wires": []},
    ]
    
    rc, stdout, stderr = run_validator(flow)
    assert rc != 0
    assert "group=missing_group is not a ui_group" in stdout

def test_ui_tab_references():
    # Every ui_group references a real ui_tab
    flow = [
        {"id": "tab1", "type": "tab"},
        {"id": "uitab1", "type": "ui_tab", "z": "tab1"},
        {"id": "group1", "type": "ui_group", "z": "tab1", "tab": "missing_uitab"},
    ]
    
    rc, stdout, stderr = run_validator(flow)
    assert rc != 0
    assert "tab=missing_uitab is not a ui_tab" in stdout
