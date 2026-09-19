"""Tests for the Hubitat automation triggers (Rule Machine endpoint triggers).

Every test mocks the HTTP transport -- no live hub is required.

Real API shape exercised here (see ``docs2.hubitat.com/en/apps/rule-machine``)::

    GET|POST /apps/api/<app_id>/trigger/getRuleList?access_token=<token>
    GET|POST /apps/api/<app_id>/trigger/<action>=<rule ids>?access_token=<token>
"""

import logging
import socket
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add flows to path (mirrors the other test modules).
sys.path.insert(0, str(Path(__file__).parent.parent / "flows"))
sys.path.insert(0, str(Path(__file__).parent))

from fake_hub import FakeResponse, FakeSession, TimeoutSession, UnreachableSession  # noqa: E402

APP_ID = "10249"
TOKEN = "00000000-1111-2222-3333-444444444444"
HUB = "http://192.0.2.10"

# The documented getRuleList shape: {"<rule app id>": "<rule name>"}.
RULE_LIST = {"943": "Good Morning", "956": "Away Mode", "10217": "Movie Night"}


def make_node(config=None, **overrides):
    """Build a HubitatNode wired for the Rule Machine endpoint."""
    from flows import hubitat_integration

    base = {"url": HUB, "appId": APP_ID, "accessToken": TOKEN}
    base.update(config or {})
    return hubitat_integration.HUBITAT_NODE("hubitat-control", {}, base, None), hubitat_integration


class TestAutomationListing:
    """Listing the automations the dashboard can present."""

    def test_get_automations_success(self):
        """A getRuleList response is normalised into id/name pairs."""
        node, hub = make_node()
        session = FakeSession(FakeResponse(200, RULE_LIST))
        node.send = Mock()

        result = node.getAutomations(session=session)

        assert result.ok is True
        assert result.code == "ok"
        assert sorted(a["id"] for a in result.automations) == ["10217", "943", "956"]
        assert {"id": "943", "name": "Good Morning"} in result.automations

    def test_get_automations_calls_rul_list_endpoint(self):
        """The request hits /apps/api/<appId>/trigger/getRuleList with the token."""
        node, hub = make_node()
        session = FakeSession(FakeResponse(200, RULE_LIST))

        node.getAutomations(session=session)

        assert session.call_count == 1
        call = session.last_call
        assert call["method"] == "GET"
        assert f"/apps/api/{APP_ID}/trigger/getRuleList" in call["url"]
        assert f"access_token={TOKEN}" in call["url"]
        assert call["timeout"] == hub.DEFAULT_TIMEOUT

    def test_get_automations_publishes_to_dashboard(self):
        """The list is sent on the automation topic for the UI to render."""
        node, hub = make_node()
        node.getAutomations(session=FakeSession(FakeResponse(200, RULE_LIST)))

        assert node.send.called
        payload = node.send.call_args[1]["payload"]
        assert node.send.call_args[1]["topic"] == hub.AUTOMATION_TOPIC
        assert payload["ok"] is True
        assert len(payload["automations"]) == 3

    def test_get_automations_accepts_list_shaped_payload(self):
        """A list-of-objects payload (non-documented variant) still parses."""
        node, hub = make_node()
        body = [{"id": "1", "name": "Sunrise"}, {"id": "2", "name": "Sunset"}]

        result = node.getAutomations(session=FakeSession(FakeResponse(200, body)))

        assert result.ok is True
        assert result.automations == [
            {"id": "1", "name": "Sunrise"},
            {"id": "2", "name": "Sunset"},
        ]

    def test_get_automations_caches_until_refresh(self):
        """A second call reuses the cache; refresh=True re-fetches."""
        node, hub = make_node()
        session = FakeSession(FakeResponse(200, RULE_LIST))

        node.getAutomations(session=session)
        node.getAutomations(session=session)
        assert session.call_count == 1

        node.getAutomations(session=session, refresh=True)
        assert session.call_count == 2

    def test_get_automations_empty_list_is_ok(self):
        """An empty rule list is a valid, successful result."""
        node, hub = make_node()

        result = node.getAutomations(session=FakeSession(FakeResponse(200, {})))

        assert result.ok is True
        assert result.automations == []

    def test_handle_automation_list_dashboard_entry_point(self):
        """The dashboard entry point lists automations and honours refresh."""
        node, hub = make_node()
        session = FakeSession(FakeResponse(200, RULE_LIST))

        result = node.handleAutomationList({"payload": {}}, session=session)

        assert result.ok is True
        assert len(result.automations) == 3

    def test_list_automations_alias(self):
        """listAutomations is the dashboard-facing alias of getAutomations."""
        node, hub = make_node()

        result = node.listAutomations(session=FakeSession(FakeResponse(200, RULE_LIST)))

        assert result.ok is True
        assert len(result.automations) == 3


class TestAutomationTriggering:
    """Triggering a known automation."""

    def test_trigger_success(self):
        """A successful trigger builds the documented endpoint and reports ok."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {"status": "ok"}))
        node.send = Mock()

        result = node.triggerAutomation("943", session=session)

        assert result.ok is True
        assert result.code == "ok"
        assert result.automation_id == "943"
        assert result.automation_name == "Good Morning"
        assert result.action == hub.DEFAULT_TRIGGER_ACTION

    def test_trigger_url_matches_rule_machine_format(self):
        """URL is /apps/api/<appId>/trigger/runRuleAct=<rule id>?access_token=..."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        node.triggerAutomation("943", session=session)

        url = session.last_call["url"]
        assert url == (
            f"{HUB}/apps/api/{APP_ID}/trigger/runRuleAct=943?access_token={TOKEN}"
        )
        assert session.last_call["method"] == "POST"

    def test_trigger_resolves_by_name(self):
        """A rule name from the list resolves to its app id."""
        node, hub = make_node()
        node.automations = [{"id": "956", "name": "Away Mode"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        result = node.triggerAutomation("Away Mode", session=session)

        assert result.ok is True
        assert result.automation_id == "956"
        assert "runRuleAct=956" in session.last_call["url"]

    def test_trigger_fetches_list_when_cache_cold(self):
        """With no cached list the node lists first, then triggers."""
        node, hub = make_node()
        session = FakeSession([
            FakeResponse(200, RULE_LIST),
            FakeResponse(200, {"status": "ok"}),
        ])

        result = node.triggerAutomation("943", session=session)

        assert result.ok is True
        assert session.call_count == 2
        assert "getRuleList" in session.calls[0]["url"]
        assert "runRuleAct=943" in session.calls[1]["url"]

    def test_trigger_stop_action(self):
        """stopRuleAct is passed through for stopping a running rule."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        result = node.triggerAutomation("943", action="stopRuleAct", session=session)

        assert result.action == "stopRuleAct"
        assert "trigger/stopRuleAct=943" in session.last_call["url"]

    def test_trigger_with_value_form(self):
        """A value sets the rule's %value% instead of naming an action."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        result = node.triggerAutomation("943", value="myValue", session=session)

        assert result.ok is True
        assert result.action is None
        assert f"trigger/myValue?access_token={TOKEN}" in session.last_call["url"]

    def test_trigger_method_override(self):
        """Rule Machine accepts GET as well as POST."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        node.triggerAutomation("943", session=session, method="GET")

        assert session.last_call["method"] == "GET"

    def test_trigger_config_method(self):
        """The configured trigger method is the default for calls."""
        node, hub = make_node({"triggerMethod": "get"})
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        node.triggerAutomation("943", session=session)

        assert session.last_call["method"] == "GET"

    def test_trigger_publishes_result_to_dashboard(self):
        """The trigger result reaches the dashboard with the resolved name."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        node.send = Mock()

        node.triggerAutomation("943", session=FakeSession(FakeResponse(200, {})))

        assert node.send.called
        payload = node.send.call_args[1]["payload"]
        assert node.send.call_args[1]["topic"] == hub.automation_result_topic("943")
        assert payload["ok"] is True
        assert payload["automationName"] == "Good Morning"

    def test_trigger_callback_receives_result(self):
        """The callback gets (None, result) on success."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        seen = []

        result = node.triggerAutomation(
            "943", lambda err, res: seen.append((err, res)),
            session=FakeSession(FakeResponse(200, {})),
        )

        assert seen == [(None, result)]

    def test_handle_automation_trigger_dashboard_entry_point(self):
        """The Node-RED style payload maps onto a trigger."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        result = node.handleAutomationTrigger(
            {"payload": {"automationId": "943"}}, session=session
        )

        assert result.ok is True
        assert "runRuleAct=943" in session.last_call["url"]

    def test_handle_automation_trigger_accepts_bare_id(self):
        """A bare id (no envelope) also works."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))

        result = node.handleAutomationTrigger("943", session=session)

        assert result.ok is True

    def test_trigger_optimistic_mode_passes_unknown_id(self):
        """resolveAutomations=False sends unknown ids straight to the hub."""
        node, hub = make_node({"resolveAutomations": False})
        node._automations_resolved = True
        session = FakeSession([
            FakeResponse(200, RULE_LIST),
            FakeResponse(200, {"status": "ok"}),
        ])

        result = node.triggerAutomation("9999", session=session)

        assert result.ok is True
        assert "runRuleAct=9999" in session.last_call["url"]


class TestAutomationFailures:
    """Failure paths: unknown id, unreachable hub, auth, malformed payloads."""

    def test_unknown_automation_id(self):
        """An id absent from the rule list is rejected without an HTTP call."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(200, {}))
        node.send = Mock()

        result = node.triggerAutomation("does-not-exist", session=session)

        assert result.ok is False
        assert result.code == hub.ERROR_UNKNOWN_AUTOMATION
        assert session.call_count == 0
        assert result.automation_id == "does-not-exist"

    def test_unknown_automation_id_is_published_and_callback_fires(self):
        """The failure is surfaced to the dashboard and the callback."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        node.send = Mock()
        seen = []

        node.triggerAutomation(
            "nope", lambda err, res: seen.append((err, res)),
            session=FakeSession(FakeResponse(200, {})),
        )

        assert node.send.call_args[1]["payload"]["code"] == hub.ERROR_UNKNOWN_AUTOMATION
        assert seen[0][0] is not None
        assert seen[0][1].ok is False

    def test_empty_automation_id(self):
        """A missing id is reported as an unknown automation."""
        node, hub = make_node()
        node.send = Mock()

        result = node.triggerAutomation(None)

        assert result.ok is False
        assert result.code == hub.ERROR_UNKNOWN_AUTOMATION

    def test_auth_failure_is_reported(self):
        """HTTP 401/403 map to auth_failure with actionable guidance."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(401, text="Unauthorized"))

        result = node.triggerAutomation("943", session=session)

        assert result.ok is False
        assert result.code == hub.ERROR_AUTH_FAILURE
        assert result.status_code == 401
        assert "access token" in result.message

    def test_auth_failure_on_list(self):
        """Listing with a bad token fails cleanly rather than raising."""
        node, hub = make_node()

        result = node.getAutomations(session=FakeSession(FakeResponse(403, text="Forbidden")))

        assert result.ok is False
        assert result.code == hub.ERROR_AUTH_FAILURE
        assert result.status_code == 403

    def test_hub_unreachable(self):
        """A connection error is reported as hub_unreachable."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True

        result = node.triggerAutomation("943", session=UnreachableSession())

        assert result.ok is False
        assert result.code == hub.ERROR_HUB_UNREACHABLE
        assert "unreachable" in result.message

    def test_hub_timeout(self):
        """A timeout is reported with the timeout code."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True

        result = node.triggerAutomation("943", session=TimeoutSession())

        assert result.ok is False
        assert result.code == hub.ERROR_TIMEOUT

    def test_unreachable_hub_propagates_from_list_to_trigger(self):
        """A failed list fetch surfaces instead of triggering blind."""
        node, hub = make_node()

        result = node.triggerAutomation("943", session=UnreachableSession())

        assert result.ok is False
        assert result.code == hub.ERROR_HUB_UNREACHABLE

    def test_http_404_reports_missing_endpoint(self):
        """HTTP 404 explains the app id has no endpoint trigger configured."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(404, text="Not Found"))

        result = node.triggerAutomation("943", session=session)

        assert result.ok is False
        assert result.code == hub.ERROR_HTTP_ERROR
        assert result.status_code == 404
        assert "endpoint trigger" in result.message

    def test_other_http_error(self):
        """A 500 is reported as a generic HTTP error."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        session = FakeSession(FakeResponse(500, text="Server Error"))

        result = node.triggerAutomation("943", session=session)

        assert result.ok is False
        assert result.code == hub.ERROR_HTTP_ERROR
        assert result.status_code == 500

    def test_malformed_list_payload(self):
        """An unparseable list body fails as malformed_response."""
        node, hub = make_node()
        session = FakeSession(FakeResponse(200, text="<html>not json</html>"))

        result = node.getAutomations(session=session)

        assert result.ok is False
        assert result.code == hub.ERROR_MALFORMED_RESPONSE

    def test_unexpected_transport_error(self):
        """An unexpected exception becomes transport_error, not a crash."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True

        def explode(method, url, kwargs):
            raise RuntimeError("weird transport failure")

        result = node.triggerAutomation("943", session=FakeSession(explode))

        assert result.ok is False
        assert result.code == hub.ERROR_TRANSPORT_ERROR

    def test_missing_app_id_is_not_configured(self):
        """No app id (but a token) is a configuration error, not a request."""
        node, hub = make_node({"appId": None})

        result = node.getAutomations(session=FakeSession(FakeResponse(200, {})))

        assert result.ok is False
        assert result.code == hub.ERROR_NOT_CONFIGURED
        assert "app id" in result.message

    def test_missing_token_is_not_configured(self):
        """No access token is a configuration error."""
        node, hub = make_node({"accessToken": None, "apiKey": None})

        result = node.getAutomations(session=FakeSession(FakeResponse(200, {})))

        assert result.ok is False
        assert result.code == hub.ERROR_NOT_CONFIGURED
        assert "access token" in result.message


class TestAutomationConfigAndSecrets:
    """Config resolution follows repo conventions; tokens never leak."""

    def test_env_fallback_for_credentials(self, monkeypatch):
        """HUBITAT_APP_ID / HUBITAT_ACCESS_TOKEN are picked up from the env."""
        from flows import hubitat_integration

        monkeypatch.setenv("HUBITAT_URL", HUB)
        monkeypatch.setenv("HUBITAT_APP_ID", APP_ID)
        monkeypatch.setenv("HUBITAT_ACCESS_TOKEN", TOKEN)

        node = hubitat_integration.HUBITAT_NODE("hubitat-control", {}, {}, None)

        assert node.baseUrl == HUB
        assert node.appId == APP_ID
        assert node.accessToken == TOKEN

    def test_automation_app_id_env_alias(self, monkeypatch):
        """HUBITAT_AUTOMATION_APP_ID is accepted as an alias."""
        from flows import hubitat_integration

        monkeypatch.setenv("HUBITAT_AUTOMATION_APP_ID", "4711")
        node = hubitat_integration.HUBITAT_NODE("hubitat-control", {}, {}, None)

        assert node.appId == "4711"

    def test_api_key_used_as_access_token_fallback(self):
        """A hub sharing one bearer value keeps working via apiKey."""
        node, hub = make_node({"accessToken": None, "apiKey": "shared-token"})
        session = FakeSession(FakeResponse(200, RULE_LIST))

        node.getAutomations(session=session)

        assert session.call_count == 1
        assert "access_token=shared-token" in session.last_call["url"]

    def test_token_never_appears_in_logs_or_results(self, caplog):
        """Redaction keeps the access token out of logs and result payloads."""
        node, hub = make_node({"resolveAutomations": False})
        node._automations_resolved = True
        session = FakeSession(FakeResponse(500, text="Server Error"))

        with caplog.at_level(logging.DEBUG):
            result = node.triggerAutomation("943", session=session)

        assert result.ok is False
        assert TOKEN not in caplog.text
        assert TOKEN not in repr(result.to_dict())
        assert "***" in result.url

    def test_redact_url_helper(self):
        """redact_url masks access_token/token/apiKey query values."""
        node, hub = make_node()

        assert hub.redact_url(f"{HUB}/apps/api/1/trigger?access_token={TOKEN}") == (
            f"{HUB}/apps/api/1/trigger?access_token=***"
        )
        assert hub.redact_url(f"{HUB}/x?apiKey=abc&y=1") == f"{HUB}/x?apiKey=***&y=1"
        assert hub.redact_url(None) is None


class TestAutomationSimulatedMode:
    """Without hub credentials the node keeps the legacy simulated behaviour."""

    def test_trigger_without_credentials_uses_simulator(self):
        """No appId/token -> the legacy simulated sendRequest path."""
        from flows import hubitat_integration

        node = hubitat_integration.HUBITAT_NODE("hubitat-control", {}, {}, None)

        response = node.triggerAutomation("aut1")

        assert response["success"] is True
        assert "Hubitat request completed" in response["message"]

    def test_trigger_without_credentials_honours_callback(self):
        """The simulated path still calls back like the JS flow."""
        from flows import hubitat_integration

        node = hubitat_integration.HUBITAT_NODE("hubitat-control", {}, {}, None)
        seen = []

        node.triggerAutomation("aut1", lambda err, res: seen.append((err, res)))

        assert len(seen) == 1
        assert seen[0][0] is None

    def test_list_without_credentials_uses_simulator(self):
        """Listing without credentials also uses the simulator."""
        from flows import hubitat_integration

        node = hubitat_integration.HUBITAT_NODE("hubitat-control", {}, {}, None)

        response = node.getAutomations()

        assert response["success"] is True

    def test_no_transport_configured_still_succeeds(self):
        """A configured node with no transport reports a simulated success."""
        node, hub = make_node()
        node.automations = [{"id": "943", "name": "Good Morning"}]
        node._automations_resolved = True
        hub.session = None

        result = node.triggerAutomation("943", session=None)

        assert result.ok is True
        assert result.message == "simulated"


class TestAutomationLegacyParity:
    """The legacy /api/v1/automations shims stay callable (JS parity)."""

    def test_update_automation(self):
        """updateAutomation still issues a PUT through the simulator."""
        node, hub = make_node()
        node.sendRequest = Mock()

        node.updateAutomation("aut1", {"enabled": True}, Mock())

        assert node.sendRequest.call_args[0][0] == "PUT"

    def test_delete_automation(self):
        """deleteAutomation still issues a DELETE through the simulator."""
        node, hub = make_node()
        node.sendRequest = Mock()

        node.deleteAutomation("aut1", Mock())

        assert node.sendRequest.call_args[0][0] == "DELETE"

    def test_get_automation_status(self):
        """getAutomationStatus still issues a GET through the simulator."""
        node, hub = make_node()
        node.sendRequest = Mock()

        node.getAutomationStatus("aut1", Mock())

        assert node.sendRequest.call_args[0][0] == "GET"

    def test_results_are_truthy_when_ok(self):
        """AutomationResult is bool-compatible for `if trigger(...)` checks."""
        node, hub = make_node()
        ok = hub.AutomationResult(ok=True)
        bad = hub.AutomationResult(ok=False, code="nope")

        assert bool(ok) is True
        assert bool(bad) is False
