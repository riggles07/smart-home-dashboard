# Verification Report: H3 Regression (Structural Breakages)
Task ID: t_b7398856
Date: 2026-10-04

## 1. Test Setup
- Good Flow: /root/.hermes/projects/smart-home-dashboard/flows/all-flows.flow.json
- Mutated Flow: /root/.hermes/projects/smart-home-dashboard/flows/all-flows.broken.json

Mutations applied to broken flow:
- All `wires` rewritten to `[['unknown_node_9999']]`.
- All `ui_group.tab` set to `unknown_tab_9999`.
- Theme template deleted.
- Theme tab `hidden` set to `false`.

## 2. Test Harness Execution (tools/test_flow_functions.js)

### A. Mutated Flow
Command: `node tools/test_flow_functions.js flows/all-flows.broken.json`
Exit Code: 1
Result: FAIL
Measured Value: "=== STRUCTURAL VALIDATION FAILED === Flow file is structurally invalid. Cannot proceed with function tests."
Observation: The harness correctly blocked function tests and identified the structural issues (unknown nodes and invalid tabs).

### B. Good Flow
Command: `node tools/test_flow_functions.js flows/all-flows.flow.json`
Exit Code: 0
Result: PASS
Measured Value: "80 passed, 0 failed"

## 3. Cross-Check (tools/validate_flows.py)

### A. Mutated Flow
Command: `python3 tools/validate_flows.py flows/all-flows.broken.json`
Exit Code: 1
Result: FAIL
Observation: Correctly identified dangling wires and invalid tabs.

### B. Good Flow
Command: `python3 tools/validate_flows.py flows/all-flows.flow.json`
Exit Code: 0
Result: PASS

## 4. Regression Analysis
Previous behavior (reported in H3): Harness reported 66/66 green despite structural breakages.
Current behavior: Harness exits with code 1, reports structural failure, and refuses to run function tests on broken flows.
Verdict: 66/66 green-on-broken behavior is ELIMINATED.

## 5. Steps I could not complete
None. All requested gates were measured.

## 6. Falsification Attempt
Attempted to bypass the structural check by only breaking the `ui_group.tab` references while keeping wires intact.
Result: The harness still failed with "ui_group(...) tab=... not a ui_tab", confirming that structural validation is not solely dependent on wires.
