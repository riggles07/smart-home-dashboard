"""Kiosk / WallPanel MQTT contract tests (task t_57dfd219).

These assert the *structure* of the generated flows -- topic names, retention
policy, broker wiring, and the tab-index mapping that the `eval` view switcher
depends on. The function bodies themselves are driven for real by
`tools/test_flow_functions.js`; these tests catch the wiring mistakes that a
body test cannot see (a topic typo, a retained wake command, a broker reference
that points at a node that does not exist).

Contract source: wallpanel.xyz/docs/remote-control/{mqtt-setup,commands,sensors}
(fetched 2026-10-19), mirroring TheTimeWalker/wallpanel-android.
"""

import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOWS = PROJECT_ROOT / "flows" / "all-flows.flow.json"

BASE = "wallpanel/a7lite"
CMD_TOPIC = BASE + "/command"
STATE_TOPIC = BASE + "/state"
MOTION_TOPIC = BASE + "/sensor/motion"


@pytest.fixture(scope="module")
def nodes():
    return json.loads(FLOWS.read_text())


def _of_type(nodes, t):
    return [n for n in nodes if n.get("type") == t]


def _by_name(nodes, t, name):
    hits = [n for n in _of_type(nodes, t) if n.get("name") == name]
    assert len(hits) == 1, f"expected exactly one {t} named {name!r}, got {len(hits)}"
    return hits[0]


# ------------------------------------------------------------------ broker

def test_exactly_one_broker_and_it_points_at_the_lan_docker_host(nodes):
    brokers = _of_type(nodes, "mqtt-broker")
    assert len(brokers) == 1, f"expected 1 broker config node, got {len(brokers)}"
    b = brokers[0]
    # The dashboard already reaches this host for Grafana (:3001) and
    # Prometheus (:9090); MQTT rides the same path.
    assert b["broker"] == "192.168.4.145", b["broker"]
    assert str(b["port"]) == "1883", b["port"]
    assert b["usetls"] is False


def test_every_mqtt_node_references_the_live_broker_id(nodes):
    broker_ids = {b["id"] for b in _of_type(nodes, "mqtt-broker")}
    for n in nodes:
        if n.get("type") in ("mqtt in", "mqtt out"):
            assert n.get("broker") in broker_ids, (
                f"{n.get('name')} references broker {n.get('broker')!r} "
                f"which is not in {broker_ids} -- the node would silently never "
                f"connect"
            )


# ------------------------------------------------------------------ topics

def test_command_topics_match_the_documented_path(nodes):
    outs = _of_type(nodes, "mqtt out")
    assert outs, "no mqtt out nodes"
    for n in outs:
        assert n["topic"] == CMD_TOPIC, f"{n.get('name')} topic={n['topic']!r}"


def test_inbound_topics_are_the_documented_state_and_motion_paths(nodes):
    ins = {n["name"]: n["topic"] for n in _of_type(nodes, "mqtt in")}
    assert ins.get("Tablet state") == STATE_TOPIC, ins
    assert ins.get("Tablet motion") == MOTION_TOPIC, ins


# --------------------------------------------------------------- retention

def test_only_brightness_is_retained(nodes):
    """A retained wake/eval would replay on every tablet reconnect.

    Brightness is the one idempotent command: the tablet should adopt the
    current level when it comes back, without waiting for the next tick.
    """
    by_name = {n["name"]: n for n in _of_type(nodes, "mqtt out")}
    assert by_name["Brightness (retained)"]["retain"] in (True, "true"), \
        "brightness must be retained so a reconnecting tablet adopts it"
    assert by_name["Kiosk command"]["retain"] in (False, "false"), \
        "wake/eval must NOT be retained -- it would replay on every reconnect"


# ------------------------------------------------------- function hygiene

@pytest.mark.parametrize("name", [
    "Build kiosk command", "Motion -> wake", "Schedule -> brightness", "Tablet state",
])
def test_kiosk_function_bodies_are_not_escape_corrupted(nodes, name):
    """Literal backslash-n comments out the body silently (see the newline guard)."""
    f = _by_name(nodes, "function", name)["func"]
    assert f.count("\\n") == 0, f"{name} contains literal backslash-n"
    assert f.count("\n") > 2, f"{name} has no real newlines -- body is one line"


# -------------------------------------------------------- view index map

def test_view_indices_match_the_ui_tab_order(nodes):
    """The `eval` switcher writes location.hash='#!/<n>', where n is the tab's
    position in the VISIBLE nav (ui_tab `order`, hidden tabs excluded).

    If a tab is reordered or inserted, a hardcoded index silently sends the
    tablet to the wrong page -- so derive the expectation from the flow itself
    and compare it against the mapping baked into the function body.
    """
    ui_tabs = [
        n for n in _of_type(nodes, "ui_tab")
        if not n.get("hidden")
    ]
    visible = sorted(ui_tabs, key=lambda n: n["order"])
    name_to_index = {n["name"]: i for i, n in enumerate(visible)}

    # Live-verified 2026-10-19: the nav order really is this.
    assert [n["name"] for n in visible] == [
        "Home Lab", "Network", "Kanban", "System Health", "Settings",
        "Home Assistant", "Kiosk",
    ], [n["name"] for n in visible]

    func = _by_name(nodes, "function", "Build kiosk command")["func"]
    m = re.search(r"var VIEWS = \{([^}]*)\}", func)
    assert m, "VIEWS map not found in Build kiosk command"
    baked = dict(
        (k.strip().strip("'\""), int(v))
        for k, v in re.findall(r"'([a-z]+)':\s*(\d+)", m.group(1))
    )
    expected = {
        "homelab": name_to_index["Home Lab"],
        "network": name_to_index["Network"],
        "kanban": name_to_index["Kanban"],
        "health": name_to_index["System Health"],
        "settings": name_to_index["Settings"],
        "ha": name_to_index["Home Assistant"],
    }
    assert baked == expected, f"baked view map {baked} != tab order {expected}"


def test_kiosk_tab_is_last_in_the_nav(nodes):
    kiosk = _by_name(nodes, "ui_tab", "Kiosk")
    others = [n["order"] for n in _of_type(nodes, "ui_tab") if n.get("name") != "Kiosk"]
    # The Theme tab is order 99 and hidden; Kiosk must still sort before it.
    assert kiosk["order"] < 99
    assert kiosk["order"] > max(o for o in others if o < 99)


# ------------------------------------------------------------- brightness

def test_brightness_levels_are_within_the_documented_1_to_255_range(nodes):
    func = _by_name(nodes, "function", "Schedule -> brightness")["func"]
    m = re.search(r"var B = \{([^}]*)\}", func)
    assert m, "brightness bucket map not found"
    levels = [int(v) for v in re.findall(r":\s*(\d+)", m.group(1))]
    assert len(levels) == 4, f"expected 4 time-of-day buckets, got {levels}"
    for lv in levels:
        assert 1 <= lv <= 255, (
            f"brightness {lv} outside WallPanel's documented 1-255 range -- "
            f"WallPanel does NOT accept percentages"
        )
