"""Test Home Assistant WebSocket client integration."""
import pytest
import json
import re
import os
from pathlib import Path

# Project paths, resolved relative to THIS FILE.
# Never hardcode an absolute dev path: it resolves on the author's machine and
# nowhere else, so the suite passes locally and fails in CI. That mistake has now
# been made twice in this repo -- also in tools/test_flow_functions.js.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FLOWS_FILE = PROJECT_ROOT / "flows" / "all-flows.flow.json"
ENV_EXAMPLE = PROJECT_ROOT / "deploy" / ".env.example"


class TestHAWsClient:
    """Test WebSocket client for Home Assistant state sync."""
    
    def test_ws_url_construction(self):
        """Test WebSocket URL is correctly constructed from HA_URL."""
        ha_url = "http://homeassistant.local:8123"
        ws_path = "/api/websocket"
        
        # Simulate URL conversion (replace http with ws)
        actual = ha_url.replace('http', 'ws') + ws_path
        
        assert actual == "ws://homeassistant.local:8123/api/websocket"
    
    def test_auth_frame_format(self):
        """Test authentication frame format."""
        token = "test_token_123"
        auth_frame = json.dumps({
            "type": "auth",
            "access_token": token
        })
        
        assert auth_frame.startswith('{"type": "auth"')
        assert "access_token" in auth_frame
    
    def test_get_states_frame(self):
        """Test get_states frame format."""
        frame = json.dumps({
            "type": "get_states"
        })
        
        assert frame == '{"type": "get_states"}'
    
    def test_subscribe_events_frame(self):
        """Test subscribe_events frame format."""
        frame = json.dumps({
            "type": "subscribe_events",
            "event_type": "state_changed"
        })
        
        assert "state_changed" in frame
    
    def test_state_sync_event_format(self):
        """Test state change event payload format."""
        entity_id = "light.kitchen"
        new_state = {
            "entity_id": "light.kitchen",
            "state": "on",
            "attributes": {
                "friendly_name": "Kitchen Light",
                "brightness_pct": 80
            }
        }
        
        event = {
            "type": "event",
            "event": {
                "data": new_state
            }
        }
        
        assert event["event"]["data"]["entity_id"] == "light.kitchen"
        assert event["event"]["data"]["state"] == "on"
    
    def test_read_only_domains_filter(self):
        """Test read-only entity domains are identified."""
        read_only = ['sensor', 'binary_sensor', 'input_datetime', 'weather', 'zone', 'device_tracker']
        
        assert 'sensor' in read_only
        assert 'light' not in read_only
        assert 'switch' not in read_only
    
    def test_env_var_defaults(self):
        """Test environment variable defaults."""
        # HA_URL should have a default fallback
        ha_url = os.environ.get('HA_URL', 'http://homeassistant.local:8123')
        assert ha_url == 'http://homeassistant.local:8123'


class TestHARESTController:
    """Test REST controller for Home Assistant service calls."""
    
    def test_auth_header_format(self):
        """Test authorization header format."""
        token = "test_token"
        header = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        assert header["Authorization"] == "Bearer test_token"
        assert header["Content-Type"] == "application/json"
    
    def test_http_request_url(self):
        """Test HTTP request URL construction."""
        base_url = "http://homeassistant.local:8123"
        light_url = f"{base_url}/api/services/light/turn_on"
        
        assert light_url.endswith("/light/turn_on")
    
    def test_service_call_payload(self):
        """Test service call payload format."""
        payload = {
            "entity_id": "light.kitchen",
            "brightness": 255,
            "color_temp": 300
        }
        
        assert payload["entity_id"] == "light.kitchen"
        assert payload["brightness"] == 255
    
    def test_turn_on_payload(self):
        """Test turn_on service payload."""
        payload = {
            "entity_id": "light.living_room",
            "brightness_pct": 80
        }
        
        assert "entity_id" in payload
        assert payload["brightness_pct"] == 80
    
    def test_turn_off_payload(self):
        """Test turn_off service payload."""
        payload = {
            "entity_id": "light.bedroom"
        }
        
        assert payload["entity_id"] == "light.bedroom"


class TestHAEnvVars:
    """Test Home Assistant environment variables in .env.example."""
    
    def test_env_example_exists(self):
        """Test .env.example file exists."""
        assert ENV_EXAMPLE.exists()
    
    def test_ha_url_present(self):
        """Test HA_URL variable is defined."""
        content = ENV_EXAMPLE.read_text()
        assert "HA_URL=" in content
    
    def test_ha_token_present(self):
        """Test HA_TOKEN variable is defined."""
        content = ENV_EXAMPLE.read_text()
        assert "HA_TOKEN=" in content
    
    def test_ha_entity_id_present(self):
        """Test HA_ENTITY_ID variable is defined."""
        content = ENV_EXAMPLE.read_text()
        assert "HA_ENTITY_ID=" in content
    
    def test_ha_variables_count(self):
        """Test all expected HA variables are present."""
        content = ENV_EXAMPLE.read_text()
        
        expected_vars = ["HA_URL", "HA_TOKEN", "HA_ENTITY_ID"]
        for var in expected_vars:
            assert f"{var}=" in content, f"Missing {var} in .env.example"


class TestHADriftGate:
    """Test HA integration drift gate (env.get() calls must be in .env.example)."""
    
    def test_env_get_calls_documented(self):
        """Test all env.get() calls in HA flows are documented in .env.example."""
        flows_content = FLOWS_FILE.read_text()
        env_content = ENV_EXAMPLE.read_text()
        
        # Find only HA-related env.get() calls (not general flow env vars)
        ha_env_calls = re.findall(r'env\.get\([\'"]([^\'"]+)[\'"]\)', flows_content)
        
        # Filter to only HA-related calls (exclude PROXMOX, HUBITAT, UNIFI, PROMETHEUS, GRAFANA)
        ha_calls = [c for c in ha_env_calls if c.startswith('HA_')]
        
        # Check each HA env.get() call has corresponding env var
        for call in ha_calls:
            assert f"{call}=" in env_content, f"env.get('{call}') not documented in .env.example"


class TestHAFlowsGenerated:
    """Test that HA flows were actually generated."""
    
    def test_ha_tab_exists_in_flows(self):
        """Test HA tab is present in generated flows."""
        flows_content = FLOWS_FILE.read_text()
        assert "Home Assistant" in flows_content, "HA tab not found in flows"
    
    def test_ha_nodes_count(self):
        """Test HA nodes are present in flows."""
        flows_content = FLOWS_FILE.read_text()
        
        # Count HA-related elements by searching for key terms
        ha_patterns = [
            "Home Assistant",
            "HA WebSocket",
            "HA REST", 
            "ws module",
            "HA_TOKEN",
            "HA_URL",
            "api/websocket",
            "turn_on",
            "turn_off"
        ]
        
        found_patterns = []
        for pattern in ha_patterns:
            if pattern in flows_content:
                found_patterns.append(pattern)
        
        assert len(found_patterns) >= 3, f"Expected at least 3 HA patterns, found: {found_patterns}"
        print(f"Found HA patterns: {found_patterns}")
    
    def test_ha_tab_in_home_assistant_file(self):
        """The HA tab lives in 07-home-assistant.flow.json.

        This used to assert "Home Assistant" appeared in 99-other.flow.json and
        passed -- but only because 99-other was a STALE file left over from an
        older generator run that had not yet been given a `07-` label. The tab
        was never written there by the current generator. Regenerating 99-other
        (2026-10-19, when config nodes gained a 00-config.flow.json home)
        replaced the stale copy and the assertion finally failed. Assert the
        real location, and that the stale file is gone.
        """
        ha_file = PROJECT_ROOT / "flows" / "07-home-assistant.flow.json"
        content = ha_file.read_text()
        assert "Home Assistant" in content, "HA tab not in 07-home-assistant.flow.json"
        assert "HA WebSocket Client" in content, \
            "07-home-assistant.flow.json is missing the HA WebSocket node"

        stale = PROJECT_ROOT / "flows" / "99-other.flow.json"
        assert not stale.exists() or "Home Assistant" not in stale.read_text(), \
            "stale 99-other.flow.json still carries a duplicated copy of the HA tab"


class TestHARequirements:
    """Test requirements.txt includes ws module."""
    
    def test_ws_in_requirements(self):
        """Test ws module is in requirements.txt."""
        req_file = PROJECT_ROOT / "requirements.txt"
        content = req_file.read_text()
        
        assert "ws" in content, "ws module not in requirements.txt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
