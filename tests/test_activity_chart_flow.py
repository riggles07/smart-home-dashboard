"""Regression tests for the Activity tab generator section (P3 follow-up).

Why these exist: P3's worker delivered `flows/09-activity-chart.flow.json` as a
HAND-WRITTEN file. `tools/gen_flows.py` builds `all-flows.flow.json` -- the file
that is actually deployed -- from its own node list, so every one of the chart's
nodes was absent from the bundle while its CSS shipped inside the theme
template. The dashboard therefore had dead styles and no chart, and nothing in
the test suite noticed, because every test read a single flow file in isolation.

The load-bearing assertion is `test_every_activity_node_is_in_the_deploy_bundle`:
any node that exists only in a per-tab file is a node that never deploys.

The rest lock in four defects that were found while porting:
  1. the history call hit /api/history/events, which is not an HA REST endpoint
  2. the HA history response is one array per ENTITY, not a flat event list
  3. `if (!ARR.indexOf(d) >= 0) continue` inverts the domain filter in JS
  4. Chart.js 2.x needs {t, y} points; {t, payload} leaves every point y-less
"""
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "flows"
BUNDLE = FLOWS / "all-flows.flow.json"
ACTIVITY = FLOWS / "09-activity-chart.flow.json"


def _nid(seed: str) -> str:
    return hashlib.sha1(seed.encode()).hexdigest()[:16]


@pytest.fixture(scope="module")
def bundle():
    assert BUNDLE.exists(), "all-flows.flow.json missing -- run tools/gen_flows.py"
    return json.loads(BUNDLE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def activity():
    assert ACTIVITY.exists(), (
        "09-activity-chart.flow.json missing -- the generator must emit it, "
        "not a hand-written file"
    )
    return json.loads(ACTIVITY.read_text(encoding="utf-8"))


def _by_name(nodes, name):
    hits = [n for n in nodes if n.get("name") == name]
    assert hits, f"node named {name!r} not found"
    assert len(hits) == 1, f"{len(hits)} nodes named {name!r}"
    return hits[0]


# --------------------------------------------------------------------- structure
def test_activity_tab_exists_in_bundle(bundle):
    tab = [n for n in bundle if n.get("type") == "tab"
           and n.get("label") == "Activity"]
    assert len(tab) == 1, "exactly one Activity tab expected"
    assert tab[0]["id"] == _nid("tab-activity")


def test_activity_ui_tab_is_registered_in_bundle(bundle):
    tabs = [n for n in bundle if n.get("type") == "ui_tab"
            and n.get("name") == "Activity"]
    assert len(tabs) == 1
    # index 6 of the visible nav: after the six kiosk VIEWS targets, before Kiosk
    assert tabs[0]["order"] == 8
    assert tabs[0]["icon"] == "show_chart"


def test_every_activity_node_is_in_the_deploy_bundle(bundle, activity):
    """THE orphan guard: a node in a per-tab file but not in the bundle is
    never deployed. This is the exact failure P3 shipped."""
    bundle_ids = {n.get("id") for n in bundle}
    missing = [n.get("name") or n.get("id") for n in activity
               if n.get("id") not in bundle_ids]
    assert not missing, f"nodes absent from the deploy bundle: {missing}"


def test_activity_nodes_all_belong_to_the_activity_tab(activity):
    tab_id = _nid("tab-activity")
    strays = [n.get("name") or n.get("id") for n in activity
              if n.get("type") != "tab" and n.get("z") != tab_id]
    assert not strays, f"nodes with the wrong z (would land in 99-other): {strays}"


def test_alert_banner_comes_first(activity):
    groups = [n for n in activity if n.get("type") == "ui_group"]
    alerts = [g for g in groups if g.get("name") == "Alerts"]
    assert len(alerts) == 1, "every monitored tab carries one Alerts group"
    assert alerts[0]["order"] == 1
    assert alerts[0]["disp"] is False or alerts[0].get("collapse") is False


def test_catch_node_feeds_the_alert_evaluator(activity):
    catches = [n for n in activity if n.get("type") == "catch"]
    assert len(catches) == 1, "one catch node per tab"
    alert_fn = _nid("fn-act-alert")
    assert catches[0]["wires"] == [[alert_fn]]


# ------------------------------------------------------------------ query contract
def test_history_call_uses_the_rest_history_period_endpoint(activity):
    fn = _by_name(activity, "Build history query")
    assert "/api/history/period/" in fn["func"]
    assert "/api/history/events" not in fn["func"], (
        "/api/history/events is not an HA REST endpoint"
    )
    assert "filter_entity_id=" in fn["func"]
    assert "minimal_response" in fn["func"]


def test_domain_filter_is_not_the_inverted_indexof(activity):
    fn = _by_name(activity, "Build history query")
    assert "!(DOMAINS.indexOf" not in fn["func"].replace(" ", "")
    assert "DOMAINS.indexOf(dom) < 0" in fn["func"]


def test_hour_buckets_are_counted_from_a_per_entity_response(activity):
    """The REST response is [[state,...], [state,...]] -- one array per entity."""
    fn = _by_name(activity, "Count changes per hour")
    src = fn["func"]
    assert "perEntity" in src and "Array.isArray(series)" in src
    assert "last_changed" in src
    assert "points.push({t:" in src and "y: buckets" in src, (
        "Chart.js 2.x needs {t, y} points"
    )


def test_chart_template_reads_y_not_payload(activity):
    tpl = _by_name(activity, "Activity Area Chart")
    src = tpl["format"]
    assert "typeof ctx.raw.y" in src or "ctx.raw.y" in src
    assert "new window.Chart" in src
    assert "type: 'time'" in src, "hourly axis needs the Chart.js time scale"
    # a zero series must be described in words, not drawn as a flat line
    assert "chart-empty" in src


def test_poll_interval_is_five_minutes(activity):
    inj = [n for n in activity if n.get("type") == "inject"]
    assert len(inj) == 1
    assert str(inj[0]["repeat"]) == "300", "each poll is 2 GETs + 5000 history rows"


def test_unreachable_history_is_critical_not_info(activity):
    fn = _by_name(activity, "Evaluate activity alerts")
    src = fn["func"]
    assert "ha/error" in src
    assert "'critical'" in src
