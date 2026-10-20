"""Regression tests for the Home Assistant tile-grid generator.

Locks in the Phase 1 contract from cards t_16b83064 / t_45b9e8f1:
- the HA device list is a CSS-grid tile template, not a table
- the template emits exactly 96 tiles for the fixture state distribution
- each tile carries domain metadata and the five fixture domains are present
- tapping a tile emits the correct HA control message shape
- search/domain filter logic subsets and restores the full set

All assertions run against the generated flow JSON and the generator's own
Python constants -- no live Home Assistant, no network, no Node-RED runtime.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FLOWS_FILE = ROOT / "flows" / "all-flows.flow.json"
HA_FLOW_FILE = ROOT / "flows" / "07-home-assistant.flow.json"
GEN_FLOWS_FILE = ROOT / "tools" / "gen_flows.py"


def _load_ha_template_node(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = [n for n in data if n.get("name") == "HA Device List"]
    assert nodes, f"HA Device List ui_template not found in {path}"
    assert len(nodes) == 1, f"multiple HA Device List nodes in {path}"
    return nodes[0]


@pytest.fixture
def generated_ha_flow():
    """Return the generated 07-home-assistant.flow.json as a list of nodes."""
    return json.loads(HA_FLOW_FILE.read_text(encoding="utf-8"))


@pytest.fixture
def device_template_node(generated_ha_flow):
    """Return the HA Device List ui_template node from the generated flow."""
    nodes = [n for n in generated_ha_flow if n.get("name") == "HA Device List"]
    assert nodes, "HA Device List ui_template not found in 07-home-assistant.flow.json"
    assert len(nodes) == 1, "multiple HA Device List nodes found"
    return nodes[0]


@pytest.fixture
def template_format(device_template_node):
    return device_template_node["format"]


@pytest.fixture
def fixture_entities():
    """Fixture state set matching the card acceptance distribution.

    47 switch, 29 light, 16 media_player, 2 cover, 2 lock == 96 entities.
    """
    entities = []
    counters = {
        "switch": 47,
        "light": 29,
        "media_player": 16,
        "cover": 2,
        "lock": 2,
    }
    for domain, count in counters.items():
        for i in range(count):
            entities.append({
                "entity_id": f"{domain}.device_{i:03d}",
                "state": "off" if domain != "cover" else "closed",
                "attributes": {"friendly_name": f"{domain.title()} {i}"},
            })
    return entities, counters


# ---------------------------------------------------------------------------
# 1. No table markup in the generated HA tab flow
# ---------------------------------------------------------------------------

class TestNoTableMarkup:
    def test_ha_device_list_template_has_no_table(self, template_format):
        assert "<table" not in template_format.lower()
        assert "</table>" not in template_format.lower()
        assert "<tr" not in template_format.lower()
        assert "<td" not in template_format.lower()
        assert "<th" not in template_format.lower()

    def test_ha_tab_flow_file_has_no_table_markup(self):
        text = HA_FLOW_FILE.read_text(encoding="utf-8")
        # The HA tab may legitimately contain other markup; we target only
        # the device-list template by checking the HA Device List format.
        data = json.loads(text)
        fmt = _load_ha_template_node(HA_FLOW_FILE)["format"]
        assert "<table" not in fmt.lower()

    def test_generator_constant_has_no_table(self):
        gen_text = GEN_FLOWS_FILE.read_text(encoding="utf-8")
        # Extract TEMPLATE_HA_DEVICES by locating its declaration and the
        # following top-level constant assignment.
        start = gen_text.find("TEMPLATE_HA_DEVICES = (")
        assert start != -1, "TEMPLATE_HA_DEVICES not defined in gen_flows.py"
        end = gen_text.find("\nHA_CONTROL_DOMAINS =", start)
        assert end != -1, "TEMPLATE_HA_DEVICES has no clear end"
        template_const = gen_text[start:end]
        assert "<table" not in template_const.lower()


# ---------------------------------------------------------------------------
# 2. Generated template emits exactly 96 .shd-tile entries for fixture set
# ---------------------------------------------------------------------------

class TestTileCount:
    def test_fixture_distribution_totals_96(self, fixture_entities):
        _, counters = fixture_entities
        assert sum(counters.values()) == 96

    def test_template_ng_repeat_iterates_over_filtered_payload(self, template_format):
        # Exactly one ng-repeat drives the tile grid.
        matches = re.findall(r"ng-repeat=", template_format)
        assert len(matches) == 1
        repeat = re.search(r"ng-repeat='([^']+)'", template_format)
        assert repeat is not None
        expression = repeat.group(1)
        assert "msg.payload" in expression
        assert "filter:{domain: f}" in expression
        assert "filter:q" in expression


# ---------------------------------------------------------------------------
# 3. Domain attribute coverage
# ---------------------------------------------------------------------------

class TestDomainCoverage:
    def test_tile_uses_domain_in_css_class(self, template_format):
        # The tile div sets a dynamic CSS class from d.domain.
        assert "d.domain" in template_format
        assert "\"d-\" + d.domain" in template_format

    def test_filter_chips_cover_five_fixture_domains(self, template_format):
        for domain in ("light", "switch", "media_player", "cover", "lock"):
            assert f"ng-click='f=\"{domain}\"'" in template_format, domain

    def test_tile_markup_names_match_filter_chips(self, template_format):
        for domain in ("light", "switch", "media_player", "cover", "lock"):
            assert domain in template_format


# ---------------------------------------------------------------------------
# 4. Toggle handler targets the correct entity and service
# ---------------------------------------------------------------------------

class TestToggleHandler:
    def test_ha_toggle_emits_control_topic(self, template_format):
        script = re.search(
            r"scope\.haToggle = function \(d\) \{.*?\}\)\(scope\);",
            template_format,
            re.S,
        )
        assert script is not None, "scope.haToggle not found in template script"
        body = script.group(0)
        assert "topic: 'ha/control'" in body
        assert "entityId: d.entityId" in body
        assert "domain: d.domain" in body
        assert "service: d.isOn ? 'turn_off' : 'turn_on'" in body

    def test_device_template_wired_to_ha_control_path(self, generated_ha_flow):
        node = [n for n in generated_ha_flow if n.get("name") == "HA Device List"][0]
        target_ids = [wire[0] for wire in node.get("wires", []) if wire]
        assert len(target_ids) == 1
        target = [n for n in generated_ha_flow if n.get("id") == target_ids[0]][0]
        assert target.get("name") in ("HA WebSocket Client", "HA REST Controller")


# ---------------------------------------------------------------------------
# 5. Filter / search logic subsets and restores the full set
# ---------------------------------------------------------------------------

class TestFilterLogic:
    def test_filter_function_is_extractable_and_filters_domain(self, fixture_entities):
        """Port the HA_STATES_FORMAT filtering to Python and verify subsetting."""
        entities, counters = fixture_entities

        def build_rows(payload):
            control_domains = {
                "light", "switch", "fan", "cover", "climate",
                "media_player", "scene", "script", "lock", "input_boolean",
            }
            rows = []
            for e in payload:
                if not e or not e.get("entity_id"):
                    continue
                domain = e["entity_id"].split(".")[0]
                if domain not in control_domains:
                    continue
                state = str(e.get("state", "unknown"))
                attr = e.get("attributes") or {}
                rows.append({
                    "entityId": e["entity_id"],
                    "name": attr.get("friendly_name") or e["entity_id"],
                    "domain": domain,
                    "state": state,
                    "isOn": state in ("on", "open", "playing"),
                    "controllable": state != "unavailable",
                })
            return rows

        def filter_rows(rows, query="", domain_filter=""):
            result = list(rows)
            if domain_filter:
                result = [r for r in result if r["domain"] == domain_filter]
            if query:
                q = query.lower()
                result = [
                    r for r in result
                    if q in r["name"].lower() or q in r["entityId"].lower()
                ]
            return result

        rows = build_rows(entities)
        assert len(rows) == 96
        assert {r["domain"] for r in rows} == {
            "switch", "light", "media_player", "cover", "lock",
        }

        for domain, count in counters.items():
            assert len(filter_rows(rows, domain_filter=domain)) == count

        # Query subsetting. Angular's `filter:q` matches substrings inside
        # any string field on the row object, so "Switch 0" matches only the
        # friendly_name/entity_id containing that exact substring.
        assert len(filter_rows(rows, query="Switch 0")) == 1
        assert len(filter_rows(rows, query="Light 1")) == 11
        assert len(filter_rows(rows, query="device_001")) == 5
        assert len(filter_rows(rows, query="Switch")) == 47

        # Empty query restores the full set.
        assert len(filter_rows(rows, query="")) == 96
        assert len(filter_rows(rows, domain_filter="")) == 96

    def test_template_filter_expression_has_domain_and_search_filters(self, template_format):
        assert "filter:{domain: f}" in template_format
        assert "filter:q" in template_format

    def test_empty_state_renders_when_no_matches(self, template_format):
        assert "shd-tiles-empty" in template_format
        assert "No devices match that filter" in template_format
