# Flow Function Coverage Report

Audit card: **t_02d0381d** (researcher worker, run #25, 2026-10-17).
Corrected by the parent session before landing — see "Parent corrections" below.

## Inventory

Total function nodes in `flows/all-flows.flow.json`: **16**
Command used: `python3 -c "import json; print(len([n for n in json.load(open('flows/all-flows.flow.json')) if n.get('type')=='function']))"`

## Coverage matrix

Both harnesses extract the `func` source **straight out of the flow JSON** and run
it against stubbed globals, so they exercise the deployed logic rather than a copy.
Every criterion below was read from the harness, not inferred.

| ID | Name | Covered | Harness | Numeric criterion |
|---|---|---|---|---|
| dcb973a98c5d7505 | Build Proxmox request | Yes | flow-functions | PASS `builds node status url` |
| bcd20c7f62b43cd7 | Split metrics | Yes | flow-functions | PASS `cpu -> 7.3%` |
| 79096e91e2e6c3a8 | Build device list call | Yes | flow-functions | PASS `list URL uses /devices` |
| 27a11686ba678c7a | Format device list | Yes | flow-functions | PASS `count emitted on out1` |
| 8ddcf421c3694424 | Build Maker API call | Yes | flow-functions | PASS `power on -> /devices/7/on` |
| 3955c5258b61b1cc | Format result | Yes | flow-functions | PASS `2xx -> OK` |
| f21d1eb7bd642318 | HA WebSocket Client | Yes | **ha-functions** | handshake `auth_required` -> `auth_ok` -> `auth_invalid`; emits `ha/entity/<id>/state` |
| 1ff5870c922f75a4 | HA REST Controller | Yes | **ha-functions** | builds `light.turn_on` / `light.turn_off` for the configured entity; attaches the bearer header from `HA_TOKEN` |
| 5c8c0661415fa783 | Build UniFi auth | Yes | flow-functions | PASS `routes to out1 (no login needed)` |
| 9f4a7680b3bdb142 | Capture session | Yes | flow-functions | PASS `extracts cookie value` |
| 62f102051af2d959 | Split client data | Yes | flow-functions | PASS `count output = 3` |
| 5c6df7c479179e47 | Add card | Yes | flow-functions | PASS `two cards persisted in flow context` |
| bd1a48dec02a2883 | Render board | Yes | flow-functions + `tests/test_render_board.py` | PASS `returns array of 2 messages` (plus 20 dedicated tests) |
| 025dac0d1c93aa91 | Build health query | Yes | flow-functions | PASS `targets the instant-query API` |
| 3a60013f3e07f4a7 | Parse health summary | Yes | flow-functions | PASS `five outputs` |
| 0920bfc12f1795af | Build Grafana embeds | Yes | flow-functions | PASS `cpu embed hits d-solo route` |

## Untested nodes

**None.** All 16 function nodes are exercised. Two gaps worth naming:

- The HA nodes are covered only by `tools/test_ha_functions.js`, so running the
  flow-functions harness alone makes them look untested. **CI runs both**
  (`.github/workflows/ci.yml`: "Test flow function logic" and "Test Home Assistant
  flow functions"), so the gap exists only for a reader who runs one harness.
- `tools/test_flow_functions.js` contains an **inlined copy** of the Render board
  body rather than reading it from the flow JSON, so it cannot catch the generated
  node drifting. `tests/test_render_board.py` (added under t_d0565899) closes that
  by asserting against the generated file.

## Measurement evidence

```
$ node tools/test_flow_functions.js     -> 108 passed, 0 failed
$ node tools/test_ha_functions.js       ->  41 passed, 0 failed
$ python3 -m pytest tests/ -q           -> 398 passed, 6 skipped, 0 failed
```

## Acceptance criteria for any future function node

1. A numeric assertion in one of the two JS harnesses, named in the harness output.
2. The harness must read the body **from the flow JSON**, not a copy — otherwise the
   generated node can drift while the test stays green.
3. Real newlines in the body with **zero** literal `\n`: a body that is one line
   starting with `//` is dead code and no structural check notices
   (`tests/test_flow_newline_guard.py` guards this).
4. If the node is wired to a dashboard tab, a structural assertion that it exists
   with its expected outputs and wire targets (see `tests/test_render_board.py`).

## Parent corrections

Applied before landing, both verified by re-running the check:

1. **"Untested: 2" was wrong.** The draft ran only `tools/test_flow_functions.js`
   and concluded the two HA nodes had no coverage. They are covered by
   `tools/test_ha_functions.js`. Corrected in the matrix above.
2. **A redaction placeholder was removed.** The draft contained a literal
   `Bearer ***` in the HA REST Controller row. That string gets pasted into a shell
   verbatim and produces a misleading `401`/JSON-decode error; the criterion now
   describes the header instead. (Repo-wide guard:
   `tests/test_env_template.py::test_no_redaction_placeholders_in_commands`.)
