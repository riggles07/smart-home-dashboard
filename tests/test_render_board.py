"""Tests for the "Render board" function node (Kanban tab).

Card: t_d0565899 -- the Render board node was the least-tested part of the flow
and had no dedicated Python coverage. `tools/test_flow_functions.js` exercises a
COPY of the body inlined as a string; nothing asserted that the node as
GENERATED actually exists, is wired where it belongs, or would be rejected if it
were shipped malformed.

Established from tools/gen_flows.py (the source of truth) BEFORE asserting:

    Render board  (id nid("fn-k-render"), type function, tab "Kanban")
        var cards = flow.get('kanban_cards') || [];
        node.status({fill:'blue',shape:'dot',text:cards.length + ' cards'});
        msg.payload = cards;
        return [msg, msg];
    outputs: 2, noerr: 0, libs: [], initialize: "" (empty)
    wires:   [[Cards ui_template], [Cards debug]]   -- out0 = UI, out1 = debug

    driven by: ui_button "Add" (topic kanban/render)
               inject    "Load board" (repeat 60, once, onceDelay 1.5)

Every path is resolved relative to this file -- a hardcoded absolute path passes
on the author's machine and fails in CI (that mistake has been made twice in
this repo already).
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "flows" / "all-flows.flow.json"
PER_TAB = ROOT / "flows" / "04-kanban-board.flow.json"
VALIDATOR = ROOT / "tools" / "validate_flows.py"

RENDER_NAME = "Render board"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def load(path=FLOWS):
    return json.loads(Path(path).read_text())


def find(nodes, name, ntype="function"):
    hits = [n for n in nodes if n.get("name") == name and n.get("type") == ntype]
    return hits


def render_node(nodes=None):
    nodes = nodes if nodes is not None else load()
    hits = find(nodes, RENDER_NAME)
    assert len(hits) == 1, (
        f"expected exactly ONE function node named {RENDER_NAME!r}, found {len(hits)}"
    )
    return hits[0], nodes


def body_of(node):
    return node.get("func", "")


def run_validator(path):
    """Run the repo's real validator on a given flow file."""
    p = subprocess.run([sys.executable, str(VALIDATOR), str(path)],
                       capture_output=True, text=True, cwd=str(ROOT))
    return p.returncode, (p.stdout + p.stderr)


def write_mutated(tmp_path, mutate):
    """Deep-copy the flows, apply `mutate(nodes)`, write to a temp file."""
    nodes = load()
    mutate(nodes)
    out = tmp_path / "mutated.flow.json"
    out.write_text(json.dumps(nodes))
    return out


# --------------------------------------------------------------------------
# POSITIVE -- the node exists with the wiring it is supposed to have
# --------------------------------------------------------------------------
class TestRenderBoardWiring:
    def test_render_board_node_exists_once_and_is_a_function(self):
        node, _ = render_node()
        assert node["type"] == "function"
        assert node["name"] == RENDER_NAME

    def test_render_board_lives_on_the_kanban_tab(self):
        node, nodes = render_node()
        tab = next((n for n in nodes if n["id"] == node.get("z")), None)
        assert tab is not None, f"{RENDER_NAME} has z={node.get('z')!r}, not a tab"
        assert tab["type"] == "tab"
        assert tab.get("label") == "Kanban", (
            f"{RENDER_NAME} is on tab {tab.get('label')!r}, expected 'Kanban'"
        )

    def test_render_board_declares_two_outputs(self):
        node, _ = render_node()
        assert node["outputs"] == 2, (
            f"{RENDER_NAME} declares outputs={node['outputs']}, expected 2 "
            "(the body returns [msg, msg])"
        )
        assert node.get("noerr") == 0, "noerr must stay 0, else errors are swallowed"

    def test_render_board_has_no_external_libs(self):
        node, _ = render_node()
        assert not node.get("libs"), (
            f"{RENDER_NAME} declares libs={node.get('libs')!r}; it needs none, and a "
            "libs entry that cannot resolve stops the node loading entirely"
        )

    def test_render_board_output_0_goes_to_the_cards_template(self):
        node, nodes = render_node()
        wires = node.get("wires") or []
        assert len(wires) == 2, f"expected 2 wire arrays, got {len(wires)}"
        assert len(wires[0]) == 1, f"out0 should feed exactly one node, got {wires[0]}"
        target = next((n for n in nodes if n["id"] == wires[0][0]), None)
        assert target is not None, f"out0 -> {wires[0][0]} does not exist"
        assert target["type"] == "ui_template", (
            f"out0 should drive the Cards ui_template, got {target['type']}"
        )
        assert target.get("name") == "Cards"

    def test_render_board_output_1_goes_to_the_cards_debug(self):
        node, nodes = render_node()
        wires = node["wires"]
        assert len(wires[1]) == 1, f"out1 should feed exactly one node, got {wires[1]}"
        target = next((n for n in nodes if n["id"] == wires[1][0]), None)
        assert target is not None, f"out1 -> {wires[1][0]} does not exist"
        assert target["type"] == "debug", (
            f"out1 is the debug tap, got {target['type']}"
        )

    def test_render_board_is_driven_by_the_add_button(self):
        _, nodes = render_node()
        btn = next((n for n in nodes
                    if n["type"] == "ui_button" and n.get("name") == "Add"), None)
        assert btn is not None, "the 'Add' ui_button is missing"
        flat = [t for out in (btn.get("wires") or []) for t in out]
        assert any(n["id"] in flat and n["name"] == RENDER_NAME for n in nodes), (
            "the 'Add' button does not wire into " + RENDER_NAME
        )

    def test_render_board_is_driven_by_the_load_board_inject(self):
        _, nodes = render_node()
        inj = next((n for n in nodes
                    if n["type"] == "inject" and n.get("name") == "Load board"), None)
        assert inj is not None, "the 'Load board' inject is missing"
        flat = [t for out in (inj.get("wires") or []) for t in out]
        assert any(n["id"] in flat and n["name"] == RENDER_NAME for n in nodes), (
            "the 'Load board' inject does not wire into " + RENDER_NAME
        )
        # it is the periodic refresh, and must fire once at startup or the tab
        # stays blank until the first 60s tick
        assert str(inj.get("repeat")) == "60", f"repeat={inj.get('repeat')!r}"
        assert inj.get("once") is True, "the inject must fire once on startup"

    def test_render_board_matches_the_per_tab_file(self):
        """all-flows.flow.json must not drift from the per-tab build."""
        node, _ = render_node()
        per_tab = load(PER_TAB)
        same = find(per_tab, RENDER_NAME)
        assert len(same) == 1, f"{PER_TAB.name} has {len(same)} {RENDER_NAME} nodes"
        for key in ("func", "outputs", "wires", "type", "name", "libs"):
            assert same[0].get(key) == node.get(key), (
                f"{RENDER_NAME}.{key} differs between 04-kanban-board and all-flows"
            )


# --------------------------------------------------------------------------
# POSITIVE -- what the body actually does
# --------------------------------------------------------------------------
class TestRenderBoardBody:
    def test_render_board_reads_the_flow_context_key_with_an_empty_default(self):
        body = body_of(render_node()[0])
        assert "flow.get('kanban_cards')" in body or 'flow.get("kanban_cards")' in body, (
            f"{RENDER_NAME} must read the kanban_cards flow-context key"
        )
        assert "|| []" in body, (
            "the context read must default to an empty array, or a fresh runtime "
            "throws / renders nothing"
        )

    def test_render_board_publishes_the_cards_on_the_payload(self):
        body = body_of(render_node()[0])
        assert "msg.payload = cards" in body, (
            f"{RENDER_NAME} must assign the cards array to msg.payload"
        )

    def test_render_board_emits_both_outputs_from_one_message(self):
        body = body_of(render_node()[0])
        assert "return [msg, msg]" in body, (
            f"{RENDER_NAME} must return [msg, msg] -- one emit per declared output; "
            f"returning a bare msg leaves out1 dark"
        )

    def test_render_board_reports_its_card_count_via_node_status(self):
        body = body_of(render_node()[0])
        assert "node.status(" in body, f"{RENDER_NAME} should surface a status"
        assert "cards.length" in body, (
            f"{RENDER_NAME} status must include the card count"
        )

    def test_render_board_body_uses_real_newlines_not_literal_backslash_n(self):
        """The dead-code trap: a literal \\n makes the whole body one // comment.

        That is precisely how both Home Assistant nodes shipped dead while the
        entire suite stayed green. A body that is syntactically plausible and
        does nothing is the failure mode this asserts against.
        """
        node, _ = render_node()
        body = body_of(node)
        literal = body.count("\\n")
        real = body.count("\n")
        assert literal == 0, (
            f"{RENDER_NAME} body contains {literal} literal backslash-n sequence(s); "
            "the generated JSON must carry real newlines"
        )
        # MEASURED, not assumed: the body is 4 statements separated by 3 newlines,
        # with no trailing newline (repr ends "...return [msg, msg];"). Asserting
        # 4 here was my first guess and it failed -- which is the point.
        assert real >= 3, (
            f"{RENDER_NAME} body has only {real} real newline(s); a 4-statement "
            "body needs at least 3 separators"
        )
        assert len(body.splitlines()) == 4, (
            f"{RENDER_NAME} body is {len(body.splitlines())} line(s), expected the "
            "4-statement body"
        )
        assert not body.lstrip().startswith("//"), (
            f"{RENDER_NAME} body starts with a comment -- if the body is one line, "
            "this silences the entire node"
        )


# --------------------------------------------------------------------------
# NEGATIVE -- a malformed variant is REJECTED by the repo's real validator
# --------------------------------------------------------------------------
class TestRenderBoardMalformedRejected:
    def test_control_the_validator_accepts_the_unmutated_flows(self):
        """Without this, a negative test could pass because the validator is broken."""
        rc, out = run_validator(FLOWS)
        assert rc == 0, f"validator rejects the unmutated flows:\n{out}"
        assert "OK: structure valid" in out

    def test_render_board_with_empty_func_is_rejected(self, tmp_path):
        def mutate(nodes):
            for n in nodes:
                if n.get("name") == RENDER_NAME and n.get("type") == "function":
                    n["func"] = ""
        path = write_mutated(tmp_path, mutate)
        rc, out = run_validator(path)
        assert rc != 0, f"validator ACCEPTED a {RENDER_NAME} with an empty body:\n{out}"
        assert "empty func" in out, out

    def test_render_board_with_dangling_output_wire_is_rejected(self, tmp_path):
        def mutate(nodes):
            for n in nodes:
                if n.get("name") == RENDER_NAME and n.get("type") == "function":
                    n["wires"] = [["no-such-node-id"], list(n.get("wires", [[], []])[1])]
        path = write_mutated(tmp_path, mutate)
        rc, out = run_validator(path)
        assert rc != 0, f"validator ACCEPTED a dangling wire out of {RENDER_NAME}:\\n{out}"
        assert "does not exist" in out, out

    def test_render_board_orphaned_from_its_tab_is_rejected(self, tmp_path):
        def mutate(nodes):
            for n in nodes:
                if n.get("name") == RENDER_NAME and n.get("type") == "function":
                    n["z"] = "not-a-tab-id"
        path = write_mutated(tmp_path, mutate)
        rc, out = run_validator(path)
        assert rc != 0, f"validator ACCEPTED an orphaned {RENDER_NAME}:\n{out}"
        assert "is not a tab" in out, out

    def test_a_duplicated_render_board_node_is_rejected(self, tmp_path):
        """Two nodes with the same id is the shape a bad merge produces."""
        def mutate(nodes):
            dup = next(n for n in nodes
                       if n.get("name") == RENDER_NAME and n.get("type") == "function")
            nodes.append(dict(dup))
        path = write_mutated(tmp_path, mutate)
        rc, out = run_validator(path)
        assert rc != 0, f"validator ACCEPTED a duplicated {RENDER_NAME}:\n{out}"
        assert "duplicate id" in out, out

    def test_literal_backslash_n_body_would_be_rejected_by_our_guard(self):
        """Falsify the newline guard itself: the dead-code shape must trip it."""
        node, _ = render_node()
        broken = {**node, "func": node["func"].replace("\n", "\\n")}
        literal = broken["func"].count("\\n")
        real = broken["func"].count("\n")
        assert literal > 0 and real == 0, (
            "the mutation did not produce the dead-code shape, so this control proves "
            "nothing"
        )
        # and the same assertion the positive test makes must now FAIL
        with pytest.raises(AssertionError):
            assert literal == 0, (
                f"{RENDER_NAME} body contains {literal} literal backslash-n sequence(s)"
            )
