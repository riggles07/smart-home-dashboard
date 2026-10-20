"""Behavioural tests for the Activity tab's function nodes, run through real V8.

Syntax is not behaviour: the ported code's original defects (inverted domain
filter, event-shaped formatter against a per-entity response) all parsed fine.
These tests extract each function body from the generated flow and execute it in
Node with Node-RED-shaped stubs, then assert on the messages it emits.

Skipped when no `node` binary is available -- the structural pytest suite still
covers the flow shape in that case.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ACTIVITY = ROOT / "flows" / "09-activity-chart.flow.json"

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not installed")

HARNESS = r"""
const funcs = __FUNCS__;

function run(src, msg, envMap) {
  const node = { status() {}, warn() {}, error() {}, log() {}, send() {} };
  const store = {};
  const context = { get(k) { return store[k]; }, set(k, v) { store[k] = v; } };
  const flow = { get(k) { return store[k]; }, set(k, v) { store[k] = v; } };
  const global = { get(k) { return store[k]; }, set(k, v) { store[k] = v; } };
  const env = { get(k) { return envMap[k]; } };
  const f = new Function('msg', 'node', 'context', 'flow', 'global', 'env', src);
  return f(msg, node, context, flow, global, env);
}

const out = {};
const ENV = { HA_URL: 'http://ha.local:8123/', HA_TOKEN: 'tok' };

// ---- 0. step 1 only builds the states call -------------------------------
const r0 = run(funcs.listEntities, { payload: '' }, ENV);
out.statesUrl = r0[0].url;

// ---- 1. entity discovery: the domain filter must KEEP lights -------------
const states = [
  { entity_id: 'light.kitchen', state: 'on' },
  { entity_id: 'light.hall', state: 'off' },
  { entity_id: 'switch.fan', state: 'on' },
  { entity_id: 'sensor.temp', state: '21' },
  { entity_id: 'lock.front', state: 'locked' },
  { entity_id: 'light.gone', state: 'unavailable' },
];
// Step 2 turns /api/states into the history query -- it does the filtering.
const r1 = run(funcs.buildHistory, { payload: states, statusCode: 200 }, ENV);
const url = r1[0].url;
out.url = url;
out.ids = decodeURIComponent((url.match(/filter_entity_id=([^&]*)/) || [])[1] || '');

// ---- 2. formatter: per-entity arrays -> 24 hourly {t,y} points -----------
const now = Date.now();
const HOUR = 3600000;
function at(hoursAgo) { return new Date(now - hoursAgo * HOUR).toISOString(); }
const history = [
  [ { last_changed: at(0.1) }, { last_changed: at(0.2) }, { last_changed: at(0.3) } ],
  [ { last_changed: at(2.1) } ],
  [ { last_changed: at(30) } ],           // older than 24h -> ignored
];
const r2 = run(funcs.count, { payload: history, statusCode: 200, _entityCount: 3 }, ENV);
const series = r2[0].payload.series;
out.points = series.length;
out.total = r2[0].payload.total;
out.entities = r2[0].payload.entities;
out.first = series[0];
out.last = series[series.length - 1];
out.allHaveXY = series.every(p => typeof p.x === 'number' && typeof p.y === 'number');
out.haveT = series.some(p => p.t !== undefined);
out.allHaveTY = series.every(p => typeof p.t === 'number' && typeof p.y === 'number');
// out1 must carry the same counts, or the alert banner never updates on success
out.out1 = r2[1] ? { total: r2[1]._total, entities: r2[1]._entities } : null;

// ---- 3. failure paths feed the alert evaluator, not the chart ------------
const r3 = run(funcs.count, { statusCode: 500, payload: {} }, ENV);
out.errOut0 = r3[0];
out.errTopic = r3[1] && r3[1].topic;
const r4 = run(funcs.alert, { topic: 'ha/error', _error: 'connect ECONNREFUSED' }, ENV);
out.alert = r4.payload;

// ---- 4. the banner reads the counts off the MESSAGE, as out1 emits them ----
const r5 = run(funcs.alert, { payload: 485, _total: 485, _entities: 110 }, ENV);
out.okAlert = r5.payload;

console.log(JSON.stringify(out));
"""


def _function_sources():
    nodes = json.loads(ACTIVITY.read_text(encoding="utf-8"))
    by = {n.get("name"): n.get("func") for n in nodes if n.get("type") == "function"}
    return {
        "listEntities": by["List entities"],
        "buildHistory": by["Build history query"],
        "count": by["Count changes per hour"],
        "alert": by["Evaluate activity alerts"],
    }


@pytest.fixture(scope="module")
def result():
    funcs = _function_sources()
    script = HARNESS.replace("__FUNCS__", json.dumps(funcs))
    proc = subprocess.run(["node", "-e", script], capture_output=True, text=True)
    assert proc.returncode == 0, f"node harness failed:\n{proc.stderr}"
    return json.loads(proc.stdout.strip().splitlines()[-1])


def test_step_one_only_lists_entities(result):
    """Step 1 must stay a plain /api/states GET: the history endpoint takes no
    wildcards, so ids have to be discovered first."""
    assert result["statesUrl"].endswith("/api/states")


def test_lights_are_not_filtered_out(result):
    """The worker's `!(indexOf) >= 0` test dropped every domain at index 0."""
    assert "light.kitchen" in result["ids"]
    assert "light.hall" in result["ids"]
    assert "switch.fan" in result["ids"]
    assert "lock.front" in result["ids"]


def test_sensors_and_unavailable_entities_are_excluded(result):
    assert "sensor.temp" not in result["ids"]
    assert "light.gone" not in result["ids"]


def test_history_call_is_the_rest_endpoint(result):
    assert "/api/history/period/" in result["url"]
    assert "minimal_response" in result["url"]


def test_formatter_emits_24_hourly_ty_points(result):
    assert result["points"] == 24
    assert result["allHaveXY"] is True, "this Chart.js build plots {x, y} only"
    assert result["haveT"] is False, (
        "a {t, y} series draws zero pixels on this build -- the scales render and "
        "the line is silently missing"
    )


def test_formatter_counts_changes_in_the_right_bucket(result):
    assert result["total"] == 4, "3 in the current hour + 1 two hours ago"
    assert result["last"]["y"] == 3, "newest bucket holds the current-hour changes"


def test_horizon_drops_events_older_than_24h(result):
    assert result["total"] == 4, "the 30h-old event must not be counted"


def test_a_successful_poll_also_feeds_the_alert_banner(result):
    """out1 was wired to the evaluator but emitted null, so the banner sat on its
    default text forever while the chart updated."""
    assert result["out1"] == {"total": 4, "entities": 3}


def test_a_http_failure_reaches_the_alert_evaluator(result):
    assert result["errOut0"] is None, "no chart update on failure"
    assert result["errTopic"] == "ha/error"


def test_alert_banner_treats_unreachable_history_as_critical(result):
    assert result["alert"]["severity"] == "critical"
    assert "ECONNREFUSED" in result["alert"]["message"]


def test_a_successful_poll_reports_counts_not_awaiting(result):
    """Regression: the evaluator read payload._total while out1's payload is the
    bare number, so a healthy 485-change poll was announced as 'awaiting'."""
    assert result["okAlert"]["severity"] == "ok"
    assert "485" in result["okAlert"]["message"]
    assert "110" in result["okAlert"]["message"]
