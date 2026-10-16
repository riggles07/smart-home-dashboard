"""Guard: every generated function body must contain REAL newlines.

Regression test for the 2026-10-16 defect where `tools/gen_flows.py` emitted
literal backslash-n (2 chars) instead of newlines for the Home Assistant
functions. Because each body starts with a `//` comment, the whole function
collapsed onto one commented-out line: it parsed, deployed, reported
`flows.state = start`, showed no error badge and no node status -- it was simply
dead code. Nothing else in the suite caught it.

The assertion is deliberately blunt: zero literal backslash-n anywhere in a
`func` body.
"""
import json
import re
from pathlib import Path

import pytest

FLOWS_DIR = Path(__file__).resolve().parent.parent / "flows"
ALL_FLOWS = FLOWS_DIR / "all-flows.flow.json"


def _function_nodes(path):
    data = json.loads(Path(path).read_text())
    return [n for n in data if n.get("type") == "function"]


def test_all_flows_exists():
    assert ALL_FLOWS.exists(), f"missing {ALL_FLOWS}"


def test_no_literal_backslash_n_in_any_function():
    """A literal \\n in a func body means an over-escaped generator string."""
    offenders = []
    for node in _function_nodes(ALL_FLOWS):
        body = node.get("func", "")
        literal = body.count("\\" + "n")
        if literal:
            offenders.append((node.get("name"), literal, body.count("\n")))
    assert not offenders, (
        "these function bodies contain literal backslash-n instead of real "
        "newlines (name, literal_count, real_newlines): "
        f"{offenders}. Fix the escaping in tools/gen_flows.py -- one extra "
        "backslash in the Python string literal is the usual cause."
    )


def test_every_function_has_real_newlines():
    """Multi-line bodies must actually be multi-line."""
    suspicious = []
    for node in _function_nodes(ALL_FLOWS):
        body = node.get("func", "")
        name = node.get("name", "?")
        # comment-only or genuine one-liners are allowed, but nothing here is
        if len(body) > 120 and body.count("\n") == 0:
            suspicious.append((name, len(body)))
    assert not suspicious, (
        "long function bodies with zero real newlines are almost certainly "
        f"over-escaped generators: {suspicious}"
    )


def test_ha_functions_are_real_code_not_one_big_comment():
    """The HA bodies must contain executable statements, not just comments.

    The original defect left each body as a single `//` line: it parsed and
    deployed but did nothing. Stripping comments must leave real code behind.
    """
    by_name = {n.get("name"): n.get("func", "") for n in _function_nodes(ALL_FLOWS)}
    for name in ("HA WebSocket Client", "HA REST Controller"):
        body = by_name.get(name)
        assert body, f"{name} missing from {ALL_FLOWS.name}"
        assert body.count("\n") > 1, f"{name} is a single line -- over-escaped generator?"
        code = "\n".join(
            re.sub(r"//.*$", "", line) for line in body.split("\n")
        ).strip()
        assert code, f"{name} strips to nothing -- the whole body is a comment"
        assert "node.status" in code, (
            f"{name} has no node.status call; it is probably not the real body"
        )
        # the classic per-message contract: return the outgoing message
        assert "return" in code, f"{name} never returns a message"


@pytest.mark.parametrize("flow_file", sorted(p.name for p in FLOWS_DIR.glob("*.flow.json")))
def test_no_literal_backslash_n_in_per_tab_flows(flow_file):
    """Same guard across the per-tab files that all-flows is concatenated from."""
    path = FLOWS_DIR / flow_file
    offenders = [
        n.get("name") for n in _function_nodes(path)
        if n.get("func", "").count("\\" + "n")
    ]
    assert not offenders, f"{flow_file}: literal backslash-n in {offenders}"


# --- Node-RED 5.0.7 function-node API constraints ---------------------------
# Measured on the live runtime (node-red 5.0.7, node v24.21.0):
#   typeof on        -> "undefined"          => `on('input', ...)` throws
#                                               "ReferenceError: on is not defined"
#   node.on('input') -> throws              => "Cannot add listener to 'input'
#                                               event within Function"
#   send / done      -> "undefined"          => no async-callback signature
#   initialize vars  -> NOT in body scope
#   context          -> DOES persist across messages
# So every function body must use the CLASSIC style: run per message, return
# the outgoing message, use node.send() for async, and context for state.

_UNSUPPORTED = (
    (re.compile(r"(?<![.\w])on\s*\("), "bare on(...) -- use the classic per-message style"),
    (re.compile(r"node\.on\s*\("), "node.on(...) -- throws inside a function node"),
    (re.compile(r"(?<![.\w])(send|done)\s*\("), "send()/done() -- not provided by this runtime"),
)


def _strip_comments(body):
    return "\n".join(re.sub(r"//.*$", "", line) for line in body.split("\n"))


def test_function_bodies_avoid_unsupported_runtime_apis():
    offenders = []
    for node in _function_nodes(ALL_FLOWS):
        code = _strip_comments(node.get("func", ""))
        for pattern, why in _UNSUPPORTED:
            if pattern.search(code):
                offenders.append((node.get("name"), why))
    assert not offenders, (
        f"function bodies use APIs this Node-RED does not provide: {offenders}. "
        "They will throw at runtime -- see the constraints documented in "
        "tools/test_ha_functions.js."
    )


def test_ha_nodes_are_wired_to_both_outputs():
    """The WS node must separate control (out0) from state (out1)."""
    ws = next((n for n in _function_nodes(ALL_FLOWS) if n.get("name") == "HA WebSocket Client"), None)
    assert ws is not None, "HA WebSocket Client missing"
    assert ws.get("outputs") == 2, f"expected 2 outputs, got {ws.get('outputs')}"
    wires = ws.get("wires") or []
    assert len(wires) == 2 and wires[0] and wires[1], (
        f"both outputs must be wired (control -> REST, state -> debug): {wires}"
    )

    rest = next((n for n in _function_nodes(ALL_FLOWS) if n.get("name") == "HA REST Controller"), None)
    assert rest is not None, "HA REST Controller missing"
    assert len(rest.get("wires", [])) == 1 and rest["wires"][0], "REST controller must be wired onward"
