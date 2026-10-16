"""
Tests for Home Assistant device controls (flows/home_assistant_integration.py)

Covers the dashboard control surface: Hubitat -> HA command mapping, the
native HA service-call shape, and every failure path (timeouts, non-2xx
responses, unknown entities, read-only domains, bad arguments, missing
configuration).  The HTTP layer is fully mocked -- no live Home Assistant
is required (none is reachable from this environment).

Mirrors tests/test_hubitat_device_control.py in structure and strictness.
"""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))

BASE_URL = "http://ha.local:8123"
TOKEN = "test-llat-token"
ENTITY_ID = "light.kitchen"


@pytest.fixture(autouse=True)
def no_module_transport(monkeypatch):
    """Keep the module-level transport hook out of every test."""
    import home_assistant_integration

    monkeypatch.setattr(
        home_assistant_integration, "session", None, raising=False
    )


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """HA_* env vars must not leak between tests (or in from a shell)."""
    for name in ("HA_URL", "HA_TOKEN", "HA_ENTITY_ID"):
        monkeypatch.delenv(name, raising=False)


class FakeResponse:
    """Minimal ``requests.Response`` stand-in (same as the Hubitat suite)."""

    def __init__(self, body, status_code=200):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)
        self._payload = body if isinstance(body, (dict, list)) else None

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)


def make_node(config=None, session=None):
    """Build a HomeAssistantNode wired to a mock transport."""
    from home_assistant_integration import HOME_ASSISTANT_NODE

    config = dict(config or {})
    config.setdefault("url", BASE_URL)
    config.setdefault("token", TOKEN)
    config.setdefault("entityId", ENTITY_ID)
    node = HOME_ASSISTANT_NODE('home-assistant-control', {}, config, None)
    node.session = session if session is not None else Mock()
    return node


def ok_session(session, body=None):
    """Make ``session`` answer 200 with ``body`` (default: a state payload)."""
    session.request.return_value = FakeResponse(
        body or [{"entity_id": ENTITY_ID, "state": "on", "attributes": {}}]
    )
    return session


def failing_session(session, status_code, body=None):
    session.request.return_value = FakeResponse(
        body or {"message": "error"}, status_code=status_code
    )
    return session


class TestHubitatCommandMapping:
    """Legacy Hubitat Maker API commands -> HA service calls."""

    def test_on_maps_to_turn_on(self):
        node = make_node()
        mapped = node.map_hubitat_command("on")
        assert mapped == {
            "domain": "light", "service": "turn_on", "serviceData": {}
        }

    def test_off_maps_to_turn_off(self):
        node = make_node()
        mapped = node.map_hubitat_command("off")
        assert mapped["domain"] == "light"
        assert mapped["service"] == "turn_off"

    def test_toggle_maps_to_toggle(self):
        node = make_node()
        mapped = node.map_hubitat_command("toggle")
        assert mapped["service"] == "toggle"

    def test_set_switch_on_and_off(self):
        node = make_node()
        assert node.map_hubitat_command("setSwitch", "on")["service"] == "turn_on"
        assert node.map_hubitat_command("setSwitch", "off")["service"] == "turn_off"
        assert node.map_hubitat_command(
            "setSwitch", {"state": "on"}
        )["service"] == "turn_on"

    def test_set_switch_rejects_bad_state(self):
        node = make_node()
        with pytest.raises(ValueError, match="'on' or 'off'"):
            node.map_hubitat_command("setSwitch", "sideways")

    def test_set_level_maps_to_brightness_pct(self):
        node = make_node()
        mapped = node.map_hubitat_command("setLevel", 50)
        assert mapped["service"] == "turn_on"
        assert mapped["serviceData"] == {"brightness_pct": 50}

    @pytest.mark.parametrize("level", [-1, 101, "bright", None])
    def test_set_level_rejects_out_of_range(self, level):
        node = make_node()
        with pytest.raises(ValueError):
            node.map_hubitat_command("setLevel", level)

    def test_set_hue_converts_hubitat_scale(self):
        """Hubitat hue is 0-100; HA hs_color hue is 0-360."""
        node = make_node()
        mapped = node.map_hubitat_command("setHue", 50)
        assert mapped["serviceData"]["hs_color"] == [180, 100]

    def test_set_saturation_keeps_hue_zero(self):
        node = make_node()
        mapped = node.map_hubitat_command("setSaturation", 80)
        assert mapped["serviceData"]["hs_color"] == [0, 80]

    def test_set_color_full_hsb(self):
        node = make_node()
        mapped = node.map_hubitat_command(
            "setColor", {"hue": 10, "saturation": 90, "level": 40}
        )
        assert mapped["serviceData"]["hs_color"] == [36, 90]
        assert mapped["serviceData"]["brightness_pct"] == 40

    def test_set_color_requires_hue_and_saturation(self):
        node = make_node()
        with pytest.raises(ValueError, match="hue and saturation"):
            node.map_hubitat_command("setColor", {"hue": 10})

    def test_set_color_rejects_bad_level(self):
        node = make_node()
        with pytest.raises(ValueError, match="level"):
            node.map_hubitat_command(
                "setColor", {"hue": 10, "saturation": 90, "level": 200}
            )

    def test_set_color_temperature(self):
        node = make_node()
        mapped = node.map_hubitat_command("setColorTemperature", 2700)
        assert mapped["serviceData"] == {"kelvin": 2700}

    @pytest.mark.parametrize("kelvin", [999, 10001, "warm", None])
    def test_set_color_temperature_rejects_out_of_range(self, kelvin):
        node = make_node()
        with pytest.raises(ValueError):
            node.map_hubitat_command("setColorTemperature", kelvin)

    def test_set_color_hex_parses_rgb(self):
        node = make_node()
        mapped = node.map_hubitat_command("setColorHex", "#FF0400")
        assert mapped["serviceData"]["rgb_color"] == [255, 4, 0]

    def test_set_color_hex_rejects_bad_value(self):
        node = make_node()
        with pytest.raises(ValueError, match="hex"):
            node.map_hubitat_command("setColorHex", "not-a-colour")

    def test_refresh_maps_to_homeassistant_update_entity(self):
        """`refresh` must land on homeassistant.update_entity -- the
        per-domain `light.update_entity` endpoint does not exist and HA
        would 404 (the defect the prior draft shipped)."""
        node = make_node()
        mapped = node.map_hubitat_command("refresh")
        assert mapped == {
            "domain": "homeassistant", "service": "update_entity",
            "serviceData": {}
        }

    def test_unknown_command_raises(self):
        node = make_node()
        with pytest.raises(ValueError, match="unsupported device command"):
            node.map_hubitat_command("explode")

    def test_missing_entity_raises(self):
        node = make_node({"entityId": None})
        with pytest.raises(ValueError, match="HA_ENTITY_ID"):
            node.map_hubitat_command("on")

    def test_explicit_entity_derives_its_own_domain(self):
        """A legacy action naming its own entity works without a global
        HA_ENTITY_ID (the prior draft ignored the explicit entity)."""
        node = make_node({"entityId": None})
        mapped = node.map_hubitat_command("on", entity_id="switch.fan")
        assert mapped["domain"] == "switch"

    def test_read_only_domain_rejected(self):
        node = make_node({"entityId": "sensor.temperature"})
        with pytest.raises(ValueError, match="read-only"):
            node.map_hubitat_command("on")

    def test_refresh_on_read_only_domain_is_allowed(self):
        """homeassistant.update_entity is valid for sensors too -- it
        forces a re-poll instead of commanding the device."""
        node = make_node({"entityId": "sensor.temperature"})
        mapped = node.map_hubitat_command("refresh")
        assert mapped["domain"] == "homeassistant"
        assert mapped["service"] == "update_entity"


class TestServiceDataValidation:
    """Local validation of service_data before it reaches HA."""

    def test_brightness_pct_in_range(self):
        node = make_node()
        ok_session(node.session)
        result = node.call_service(
            "light", "turn_on", ENTITY_ID, {"brightness_pct": 40}
        )
        assert result.ok
        sent = json.loads(node.session.request.call_args[1]["data"])
        assert sent["brightness_pct"] == 40
        assert sent["entity_id"] == ENTITY_ID

    def test_brightness_pct_out_of_range_rejected_locally(self):
        """NUMERIC_RANGES was declared but never used in the prior draft --
        a 500% brightness would have gone straight to HA."""
        node = make_node()
        result = node.call_service(
            "light", "turn_on", ENTITY_ID, {"brightness_pct": 500}
        )
        assert result.ok is False
        assert result.code == "invalid_argument"
        node.session.request.assert_not_called()

    def test_service_data_may_not_carry_entity_id(self):
        """A stray entity_id in service_data could silently override the
        validated target."""
        node = make_node()
        result = node.call_service(
            "light", "turn_on", ENTITY_ID, {"entity_id": "light.other"}
        )
        assert result.ok is False
        assert result.code == "invalid_argument"
        node.session.request.assert_not_called()

    def test_unsupported_service_data_field_rejected(self):
        node = make_node()
        result = node.call_service(
            "light", "turn_on", ENTITY_ID, {"frobnicate": 1}
        )
        assert result.ok is False
        assert result.code == "invalid_argument"
        assert "frobnicate" in result.error

    def test_hs_color_requires_a_list(self):
        node = make_node()
        result = node.call_service(
            "light", "turn_on", ENTITY_ID, {"hs_color": "red"}
        )
        assert result.ok is False
        assert result.code == "invalid_argument"

    def test_non_mapping_service_data_rejected(self):
        node = make_node()
        result = node.call_service("light", "turn_on", ENTITY_ID, [1, 2, 3])
        assert result.ok is False
        assert result.code == "invalid_argument"


class TestCallService:
    """The REST control path (POST /api/services/<domain>/<service>)."""

    def test_call_service_builds_the_right_request(self):
        node = make_node()
        ok_session(node.session)
        result = node.call_service("light", "turn_on", ENTITY_ID,
                                   {"brightness_pct": 30})

        assert result.ok is True
        method, url = node.session.request.call_args[0][0], \
            node.session.request.call_args[0][1]
        assert method == "POST"
        assert url == f"{BASE_URL}/api/services/light/turn_on"
        headers = node.session.request.call_args[1]["headers"]
        assert headers["Authorization"] == f"Bearer {TOKEN}"
        assert headers["Content-Type"] == "application/json"
        body = json.loads(node.session.request.call_args[1]["data"])
        assert body == {"entity_id": ENTITY_ID, "brightness_pct": 30}

    def test_call_service_success_folds_state_into_cache(self):
        node = make_node()
        node.session.request.return_value = FakeResponse(
            [{"entity_id": ENTITY_ID, "state": "on", "attributes": {}}]
        )
        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok
        assert node.states[ENTITY_ID]["state"] == "on"

    def test_call_service_publishes_on_send(self):
        node = make_node()
        ok_session(node.session)
        node.call_service("light", "turn_off", ENTITY_ID)
        assert node.send.called
        message = node.send.call_args[0][0]
        assert message["topic"] == f"ha/entity/{ENTITY_ID}/command"
        assert message["payload"]["ok"] is True

    def test_domain_defaults_to_entity_prefix(self):
        node = make_node({"entityId": "switch.fan"})
        ok_session(node.session)
        result = node.call_service(None, "turn_on", "switch.fan")
        assert result.ok
        url = node.session.request.call_args[0][1]
        assert url == f"{BASE_URL}/api/services/switch/turn_on"

    def test_homeassistant_domain_accepted_for_any_entity(self):
        node = make_node()
        ok_session(node.session)
        result = node.call_service("homeassistant", "turn_off", "fan.ceiling")
        assert result.ok
        url = node.session.request.call_args[0][1]
        assert url == f"{BASE_URL}/api/services/homeassistant/turn_off"

    def test_missing_entity_id_fails(self):
        node = make_node({"entityId": None})
        result = node.call_service("light", "turn_on")
        assert result.ok is False
        assert result.code == "missing_configuration"
        node.session.request.assert_not_called()

    def test_missing_service_name_fails(self):
        node = make_node()
        result = node.call_service("light", "", ENTITY_ID)
        assert result.ok is False
        assert result.code == "invalid_argument"

    def test_unknown_service_fails(self):
        node = make_node()
        result = node.call_service("light", "frobnicate", ENTITY_ID)
        assert result.ok is False
        assert result.code == "unknown_service"
        node.session.request.assert_not_called()

    def test_read_only_domain_fails(self):
        node = make_node()
        result = node.call_service("sensor", "turn_on", "sensor.temp")
        assert result.ok is False
        assert result.code == "read_only"
        node.session.request.assert_not_called()

    def test_missing_token_fails_without_http(self):
        node = make_node({"token": None})
        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is False
        assert result.code == "missing_configuration"
        assert "token" in result.error
        node.session.request.assert_not_called()


class TestConvenienceCommands:
    """turn_on / turn_off / toggle and the Node-RED naming convention."""

    def test_turn_on(self):
        node = make_node()
        ok_session(node.session)
        result = node.turn_on(ENTITY_ID)
        assert result.ok
        assert node.session.request.call_args[0][1].endswith(
            "/api/services/light/turn_on"
        )

    def test_turn_off(self):
        node = make_node()
        ok_session(node.session)
        result = node.turn_off(ENTITY_ID)
        assert result.ok
        assert node.session.request.call_args[0][1].endswith(
            "/api/services/light/turn_off"
        )

    def test_toggle(self):
        node = make_node()
        ok_session(node.session)
        result = node.toggle(ENTITY_ID)
        assert result.ok
        assert node.session.request.call_args[0][1].endswith(
            "/api/services/light/toggle"
        )

    def test_turn_on_defaults_to_configured_entity(self):
        node = make_node()
        ok_session(node.session)
        result = node.turn_on()
        assert result.ok
        body = json.loads(node.session.request.call_args[1]["data"])
        assert body["entity_id"] == ENTITY_ID


class TestDashboardControlSurface:
    """``controlDevice`` / ``handle_control`` -- the UI entry point."""

    def test_native_service_shape(self):
        node = make_node()
        ok_session(node.session)
        result = node.control_device({
            "entityId": "switch.fan", "domain": "switch",
            "service": "turn_on", "data": {},
        })
        assert result.ok
        assert node.session.request.call_args[0][1].endswith(
            "/api/services/switch/turn_on"
        )

    def test_native_shape_with_snake_case_keys(self):
        node = make_node()
        ok_session(node.session)
        result = node.control_device({
            "entity_id": "switch.fan", "domain": "switch",
            "service": "turn_on", "service_data": {"brightness_pct": 20},
        })
        assert result.ok

    def test_legacy_hubitat_shape(self):
        """Legacy widgets ({deviceId, command, value}) keep working."""
        node = make_node()
        ok_session(node.session)
        result = node.control_device({
            "deviceId": "switch.fan", "command": "on",
        })
        assert result.ok
        assert node.session.request.call_args[0][1].endswith(
            "/api/services/switch/turn_on"
        )

    def test_legacy_set_level(self):
        node = make_node()
        ok_session(node.session)
        result = node.control_device({
            "deviceId": "light.kitchen", "command": "setLevel", "value": 60,
        })
        assert result.ok
        body = json.loads(node.session.request.call_args[1]["data"])
        assert body == {"entity_id": "light.kitchen", "brightness_pct": 60}

    def test_wrapped_node_red_msg(self):
        node = make_node()
        ok_session(node.session)
        result = node.control_device({
            "payload": {"deviceId": "light.kitchen", "command": "off"},
        })
        assert result.ok
        assert node.session.request.call_args[0][1].endswith(
            "/api/services/light/turn_off"
        )

    def test_handle_control_alias(self):
        node = make_node()
        ok_session(node.session)
        result = node.handle_control({
            "payload": {"deviceId": "light.kitchen", "command": "toggle"},
        })
        assert result.ok

    def test_rejects_non_mapping(self):
        node = make_node()
        result = node.control_device("turn the light on")
        assert result.ok is False
        assert result.code == "invalid_payload"

    def test_rejects_missing_command_and_service(self):
        node = make_node()
        result = node.control_device({"deviceId": "light.kitchen"})
        assert result.ok is False
        assert result.code == "unknown_command"

    def test_rejects_unknown_command(self):
        node = make_node()
        result = node.control_device({
            "deviceId": "light.kitchen", "command": "explode",
        })
        assert result.ok is False
        assert result.code == "invalid_argument"
        node.session.request.assert_not_called()

    def test_legacy_command_result_carries_the_command(self):
        """The failure result must name the legacy command, so the UI can
        tell the user what failed."""
        node = make_node()
        result = node.control_device({
            "deviceId": "light.kitchen", "command": "setLevel", "value": "bogus",
        })
        assert result.ok is False
        assert result.command == "setLevel"


class TestFailurePaths:
    """Timeouts, non-2xx responses, unknown entities, transport errors."""

    def test_timeout_returns_structured_failure(self):
        node = make_node()
        node.session.request.side_effect = TimeoutError("timed out")

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is False
        assert result.code == "timeout"
        assert result.error == "timed out"

    def test_socket_timeout_returns_timeout_code(self):
        import socket as socket_module

        node = make_node()
        node.session.request.side_effect = socket_module.timeout("timed out")
        assert node.call_service(
            "light", "turn_on", ENTITY_ID
        ).code == "timeout"

    def test_connection_error(self):
        node = make_node()
        node.session.request.side_effect = ConnectionError("refused")

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is False
        assert result.code == "connection_error"
        assert "unreachable" in result.message

    def test_unexpected_transport_error(self):
        node = make_node()
        node.session.request.side_effect = ValueError("weird")

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is False
        assert result.code == "transport_error"

    def test_401_is_auth_error(self):
        node = make_node()
        failing_session(node.session, 401, {"message": "Unauthorized"})

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is False
        assert result.code == "auth_error"
        assert result.status_code == 401
        assert "HA_TOKEN" in result.message

    def test_403_is_auth_error(self):
        node = make_node()
        failing_session(node.session, 403, {"message": "Forbidden"})

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.code == "auth_error"

    def test_404_service_is_http_error(self):
        node = make_node()
        failing_session(node.session, 404, {"message": "Not found"})

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is False
        assert result.code == "http_error"
        assert result.status_code == 404

    def test_500_is_http_error_with_status(self):
        node = make_node()
        failing_session(node.session, 500, {"error": "boom"})

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.code == "http_error"
        assert "500" in str(result.status_code)

    def test_error_body_message_surfaced(self):
        node = make_node()
        failing_session(node.session, 400, {"error": "service not found on this domain"})

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert "service not found" in result.error

    def test_unknown_entity_404_on_get(self):
        node = make_node()
        failing_session(node.session, 404, {"message": "Entity not found"})

        result = node.get_entity_state("light.missing")
        assert result.ok is False
        assert result.code == "unknown_entity"
        assert result.entity_id == "light.missing"

    def test_non_2xx_without_body_uses_status(self):
        node = make_node()
        node.session.request.return_value = FakeResponse("", status_code=502)

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.code == "http_error"
        assert "502" in result.error


class TestCallbacks:
    """Node-RED style ``callback(err, result)`` plumbing."""

    def test_callback_receives_result_on_success(self):
        node = make_node()
        ok_session(node.session)
        callback = Mock()

        node.call_service("light", "turn_on", ENTITY_ID, callback=callback)

        error, result = callback.call_args[0]
        assert error is None
        assert result.ok is True

    def test_callback_receives_error_on_failure(self):
        node = make_node()
        node.session.request.side_effect = TimeoutError("nope")
        callback = Mock()

        node.call_service("light", "turn_on", ENTITY_ID, callback=callback)

        error, result = callback.call_args[0]
        assert error == "nope"
        assert result.ok is False

    def test_callback_on_validation_failure(self):
        node = make_node()
        callback = Mock()

        node.call_service(
            "light", "turn_on", ENTITY_ID, {"brightness_pct": 999},
            callback=callback,
        )

        error, result = callback.call_args[0]
        assert error is not None
        assert result.code == "invalid_argument"


class TestConfiguration:
    """Credentials come from config/env -- never hard-coded."""

    def test_config_credentials_used(self):
        node = make_node()
        assert node.baseUrl == BASE_URL
        assert node.token == TOKEN
        assert node.entityId == ENTITY_ID

    def test_env_variables_used(self, monkeypatch):
        from home_assistant_integration import HOME_ASSISTANT_NODE

        monkeypatch.setenv("HA_URL", "http://env-ha:8123")
        monkeypatch.setenv("HA_TOKEN", "env-token")
        monkeypatch.setenv("HA_ENTITY_ID", "light.env")

        node = HOME_ASSISTANT_NODE('home-assistant-control', {}, {}, None)
        assert node.baseUrl == "http://env-ha:8123"
        assert node.token == "env-token"
        assert node.entityId == "light.env"

    def test_config_overrides_env(self, monkeypatch):
        from home_assistant_integration import HOME_ASSISTANT_NODE

        monkeypatch.setenv("HA_TOKEN", "env-token")
        node = HOME_ASSISTANT_NODE(
            'home-assistant-control', {}, {"token": "config-token"}, None
        )
        assert node.token == "config-token"

    def test_token_never_appears_in_messages(self):
        node = make_node()
        node.session.request.side_effect = TimeoutError("timed out")

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert TOKEN not in json.dumps(result.to_dict())

    def test_no_transport_configured_is_simulated(self):
        node = make_node()
        node.session = None

        result = node.call_service("light", "turn_on", ENTITY_ID)
        assert result.ok is True
        assert "simulated" in result.message or "no HTTP transport" in result.message

    def test_per_call_session_override(self):
        node = make_node()
        node.session = None
        override = ok_session(Mock())

        result = node.call_service("light", "turn_on", ENTITY_ID, session=override)
        assert result.ok
        override.request.assert_called_once()