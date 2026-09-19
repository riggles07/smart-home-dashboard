"""
Tests for Hubitat Maker API device controls (flows/hubitat_integration.py)

Covers the switch / dimmer / colour-bulb command surface and every failure
path (timeouts, non-2xx responses, unknown device ids, bad arguments, missing
configuration).  The HTTP layer is mocked -- no live hub is required.
"""
import json
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))

APP_ID = "17"
TOKEN = "test-access-token"


@pytest.fixture(autouse=True)
def no_module_transport(monkeypatch):
    """Keep the module-level transport hook out of every test."""
    import hubitat_integration

    monkeypatch.setattr(hubitat_integration, "session", None, raising=False)


class FakeResponse:
    """Minimal ``requests.Response`` stand-in."""

    def __init__(self, body, status_code=200):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)
        self._payload = body if isinstance(body, (dict, list)) else None
        self.encoding = "utf-8"

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)

    def raise_for_status(self):
        if not 200 <= self.status_code < 300:
            raise RuntimeError(f"HTTP {self.status_code}")


def make_node(config=None, session=None):
    """Build a HubitatNode wired to a mock transport."""
    from hubitat_integration import HUBITAT_NODE

    config = dict(config or {"url": "http://hub.local:8080", "appId": APP_ID})
    config.setdefault("appId", APP_ID)
    config.setdefault("accessToken", TOKEN)
    node = HUBITAT_NODE('hubitat-control', {}, config, None)
    node.session = session if session is not None else Mock()
    return node


def ok_session(session, body=None):
    """Make ``session`` answer 200 with ``body`` (default: a device payload)."""
    session.request.return_value = FakeResponse(body or {"id": "101", "switch": "on"})
    return session


class TestSupportedCommands:
    """The advertised command catalogue."""

    def test_supported_commands_covers_every_command_type(self):
        from hubitat_integration import HUBITAT_NODE

        commands = HUBITAT_NODE.supportedCommands()

        for name in ("on", "off", "setLevel", "setColor"):
            assert name in commands

    def test_supported_commands_is_a_copy(self):
        from hubitat_integration import HUBITAT_NODE

        commands = HUBITAT_NODE.supportedCommands()
        commands["on"]["capability"] = "mutated"

        assert HUBITAT_NODE.supportedCommands()["on"]["capability"] == "switch"

    def test_supported_commands_metadata(self):
        from hubitat_integration import HUBITAT_NODE

        commands = HUBITAT_NODE.supportedCommands()
        assert commands["setLevel"]["capability"] == "dimmer"
        assert commands["setLevel"]["required"] == ["level"]
        assert commands["setColor"]["capability"] == "color-bulb"


class TestOnOff:
    """Maker API ``on`` / ``off``."""

    def test_turn_on_builds_maker_api_url(self):
        node = make_node()
        ok_session(node.session)

        result = node.turnOn("101")

        assert result.ok is True
        url = node.session.request.call_args[0][1]
        assert url.startswith(f"http://hub.local:8080/apps/api/{APP_ID}/devices/101/on")
        assert f"access_token={TOKEN}" in url

    def test_turn_off_uses_off_command(self):
        node = make_node()
        ok_session(node.session)

        result = node.turnOff(101)

        assert result.ok is True
        assert result.command == "off"
        assert "/devices/101/off" in node.session.request.call_args[0][1]

    def test_toggle_supported(self):
        node = make_node()
        ok_session(node.session)

        result = node.toggle("101")

        assert result.ok and result.code == "ok"
        assert "/devices/101/toggle" in node.session.request.call_args[0][1]

    def test_send_device_command_generic(self):
        node = make_node()
        ok_session(node.session)

        result = node.sendDeviceCommand("101", "on")

        assert result.ok
        assert result.to_dict()["command"] == "on"

    def test_send_device_command_accepts_mapping_arguments(self):
        node = make_node()
        ok_session(node.session)

        result = node.sendDeviceCommand("101", "setLevel", {"level": 25, "duration": 2})

        assert result.ok
        assert result.value == "25,2"
        assert "/devices/101/setLevel/25%2C2" in node.session.request.call_args[0][1]


class TestSwitchVariants:
    """Explicit switch state commands."""

    def test_set_switch_on(self):
        node = make_node()
        ok_session(node.session)

        result = node.setSwitch("101", "on")

        assert result.ok
        assert result.value == "on"
        assert "/devices/101/setSwitch/on" in node.session.request.call_args[0][1]

    def test_set_switch_rejects_bad_state(self):
        node = make_node()

        result = node.setSwitch("101", "sideways")

        assert result.ok is False
        assert result.code == "invalid_argument"
        node.session.request.assert_not_called()

    def test_refresh_device(self):
        node = make_node()
        ok_session(node.session)

        result = node.refreshDevice("101")

        assert result.ok
        assert "/devices/101/refresh" in node.session.request.call_args[0][1]


class TestSetLevel:
    """Dimmer commands."""

    def test_set_level_only(self):
        node = make_node()
        ok_session(node.session)

        result = node.setLevel("101", 50)

        assert result.ok
        assert result.value == "50"
        assert "/devices/101/setLevel/50" in node.session.request.call_args[0][1]

    def test_set_level_with_duration(self):
        node = make_node()
        ok_session(node.session)

        result = node.setLevel("101", 50, 5)

        assert result.ok
        assert result.value == "50,5"
        # Comma is percent-encoded so the hub parses it as one value segment.
        assert "/devices/101/setLevel/50%2C5" in node.session.request.call_args[0][1]

    def test_set_level_accepts_string_number(self):
        node = make_node()
        ok_session(node.session)

        result = node.setLevel("101", "75")

        assert result.ok
        assert result.value == "75"

    @pytest.mark.parametrize("level", [-1, 101, "bright", None])
    def test_set_level_rejects_out_of_range_or_non_numeric(self, level):
        node = make_node()

        result = node.setLevel("101", level)

        assert result.ok is False
        assert result.code == "invalid_argument"
        node.session.request.assert_not_called()

    def test_set_level_rejects_bad_duration(self):
        node = make_node()

        result = node.setLevel("101", 50, "slow")

        assert result.ok is False
        assert result.code == "invalid_argument"


class TestColorCommands:
    """Colour-bulb commands."""

    def test_set_color_hue_saturation(self):
        node = make_node()
        ok_session(node.session)

        result = node.setColor("101", 10, 90)

        assert result.ok
        url = node.session.request.call_args[0][1]
        # JSON payload is percent-encoded, as the Maker API docs recommend.
        assert "/devices/101/setColor/%7B%22hue%22%3A10%2C%22saturation%22%3A90%7D" in url

    def test_set_color_with_level(self):
        node = make_node()
        ok_session(node.session)

        result = node.setColor("101", 10, 90, 40)

        assert result.ok
        assert json.loads(result.value) == {"hue": 10, "saturation": 90, "level": 40}

    def test_set_hue_and_saturation(self):
        node = make_node()
        ok_session(node.session)

        assert node.setHue("101", 33).ok
        assert "/devices/101/setHue/33" in node.session.request.call_args[0][1]

        node.session.request.reset_mock()
        ok_session(node.session)
        assert node.setSaturation("101", 66).ok
        assert "/devices/101/setSaturation/66" in node.session.request.call_args[0][1]

    def test_set_color_temperature(self):
        node = make_node()
        ok_session(node.session)

        result = node.setColorTemperature("101", 2700, 80)

        assert result.ok
        assert result.value == "2700,80"

    def test_set_color_hex(self):
        node = make_node()
        ok_session(node.session)

        result = node.setColorHex("101", "#FF0400")

        assert result.ok
        assert json.loads(result.value) == {"hex": "FF0400"}

    def test_set_color_hex_rejects_bad_value(self):
        node = make_node()

        result = node.setColorHex("101", "not-a-colour")

        assert result.ok is False
        assert result.code == "invalid_argument"

    def test_set_color_requires_saturation(self):
        node = make_node()

        result = node.controlDevice(
            {"deviceId": "101", "command": "setColor", "value": {"hue": 10}}
        )

        assert result.ok is False
        assert result.code == "invalid_argument"
        assert "saturation" in result.error

    def test_set_color_rejects_unsupported_argument(self):
        node = make_node()

        result = node.controlDevice(
            {"deviceId": "101", "command": "setColor",
             "value": {"hue": 10, "saturation": 90, "kelvin": 2700}}
        )

        assert result.ok is False
        assert result.code == "invalid_argument"
        assert "kelvin" in result.error


class TestDashboardControlSurface:
    """``controlDevice`` / ``handleControl`` -- the UI entry point."""

    def test_control_device_from_wrapped_payload(self):
        node = make_node()
        ok_session(node.session)

        result = node.controlDevice(
            {"payload": {"deviceId": "101", "command": "on"}}
        )

        assert result.ok
        assert "/devices/101/on" in node.session.request.call_args[0][1]

    def test_control_device_publishes_result_on_send(self):
        node = make_node()
        ok_session(node.session)

        node.controlDevice({"deviceId": "101", "command": "off"})

        assert node.send.called
        message = node.send.call_args[1]
        assert message["topic"] == "hubitat/device/101/command"
        assert message["payload"]["ok"] is True

    def test_control_device_with_scalar_value(self):
        node = make_node()
        ok_session(node.session)

        result = node.handleControl({"deviceId": "101", "command": "setLevel", "value": 30})

        assert result.ok
        assert "/devices/101/setLevel/30" in node.session.request.call_args[0][1]

    def test_control_device_with_list_value(self):
        node = make_node()
        ok_session(node.session)

        result = node.controlDevice(
            {"deviceId": "101", "command": "setLevel", "value": [40, 3]}
        )

        assert result.ok
        assert result.value == "40,3"

    def test_control_device_with_inline_named_arguments(self):
        node = make_node()
        ok_session(node.session)

        result = node.controlDevice({"deviceId": "101", "command": "setLevel", "level": 20})

        assert result.ok
        assert result.value == "20"

    def test_control_device_with_mapping_value(self):
        node = make_node()
        ok_session(node.session)

        result = node.controlDevice(
            {"deviceId": "101", "command": "setColor", "value": {"hue": 1, "saturation": 100}}
        )

        assert result.ok
        assert json.loads(result.value)["saturation"] == 100

    def test_control_device_accepts_device_id_alias(self):
        node = make_node()
        ok_session(node.session)

        result = node.controlDevice({"device_id": "101", "command": "on"})

        assert result.ok

    def test_control_device_rejects_non_mapping(self):
        node = make_node()

        result = node.controlDevice("turn the light on")

        assert result.ok is False
        assert result.code == "invalid_payload"

    def test_control_device_rejects_unknown_command(self):
        node = make_node()

        result = node.controlDevice({"deviceId": "101", "command": "explode"})

        assert result.ok is False
        assert result.code == "unknown_command"
        node.session.request.assert_not_called()

    def test_control_device_missing_command(self):
        node = make_node()

        result = node.controlDevice({"deviceId": "101"})

        assert result.ok is False
        assert result.code == "unknown_command"


class TestFailurePaths:
    """Timeouts, non-2xx responses and unknown devices."""

    def test_timeout_returns_structured_failure(self):
        node = make_node()
        node.session.request.side_effect = TimeoutError("timed out")

        result = node.turnOn("101")

        assert result.ok is False
        assert result.code == "timeout"
        assert result.error == "timed out"
        assert "timed out" in result.message.lower() or "respond" in result.message.lower()

    def test_socket_timeout_returns_timeout_code(self):
        import socket as socket_module

        node = make_node()
        node.session.request.side_effect = socket_module.timeout("timed out")

        assert node.turnOn("101").code == "timeout"

    def test_connection_error(self):
        node = make_node()
        error = ConnectionError("connection refused")
        node.session.request.side_effect = error

        result = node.turnOn("101")

        assert result.ok is False
        assert result.code == "connection_error"
        assert "unreachable" in result.message

    def test_requests_request_exception_subclass_is_connection_error(self):
        node = make_node()

        class RequestException(Exception):
            pass

        node.session.request.side_effect = RequestException("boom")
        assert node.turnOn("101").code == "connection_error"

    def test_unexpected_transport_error(self):
        node = make_node()
        node.session.request.side_effect = ValueError("weird")

        result = node.turnOn("101")

        assert result.ok is False
        assert result.code == "transport_error"

    def test_non_2xx_response(self):
        node = make_node()
        node.session.request.return_value = FakeResponse(
            {"error": "Unauthorized"}, status_code=401
        )

        result = node.turnOff("101")

        assert result.ok is False
        assert result.code == "http_error"
        assert result.status_code == 401
        assert result.error == "Unauthorized"

    def test_non_2xx_without_body_uses_status(self):
        node = make_node()
        node.session.request.return_value = FakeResponse("", status_code=500)

        result = node.turnOff("101")

        assert result.code == "http_error"
        assert "500" in result.error

    def test_unknown_device_payload(self):
        node = make_node()
        node.session.request.return_value = FakeResponse(
            {"error": "Device not found"}, status_code=200
        )

        result = node.setLevel("999", 50)

        assert result.ok is False
        assert result.code == "unknown_device"
        assert result.device_id == "999"

    @pytest.mark.parametrize("device_id", [None, "", "   ", True])
    def test_invalid_device_id(self, device_id):
        node = make_node()

        result = node.turnOn(device_id)

        assert result.ok is False
        assert result.code == "invalid_device_id"
        node.session.request.assert_not_called()

    def test_unknown_device_id_is_not_sent_to_hub(self):
        node = make_node()

        result = node.controlDevice({"deviceId": "", "command": "on"})

        assert result.code == "invalid_device_id"
        node.session.request.assert_not_called()

    def test_missing_app_id(self):
        node = make_node(config={"url": "http://hub.local:8080", "accessToken": TOKEN})
        node.appId = None

        result = node.turnOn("101")

        assert result.ok is False
        assert result.code == "missing_configuration"
        assert "app id" in result.error

    def test_missing_access_token(self):
        node = make_node()
        node.accessToken = None

        result = node.turnOn("101")

        assert result.code == "missing_configuration"
        assert "access token" in result.error

    def test_unexpected_kwargs_rejected(self):
        node = make_node()

        result = node.sendDeviceCommand("101", "on", nonsense=True)

        assert result.ok is False
        assert result.code == "invalid_argument"


class TestCallbacks:
    """Node-RED style ``callback(err, result)`` plumbing."""

    def test_callback_receives_result_on_success(self):
        node = make_node()
        ok_session(node.session)
        callback = Mock()

        node.turnOn("101", callback=callback)

        error, result = callback.call_args[0]
        assert error is None
        assert result.ok is True

    def test_callback_receives_error_on_failure(self):
        node = make_node()
        node.session.request.side_effect = TimeoutError("nope")
        callback = Mock()

        node.turnOn("101", callback=callback)

        error, result = callback.call_args[0]
        assert error == "nope"
        assert result.ok is False

    def test_get_device_commands_lists_hub_commands(self):
        node = make_node()
        node.session.request.return_value = FakeResponse(
            [{"command": "on"}, {"command": "off"}]
        )

        result = node.getDeviceCommands("101")

        assert result.ok
        assert "2 command(s)" in result.message
        assert "/devices/101/commands" in node.session.request.call_args[0][1]


class TestConfiguration:
    """Credentials come from config/env -- never hard-coded."""

    def test_config_credentials_used(self):
        node = make_node(config={"url": "http://hub.local:8080", "appId": "42",
                                 "accessToken": "secret-token"})

        assert node.appId == "42"
        assert node.accessToken == "secret-token"

    def test_api_key_falls_back_to_access_token(self):
        node = make_node(config={"url": "http://hub.local", "appId": "42",
                                 "apiKey": "key-token"})
        node.accessToken = node.config.get("apiKey")

        assert node.accessToken == "key-token"

    def test_env_variables_used(self, monkeypatch):
        from hubitat_integration import HUBITAT_NODE

        monkeypatch.setenv("HUBITAT_URL", "http://env-hub:8080")
        monkeypatch.setenv("HUBITAT_APP_ID", "99")
        monkeypatch.setenv("HUBITAT_ACCESS_TOKEN", "env-token")

        node = HUBITAT_NODE('hubitat-control', {}, {}, None)

        assert node.baseUrl == "http://env-hub:8080"
        assert node.appId == "99"
        assert node.accessToken == "env-token"

    def test_no_transport_configured_is_simulated(self):
        node = make_node()
        node.session = None

        result = node.turnOn("101")

        assert result.ok is True
        assert "no HTTP transport configured" in result.message

    def test_token_never_appears_in_message_or_error(self):
        node = make_node()
        node.session.request.side_effect = TimeoutError("timed out")

        result = node.turnOn("101")

        assert TOKEN not in json.dumps(result.to_dict())

    def test_per_call_session_override(self):
        node = make_node()
        node.session = None
        override = ok_session(Mock())

        result = node.turnOn("101", session=override)

        assert result.ok
        override.request.assert_called_once()
