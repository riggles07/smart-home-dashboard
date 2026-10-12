"""
Tests for home-assistant-integration.js (flows/home_assistant_integration.py)

Mirror-level coverage: the WebSocket auth sequence, state sync, entity
mapping, and the error/failure paths.  The protocol layer is exercised
against a protocol-faithful local mock -- the exact
``auth_required`` / ``auth`` / ``auth_ok`` frame sequence the HA
WebSocket API uses, a ``subscribe_events`` subscription, and a
``call_service`` round-trip.  No live Home Assistant is required (none is
reachable from this environment; the mock asserts the real frames).
"""
import json
import sys
from pathlib import Path

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


def make_node(config=None):
    """Build a HomeAssistantNode with test credentials."""
    from home_assistant_integration import HOME_ASSISTANT_NODE

    config = dict(config or {})
    config.setdefault("url", BASE_URL)
    config.setdefault("token", TOKEN)
    config.setdefault("entityId", ENTITY_ID)
    return HOME_ASSISTANT_NODE('home-assistant-control', {}, config, None)


class FakeWebSocketServer:
    """Protocol-faithful mock of the HA WebSocket API server side.

    Implements the real handshake (developers.home-assistant.io/docs/api/websocket):

        server -> {type: 'auth_required'}
        client -> {type: 'auth', access_token: <LLAT>}
        server -> {type: 'auth_ok'} (or {type: 'auth_invalid'})

    then answers the command phase: ``get_states``, ``subscribe_events``
    and ``call_service`` all get a ``result`` frame, and a subscribed
    ``state_changed`` event is delivered as an ``event`` frame.
    """

    def __init__(self, entities=(), auth_token=TOKEN):
        self.auth_token = auth_token
        self.entities = list(entities)
        self.received = []          # every client frame, in order
        self.subscribed_events = []
        self.authenticated = False
        self.rejected = False

    def server_opening_frames(self):
        """What the real server sends on connect."""
        return [{"type": "auth_required", "ha_version": "2026.9.0"}]

    def accept(self, frame):
        """Process one client frame and return the server's reply frames."""
        self.received.append(frame)
        if not self.authenticated and not self.rejected:
            if frame.get("type") != "auth":
                # Real HA closes the socket on a non-auth first frame.
                raise AssertionError(
                    f"first client frame must be 'auth', got {frame.get('type')!r}"
                )
            if frame.get("access_token") == self.auth_token:
                self.authenticated = True
                return [{"type": "auth_ok", "ha_version": "2026.9.0"}]
            self.rejected = True
            return [{"type": "auth_invalid",
                     "message": "Invalid access token or short-lived token not authorized"}]
        # Command phase
        if frame.get("type") == "get_states":
            return [{"id": frame["id"], "type": "result", "success": True,
                     "result": self.entities}]
        if frame.get("type") == "subscribe_events":
            self.subscribed_events.append(frame.get("event_type"))
            return [{"id": frame["id"], "type": "result", "success": True,
                     "result": None}]
        if frame.get("type") == "call_service":
            return [{"id": frame["id"], "type": "result", "success": True,
                     "result": [{"entity_id": frame["target"]["entity_id"],
                                 "state": "on", "attributes": {}}]}]
        raise AssertionError(f"unexpected frame {frame!r}")


def drive_handshake(node, server):
    """Run the node's dispatcher against the mock until authenticated.

    Returns the full transcript of client frames sent (server.received is
    the same list; this asserts the node never sends garbage frames).
    """
    for frame in server.server_opening_frames():
        outbound = node.handle_server_message(frame)
        for message in outbound:
            for reply in server.accept(message):
                for second_pass in node.handle_server_message(reply):
                    server.accept(second_pass)
    return server.received


# ---------------------------------------------------------------------------
# WebSocket handshake (auth_required -> auth -> auth_ok)
# ---------------------------------------------------------------------------

class TestWebSocketHandshake:
    """The LLAT auth flow, frame by frame."""

    def test_auth_message_carries_the_llat(self):
        node = make_node()
        assert node.build_auth_message() == {
            "type": "auth", "access_token": TOKEN
        }

    def test_auth_requires_a_token(self):
        node = make_node({"token": None})
        with pytest.raises(ValueError, match="token"):
            node.build_auth_message()

    def test_handshake_sends_auth_then_get_states_and_subscribe(self):
        """auth_required -> auth -> auth_ok -> get_states + subscribe_events."""
        node = make_node()
        server = FakeWebSocketServer(entities=[
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}},
        ])
        frames = drive_handshake(node, server)

        assert frames[0]["type"] == "auth"
        assert frames[0]["access_token"] == TOKEN
        assert frames[1]["type"] == "get_states"
        assert frames[2]["type"] == "subscribe_events"
        assert frames[2]["event_type"] == "state_changed"
        assert server.authenticated is True

    def test_command_ids_are_monotonic(self):
        """The WS protocol requires unique, monotonic command ids."""
        node = make_node()
        ids = [
            node.build_get_states_command()["id"],
            node.build_subscribe_events_command()["id"],
            node.build_call_service_command("light", "turn_on", ENTITY_ID)["id"],
        ]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)

    def test_websocket_url_derives_ws_scheme(self):
        node = make_node()
        assert node.websocket_url() == "ws://ha.local:8123/api/websocket"

    def test_websocket_url_https_becomes_wss(self):
        node = make_node({"url": "https://ha.local:8123"})
        assert node.websocket_url() == "wss://ha.local:8123/api/websocket"

    def test_websocket_url_requires_base_url(self):
        node = make_node()
        node.baseUrl = None
        with pytest.raises(ValueError, match="URL"):
            node.websocket_url()

    def test_auth_invalid_sets_red_status(self):
        """A bad token surfaces as a red node status, not a crash."""
        node = make_node({"token": "wrong-token"})
        server = FakeWebSocketServer(auth_token=TOKEN)

        replies = []
        for frame in server.server_opening_frames():
            for message in node.handle_server_message(frame):
                # Feed the server's reply back through the node, like a
                # real socket client would.
                for reply in server.accept(message):
                    replies.append(reply)
                    node.handle_server_message(reply)

        assert replies[0]["type"] == "auth_invalid"
        assert node.status.called
        status_args = node.status.call_args[0][0]
        assert status_args["fill"] == "red"
        assert "HA_TOKEN" in status_args["text"]

    def test_call_service_frame_has_required_service_key(self):
        """A frame without `service` is rejected by real HA with
        "required key not provided @ data['service']" -- this is the
        defect the prior draft shipped."""
        node = make_node()
        frame = node.build_call_service_command(
            "light", "turn_on", ENTITY_ID, {"brightness_pct": 50}
        )
        assert frame["type"] == "call_service"
        assert frame["domain"] == "light"
        assert frame["service"] == "turn_on"
        assert frame["target"] == {"entity_id": ENTITY_ID}
        assert frame["service_data"] == {"brightness_pct": 50}

    def test_call_service_frame_omits_empty_service_data(self):
        node = make_node()
        frame = node.build_call_service_command("switch", "turn_on", "switch.fan")
        assert "service_data" not in frame


# ---------------------------------------------------------------------------
# State sync (get_states snapshot + state_changed events)
# ---------------------------------------------------------------------------

class TestStateSync:
    """The HA -> UI half of the bidirectional state sync."""

    def test_get_states_result_fills_the_cache(self):
        node = make_node()
        node.handle_server_message({
            "type": "result", "id": 1, "success": True,
            "result": [
                {"entity_id": "light.kitchen", "state": "on",
                 "attributes": {"brightness": 128}},
                {"entity_id": "switch.fan", "state": "off", "attributes": {}},
            ],
        })
        assert set(node.states) == {"light.kitchen", "switch.fan"}
        assert node.states["light.kitchen"]["attributes"]["brightness"] == 128

    def test_get_states_publishes_entity_count(self):
        node = make_node()
        node.handle_server_message({
            "type": "result", "id": 1, "success": True,
            "result": [{"entity_id": "light.kitchen", "state": "on",
                        "attributes": {}}],
        })
        assert node.send.called
        message = node.send.call_args[0][0]
        assert message["topic"] == "ha/state_count"
        assert message["payload"] == 1

    def test_state_changed_event_updates_cache_and_publishes(self):
        node = make_node()
        node.handle_server_message({
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": "light.kitchen",
                    "new_state": {"entity_id": "light.kitchen", "state": "off",
                                  "attributes": {"brightness": 0}},
                },
            },
        })
        assert node.states["light.kitchen"]["state"] == "off"
        message = node.send.call_args[0][0]
        assert message["topic"] == "ha/entity/light.kitchen/state"
        assert message["payload"]["isOn"] is False

    def test_state_changed_without_new_state_is_ignored(self):
        """HA omits new_state when an entity is removed -- must not crash."""
        node = make_node()
        result = node.handle_state_event(
            {"data": {"entity_id": "light.gone", "new_state": None}}
        )
        assert result is None
        assert "light.gone" not in node.states

    def test_failed_result_frame_sets_red_status(self):
        """A rejected command frame must not be dropped silently."""
        node = make_node()
        node.handle_server_message({
            "type": "result", "id": 7, "success": False,
            "error": {"code": "unknown_command", "message": "Unknown command"},
        })
        assert node.status.called
        assert "failed" in node.status.call_args[0][0]["text"]

    def test_update_entity_state_publishes_cached_entity(self):
        node = make_node()
        node.states[ENTITY_ID] = {"entity_id": ENTITY_ID, "state": "on",
                                  "attributes": {}}
        node.update_entity_state(ENTITY_ID)
        assert node.send.called
        assert node.send.call_args[0][0]["topic"] == "ha/entity/light.kitchen/state"

    def test_update_entity_state_unknown_entity_publishes_nothing(self):
        node = make_node()
        assert node.update_entity_state("light.nope") is None
        assert node.send.called is False


# ---------------------------------------------------------------------------
# State normalisation / entity mapping
# ---------------------------------------------------------------------------

class TestNormalizeState:
    """HA state objects -> the shape dashboard widgets consume."""

    def test_brightness_255_scale_converted_to_pct(self):
        """HA stores brightness as 0-255; the dashboard wants 0-100."""
        from home_assistant_integration import HomeAssistantNode

        normalized = HomeAssistantNode.normalize_state({
            "entity_id": "light.kitchen", "state": "on",
            "attributes": {"brightness": 128, "friendly_name": "Kitchen"},
        })
        assert normalized["brightnessPct"] == round((128 / 255) * 100)
        assert normalized["friendlyName"] == "Kitchen"
        assert normalized["isOn"] is True
        assert normalized["domain"] == "light"

    def test_brightness_pct_attribute_wins(self):
        from home_assistant_integration import HomeAssistantNode

        normalized = HomeAssistantNode.normalize_state({
            "entity_id": "light.kitchen", "state": "on",
            "attributes": {"brightness_pct": 42, "brightness": 255},
        })
        assert normalized["brightnessPct"] == 42

    def test_switch_state_without_brightness(self):
        from home_assistant_integration import HomeAssistantNode

        normalized = HomeAssistantNode.normalize_state({
            "entity_id": "switch.fan", "state": "off", "attributes": {},
        })
        assert normalized["brightnessPct"] is None
        assert normalized["isOn"] is False

    def test_state_without_entity_id_returns_none(self):
        from home_assistant_integration import HomeAssistantNode

        assert HomeAssistantNode.normalize_state({"state": "on"}) is None
        assert HomeAssistantNode.normalize_state(None) is None


class TestEntityMapping:
    """Hubitat capability -> HA domain mapping."""

    def test_capability_domain_table(self):
        from home_assistant_integration import HomeAssistantNode

        assert HomeAssistantNode.map_capability_domain("switch") == "switch"
        assert HomeAssistantNode.map_capability_domain("dimmer") == "light"
        assert HomeAssistantNode.map_capability_domain("color-bulb") == "light"
        assert HomeAssistantNode.map_capability_domain("sensor") == "sensor"

    def test_unknown_capability_maps_to_none(self):
        from home_assistant_integration import HomeAssistantNode

        assert HomeAssistantNode.map_capability_domain("flux-capacitor") is None

    def test_supported_services_catalogue_is_a_copy(self):
        from home_assistant_integration import (
            SUPPORTED_SERVICES,
            HomeAssistantNode,
        )

        catalogue = HomeAssistantNode.supported_services()
        catalogue["light.turn_on"]["data"] = ["mutated"]
        assert SUPPORTED_SERVICES["light.turn_on"]["data"] != ["mutated"]

    def test_supported_services_cover_the_required_services(self):
        from home_assistant_integration import HomeAssistantNode

        services = HomeAssistantNode.supported_services()
        for key in ("light.turn_on", "light.turn_off", "switch.turn_on",
                    "switch.turn_off", "switch.toggle", "light.toggle"):
            assert key in services, f"{key} missing from the catalogue"


# ---------------------------------------------------------------------------
# Configuration / error paths
# ---------------------------------------------------------------------------

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

    def test_default_url_when_nothing_configured(self, monkeypatch):
        from home_assistant_integration import DEFAULT_BASE_URL, HOME_ASSISTANT_NODE

        node = HOME_ASSISTANT_NODE('home-assistant-control', {}, {}, None)
        assert node.baseUrl == DEFAULT_BASE_URL

    def test_rest_url_requires_token(self):
        node = make_node({"token": None})
        with pytest.raises(ValueError, match="token"):
            node.rest_url("states")

    def test_rest_url_joins_paths(self):
        node = make_node()
        assert node.rest_url("states") == f"{BASE_URL}/api/states"
        assert node.rest_url("/services/light/turn_on") == \
            f"{BASE_URL}/api/services/light/turn_on"

    def test_token_never_appears_in_result_payload(self):
        """The LLAT must never leak into a result or published message."""
        node = make_node()
        node.session = _ok_session(
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}}
        )
        result = node.get_entity_state("light.kitchen")
        assert result["entity_id"] == "light.kitchen"
        assert TOKEN not in json.dumps(result)
        if node.send.called:
            assert TOKEN not in json.dumps(node.send.call_args[0][0])


class TestSubscribeEvents:
    """The subscribe_events command the flow sends after auth_ok."""

    def test_subscribe_defaults_to_state_changed(self):
        node = make_node()
        command = node.build_subscribe_events_command()
        assert command["type"] == "subscribe_events"
        assert command["event_type"] == "state_changed"

    def test_subscribe_explicit_event_type(self):
        node = make_node()
        command = node.build_subscribe_events_command("zha_event")
        assert command["event_type"] == "zha_event"


class TestGetStatesRest:
    """REST twin of the WS get_states."""

    def test_get_states_missing_token_fails_cleanly(self):
        node = make_node({"token": None})
        result = node.get_states()
        assert result.ok is False
        assert result.code == "missing_configuration"
        assert "token" in result.error

    def test_get_entity_state_404_maps_to_unknown_entity(self):
        node = make_node()
        node.session = _failing_session(status_code=404, body={"message": "Entity not found"})
        result = node.get_entity_state("light.missing")
        assert result.ok is False
        assert result.code == "unknown_entity"
        assert result.entity_id == "light.missing"
        assert result.status_code == 404

    def test_get_entity_state_caches_the_response(self):
        node = make_node()
        node.session = _ok_session([
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}}
        ])
        # get_entity_state wants a single state object, not a list
        node.session.request.return_value = _FakeResponse(
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}}
        )
        result = node.get_entity_state("light.kitchen")
        assert result["entity_id"] == "light.kitchen"
        assert node.states["light.kitchen"]["state"] == "on"


class TestRefreshStates:
    """Periodic refresh publishes the full state list."""

    def test_refresh_states_publishes_list_on_success(self):
        node = make_node()
        node.session = _ok_session([
            {"entity_id": "light.kitchen", "state": "on", "attributes": {}}
        ])
        node.refresh_states()
        assert node.send.called
        message = node.send.call_args[0][0]
        assert message["topic"] == "ha/states"
        assert message["payload"][0]["entity_id"] == "light.kitchen"

    def test_refresh_states_silent_on_failure(self):
        node = make_node()
        node.session = _failing_session(status_code=500, body={"error": "boom"})
        node.refresh_states()
        # The error is swallowed (the interval handler must not throw);
        # the failure is visible on the node status instead.
        assert node.send.called is False


# ---------------------------------------------------------------------------
# Transport helpers for the REST twin
# ---------------------------------------------------------------------------

class _FakeResponse:
    """Minimal ``requests.Response`` stand-in (same shape as the Hubitat suite)."""

    def __init__(self, body, status_code=200):
        self.status_code = status_code
        self.text = body if isinstance(body, str) else json.dumps(body)
        self._payload = body if isinstance(body, (dict, list)) else None

    def json(self):
        if self._payload is not None:
            return self._payload
        return json.loads(self.text)


def _ok_session(body):
    from unittest.mock import Mock

    session = Mock()
    session.request.return_value = _FakeResponse(body)
    return session


def _failing_session(status_code, body):
    from unittest.mock import Mock

    session = Mock()
    session.request.return_value = _FakeResponse(body, status_code=status_code)
    return session