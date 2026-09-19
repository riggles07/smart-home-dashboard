"""Hubitat integration mirror -- smart home device controls and automation.

Python mirror of ``flows/hubitat-integration.js``: the ``HUBITAT_NODE``
class provides the Hubitat hub API surface used by the dashboard.

Automation triggers (Rule Machine)
----------------------------------
Hubitat exposes no ``/api/v1/automations`` resource. Rules live in
Rule Machine and are triggered through a Rule Machine *endpoint trigger*::

    GET|POST http://<hub>/apps/api/<app_id>/trigger/<action>=<rule ids>
             ?access_token=<access token>

* ``<app_id>``     app id of a Rule Machine rule that has a
  "Local End Point" (or "Cloud End Point") trigger event configured.
* ``getRuleList``  ``/apps/api/<app_id>/trigger/getRuleList`` returns
  ``{"<rule app id>": "<rule name>", ...}`` -- the automation list.
* ``<action>``     Rule Machine action, e.g. ``runRuleAct`` /
  ``stopRuleAct``; the rule app ids follow, joined with ``&``.
* ``<value>``      instead of an action, a bare string sets the rule's
  built-in ``%value%``.

Both HTTP GET and POST are accepted by the hub for these endpoints.

References:
    * https://docs2.hubitat.com/en/apps/rule-machine
      ("Using Rule Machine from HTTP requests")
    * https://docs2.hubitat.com/en/apps/maker-api

Transport
---------
Outgoing requests go through the module-level :data:`http_transport` hook
so tests can patch ``hubitat_integration.http_transport``; when it is left
unpatched the default transport performs a real request with the stdlib
:mod:`urllib.request`.
"""

import json
import logging
import os
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import quote

DEFAULT_BASE_URL = "http://hubitat.local:8080"
DEFAULT_TIMEOUT = 10

# Rule Machine endpoint-trigger paths (relative to /apps/api/<app_id>/).
RULE_LIST_PATH = "getRuleList"
TRIGGER_PATH = "trigger"
DEFAULT_TRIGGER_ACTION = "runRuleAct"
DEFAULT_METHOD = "POST"

# Dashboard topics (Node-RED style) used to surface automation state.
AUTOMATION_TOPIC = "hubitat/automations"
#: Base result topic; per-automation results go to ``<base>/<automation id>``.
AUTOMATION_RESULT_TOPIC = "hubitat/automation/result"
AUTOMATION_RESULT_TOPIC_ID = AUTOMATION_RESULT_TOPIC + "/{automation_id}"


def automation_result_topic(automation_id=None):
    """Result topic for ``automation_id`` (the bare base when id-less).

    Mirrors the JS flow's ``AUTOMATION_RESULT_TOPIC`` handling so the dashboard
    subscribes to the same string on both runtimes.
    """
    if automation_id in (None, ""):
        return AUTOMATION_RESULT_TOPIC
    return AUTOMATION_RESULT_TOPIC_ID.format(automation_id=automation_id)


# Structured error codes returned in the ``error`` field of a result dict.
ERROR_NOT_CONFIGURED = "not_configured"
ERROR_UNKNOWN_AUTOMATION = "unknown_automation"
ERROR_AUTH_FAILURE = "auth_failure"
ERROR_HTTP_ERROR = "http_error"
ERROR_HUB_UNREACHABLE = "hub_unreachable"
ERROR_TIMEOUT = "timeout"
ERROR_TRANSPORT_ERROR = "transport_error"
ERROR_MALFORMED_RESPONSE = "malformed_response"

logger = logging.getLogger(__name__)


class HTTPResponse:
    """Minimal HTTP response container, used by the stdlib transport."""

    __slots__ = ("status", "status_code", "text")

    def __init__(self, status, text=""):
        self.status = int(status)
        self.status_code = self.status
        self.text = text or ""

    def json(self):
        """Parse the body as JSON (raises ``ValueError`` on bad input)."""
        return json.loads(self.text)

    def __repr__(self):
        return f"HTTPResponse(status={self.status}, text={self.text!r})"


class Session:
    """Default HTTP transport: a real request via stdlib :mod:`urllib.request`.

    Deliberately mimics the tiny slice of the ``requests.Session`` interface the
    rest of this module relies on (``request`` / ``get`` / ``post`` returning an
    object with ``status_code`` and ``text`` / ``json()``), so pointing
    :data:`session` at a real ``requests.Session`` works interchangeably.
    """

    def request(self, method, url, data=None, timeout=DEFAULT_TIMEOUT, **kwargs):
        """Perform ``method`` against ``url`` and return a :class:`HTTPResponse`."""
        body = None
        headers = {"Accept": "application/json"}
        if data is not None:
            body = data if isinstance(data, bytes) else json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return HTTPResponse(
                    response.status, response.read().decode("utf-8", "replace")
                )
        except urllib.error.HTTPError as exc:
            # A non-2xx response still carries a body worth surfacing.
            text = exc.read().decode("utf-8", "replace") if exc.fp else ""
            return HTTPResponse(exc.code, text)

    def get(self, url, timeout=DEFAULT_TIMEOUT, **kwargs):
        """GET ``url``."""
        return self.request("GET", url, None, timeout)

    def post(self, url, data=None, timeout=DEFAULT_TIMEOUT, **kwargs):
        """POST ``data`` to ``url``."""
        return self.request("POST", url, data, timeout)


#: Module-level HTTP transport hook -- point it at a ``requests.Session`` to
#: talk to a real hub, or patch it in tests. ``HubitatNode.session`` takes
#: precedence when set, as does a per-call ``session=`` argument.
session = Session()


class _CallRecorder:
    """Minimal call recorder exposing ``called``/``call_args`` like a Mock."""

    def __init__(self):
        self._calls = []

    def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        return None

    @property
    def called(self):
        """True once at least one call has been recorded."""
        return bool(self._calls)

    @property
    def call_args(self):
        """Arguments of the most recent call as an ``(args, kwargs)`` tuple."""
        return self._calls[-1] if self._calls else None


@dataclass(frozen=True)
class AutomationResult:
    """Structured outcome of listing or triggering Hubitat automations.

    Attributes:
        ok: ``True`` when the hub accepted the request.
        code: Machine-readable outcome -- ``ok``, ``not_configured``,
            ``unknown_automation``, ``auth_failure``, ``http_error``,
            ``hub_unreachable``, ``timeout``, ``transport_error`` or
            ``malformed_response``.
        error: Failure detail (``None`` on success).
        automations: Automation list (``list`` of ``{"id", "name"}`` dicts)
            for list operations, ``None`` for triggers.
        automation_id: Automation the request targeted (``None`` for lists).
        automation_name: Resolved name of that automation, when known.
        action: Rule Machine action performed (e.g. ``runRuleAct``).
        method: HTTP method used.
        url: The endpoint URL that was called, with the token redacted.
        status_code: HTTP status code when a real transport answered.
        message: Human-readable summary, safe to surface on the dashboard.
        payload: Decoded hub response body.
    """

    ok: bool
    code: str = "ok"
    error: object = None
    automations: object = None
    automation_id: object = None
    automation_name: object = None
    action: object = None
    method: object = None
    url: object = None
    status_code: object = None
    message: str = ""
    payload: object = None

    def to_dict(self):
        """Serialise the result for the dashboard (camelCase, JSON-safe)."""
        return {
            "ok": self.ok,
            "code": self.code,
            "error": self.error,
            "automations": self.automations,
            "automationId": self.automation_id,
            "automationName": self.automation_name,
            "action": self.action,
            "method": self.method,
            "url": self.url,
            "statusCode": self.status_code,
            "message": self.message,
            "payload": self.payload,
        }

    def __bool__(self):
        return bool(self.ok)


def redact_url(url):
    """Replace any ``access_token`` value in ``url`` with ``***``.

    Hub access tokens are bearer-equivalent, so every URL that reaches a log
    line, an exception or a dashboard event goes through here first.
    """
    if not isinstance(url, str):
        return url
    for key in ("access_token", "token", "apiKey", "accessToken"):
        # ``(\?|&)key=value`` -- value ends at the next ``&``/``#`` or the end.
        url = re.sub(
            r"([?&]%s=)[^&#]*" % re.escape(key),
            r"\1***",
            url,
            flags=re.IGNORECASE,
        )
    return url


def _env(name):
    """Read an environment variable, treating blank values as unset."""
    value = os.environ.get(name)
    return value if value else None


def _normalise_automation(entry):
    """Coerce one automation-list entry into ``{"id", "name"}``.

    ``getRuleList`` returns ``{"<app id>": "<rule name>"}``; some Hubitat
    versions and third-party endpoints return a list of objects instead.
    Entries that carry no usable id are dropped (``None``).
    """
    if isinstance(entry, dict):
        rule_id = entry.get("id", entry.get("ruleId", entry.get("value")))
        name = entry.get("name", entry.get("label", entry.get("text")))
        if rule_id in (None, ""):
            return None
        return {"id": str(rule_id), "name": str(name) if name not in (None, "") else str(rule_id)}
    if isinstance(entry, str) and entry:
        return {"id": entry, "name": entry}
    return None


def _parse_automation_list(body):
    """Parse a ``getRuleList`` response body into a normalised automation list.

    Accepts the documented ``{"id": "name"}`` mapping, a bare list of entries,
    and the ``{"rules": ...}`` / ``{"result": ...}`` wrappers seen in the wild.
    Returns ``(automations, error)`` where ``error`` is an
    :class:`AutomationResult` code string on failure, else ``None``.
    """
    if body is None:
        return None, ERROR_MALFORMED_RESPONSE
    if isinstance(body, dict):
        for key in ("rules", "automations", "result", "data"):
            if key in body and isinstance(body[key], (dict, list)):
                body = body[key]
                break
    if isinstance(body, dict):
        entries = [{"id": key, "name": value} for key, value in body.items()]
    elif isinstance(body, list):
        entries = body
    else:
        return None, ERROR_MALFORMED_RESPONSE

    automations = []
    for entry in entries:
        normalised = _normalise_automation(entry)
        if normalised is not None:
            automations.append(normalised)
    return automations, None


def _response_text(response):
    """Best-effort text body from a transport response object."""
    text = getattr(response, "text", None)
    if isinstance(text, (str, bytes)):
        return text.decode("utf-8", "replace") if isinstance(text, bytes) else text
    body = getattr(response, "body", None)
    if isinstance(body, (str, bytes)):
        return body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    return ""


def _parse_body(response):
    """Decode a transport response body to JSON, or ``None`` when unparseable."""
    json_method = getattr(response, "json", None)
    if callable(json_method):
        try:
            return json_method()
        except (TypeError, ValueError):
            return None
    text = _response_text(response)
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


class HubitatNode:
    """Hubitat control node (mirror of the ``hubitat-control`` node)."""

    def __init__(self, node_type, msg, config, node=None):
        self.type = node_type
        self.config = dict(config or {})
        self.baseUrl = (
            self.config.get("url")
            or _env("HUBITAT_URL")
            or DEFAULT_BASE_URL
        )
        self.apiKey = self.config.get("apiKey") or _env("HUBITAT_API_KEY")
        # Rule Machine endpoint-trigger credentials. The endpoint is served by
        # the rule's own app id and carries the *rule* access token, which is
        # distinct from the Maker API token used for device commands; a hub can
        # be configured with either or both.
        self.appId = (
            self.config.get("appId")
            or self.config.get("automationAppId")
            or _env("HUBITAT_APP_ID")
            or _env("HUBITAT_AUTOMATION_APP_ID")
        )
        self.accessToken = (
            self.config.get("accessToken")
            or self.config.get("token")
            or _env("HUBITAT_ACCESS_TOKEN")
            # ``access_token`` is what the hub's own UI calls it; ``apiKey`` is
            # the repo's existing name for the same bearer value.
            or self.config.get("apiKey")
            or _env("HUBITAT_API_KEY")
        )
        self.timeout = self.config.get("timeout") or DEFAULT_TIMEOUT
        #: Optional ``requests``-style session used as the transport. When left
        #: as ``None`` the module-level :data:`session` hook is used instead.
        self.session = self.config.get("session")
        self.devices = []
        self.activeAutomations = []
        #: Last automation list fetched from the hub (``[{"id", "name"}, ...]``).
        self.automations = []
        #: True once a list fetch has actually succeeded (guards the cache).
        self._automations_resolved = False
        #: When True (default) an automation id must appear in the rule list
        #: before it is triggered; set ``resolveAutomations`` to ``False`` to
        #: pass unknown ids straight through to the hub.
        self.resolveAutomations = self.config.get("resolveAutomations", True)
        #: Method used for trigger calls; Rule Machine accepts GET and POST.
        self.triggerMethod = self.config.get("triggerMethod") or DEFAULT_METHOD
        self.send = _CallRecorder()
        self.status = _CallRecorder()
        self._handlers = {}

    # -- events ----------------------------------------------------------------
    def on(self, event, handler):
        """Register a handler, or dispatch immediately when given a dict."""
        if callable(handler):
            self._handlers.setdefault(event, []).append(handler)
        elif isinstance(handler, dict):
            self._dispatch(event, handler)

    def _dispatch(self, event, data):
        if event == "subscribe" and data.get("type") == "device-state":
            self.updateDeviceState(data.get("deviceId"))
        for handler in self._handlers.get(event, []):
            handler(data)

    # -- API surface -------------------------------------------------------------
    def getDevices(self, callback=None):
        """Fetch all devices (GET /api/v1/devices)."""
        return self.sendRequest(
            "GET", f"{self.baseUrl}/api/v1/devices", None, callback
        )

    def getDevice(self, device_id, callback=None):
        """Fetch one device by id (GET /api/v1/devices/<id>)."""
        return self.sendRequest(
            "GET", f"{self.baseUrl}/api/v1/devices/{device_id}", None, callback
        )

    def updateDevice(self, device_id, data, callback=None):
        """Update a device (PUT /api/v1/devices/<id>)."""
        return self.sendRequest(
            "PUT", f"{self.baseUrl}/api/v1/devices/{device_id}", data, callback
        )

    # -- automations (Rule Machine) -------------------------------------------
    def triggerAutomation(self, automation_id, callback=None, action=None,
                          value=None, session=None, method=None):
        """Trigger a Hubitat automation over a Rule Machine endpoint trigger.

        ``POST http://<hub>/apps/api/<app_id>/trigger/<action>=<automation_id>
        ?access_token=<access token>``

        Args:
            automation_id: Rule Machine rule app id, or a rule *name* that is
                present in the last :meth:`getAutomations` result.
            callback: Optional ``callback(err, result)`` -- kept as the second
                positional argument for parity with the JS flow's
                ``triggerAutomation(automationId, callback)``.
            action: Rule Machine action (default ``runRuleAct``); use
                ``stopRuleAct`` to stop a running rule.
            value: Instead of ``action``, a plain string to set the rule's
                built-in ``%value%`` variable.
            session: Per-call transport override.
            method: HTTP method override; Rule Machine accepts GET and POST.

        Returns:
            AutomationResult: never raises -- failures come back as
            ``ok=False`` with a structured ``code`` so the dashboard can
            render them. When the hub credentials are not configured the node
            falls back to the simulated transport (see :meth:`sendRequest`).
        """
        if automation_id in (None, ""):
            return self._publish_result(self._automation_fail(
                ERROR_UNKNOWN_AUTOMATION, "automation id is required",
                action=action, callback=None,
            ), callback)

        if self._automation_simulation_fallback():
            # Simulated mode: no app id and no access token, so there is nothing
            # to call on the hub. Mirror the legacy Node-RED shim exactly.
            logger.debug(
                "hubitat automation %r simulated (no appId/access token)", automation_id
            )
            return self.sendRequest(
                "POST",
                f"{self.baseUrl}/api/v1/automations/{automation_id}/trigger",
                None,
                callback,
            )

        resolved, list_error = self._resolve_automation(automation_id, session)
        if list_error is not None:
            return self._publish_result(list_error, callback)
        if resolved is None:
            return self._publish_result(self._automation_fail(
                ERROR_UNKNOWN_AUTOMATION,
                f"unknown automation id {automation_id!r}",
                automation_id=automation_id, action=action, callback=None,
            ), callback)

        rule_id = resolved["id"]
        rule_name = resolved.get("name")
        try:
            url = self._automation_url(rule_id, action=action, value=value)
        except ValueError as exc:
            return self._publish_result(self._automation_fail(
                ERROR_NOT_CONFIGURED, str(exc),
                automation_id=rule_id, automation_name=rule_name,
                action=action, callback=None,
            ), callback)

        http_method = (method or self.triggerMethod or DEFAULT_METHOD).upper()
        result = self._automation_request(
            http_method, url,
            automation_id=rule_id, automation_name=rule_name,
            action=None if value is not None else (action or DEFAULT_TRIGGER_ACTION),
            session=session,
        )
        return self._publish_result(result, callback)

    def getAutomations(self, callback=None, session=None, refresh=False):
        """List the automations available to trigger.

        ``GET http://<hub>/apps/api/<app_id>/trigger/getRuleList
        ?access_token=<access token>``

        The hub returns ``{"<rule app id>": "<rule name>", ...}``; the parsed
        list is cached on ``self.automations`` and published to the dashboard
        on :data:`AUTOMATION_TOPIC`. Pass ``refresh=True`` to bypass the cache.

        Returns:
            AutomationResult: ``automations`` holds ``[{"id", "name"}, ...]``
            on success.
        """
        if not refresh and self._automations_resolved:
            return self._publish_list(self.automations, callback)

        if self._automation_simulation_fallback():
            # Simulated mode -- see :meth:`triggerAutomation`.
            logger.debug("hubitat automation list simulated (no appId/access token)")
            return self.sendRequest(
                "GET", f"{self.baseUrl}/api/v1/automations", None, callback
            )

        try:
            url = self._automation_url(rule_list=True)
        except ValueError as exc:
            return self._publish_result(
                self._automation_fail(ERROR_NOT_CONFIGURED, str(exc), callback=None),
                callback,
            )

        result = self._automation_request(
            "GET", url, session=session, listing=True
        )
        if not result.ok:
            return self._publish_result(result, callback)

        automations, error_code = _parse_automation_list(result.payload)
        if error_code is not None:
            failure = self._automation_fail(
                error_code,
                "hub returned an unparseable automation list",
                method="GET", url=result.url, status_code=result.status_code,
                payload=result.payload, callback=None,
            )
            return self._publish_result(failure, callback)

        self.automations = automations
        self._automations_resolved = True
        logger.info("hubitat automation list refreshed: %d rule(s)", len(automations))
        return self._publish_list(automations, callback)

    #: Explicit dashboard-facing alias for the automation list.
    listAutomations = getAutomations

    def handleAutomationTrigger(self, request, callback=None, session=None):
        """Dashboard entry point for the 'Automation triggers' control.

        Accepts a Node-RED style message -- ``{"payload": {"automationId": ...,
        "action": ..., "value": ...}}`` -- or a bare automation id, and returns
        the :class:`AutomationResult` (also sent on the result topic so the UI
        can reflect success/failure).
        """
        payload = request.get("payload") if isinstance(request, dict) else request
        if not isinstance(payload, dict):
            payload = {"automationId": payload}
        return self.triggerAutomation(
            payload.get("automationId", payload.get("automation_id")),
            callback=callback,
            action=payload.get("action"),
            value=payload.get("value"),
            session=session or payload.get("session"),
        )

    def handleAutomationList(self, request=None, callback=None, session=None):
        """Dashboard entry point for the automation picker.

        Accepts the same message shape as :meth:`handleAutomationTrigger`;
        ``{"payload": {"refresh": true}}`` forces a re-fetch.
        """
        payload = request.get("payload") if isinstance(request, dict) else request
        refresh = bool(payload.get("refresh")) if isinstance(payload, dict) else False
        return self.getAutomations(callback=callback, session=session, refresh=refresh)

    # -- automations: helpers -------------------------------------------------
    def _automation_configured(self):
        """True when the Rule Machine endpoint credentials are all present."""
        return bool(self.baseUrl and self.appId and self.accessToken)

    def _automation_simulation_fallback(self):
        """True when nothing automation-related is configured at all.

        Nodes with no app id *and* no token have nothing to call, so they keep
        the legacy simulated behaviour (which the original flow tests rely on).
        A *partial* configuration is not simulated -- it is reported honestly as
        ``not_configured`` so a typo in one env var cannot look like success.
        """
        return not self.appId and not self.accessToken

    def _resolve_automation(self, automation_id, session=None):
        """Resolve ``automation_id`` against the known rule list.

        Returns ``(entry, error_result)``: ``entry`` is ``{"id", "name"}`` when
        the id (or name) is known, ``None`` when it is not, and ``error_result``
        carries a list-fetch failure that should be surfaced to the caller.
        """
        wanted = str(automation_id)
        if not self._automations_resolved:
            listing = self.getAutomations(session=session)
            if not listing.ok:
                return None, listing
        for entry in self.automations:
            if wanted in (entry.get("id"), entry.get("name")):
                return entry, None
        if not self.resolveAutomations:
            # Optimistic mode: send the id through even though it is unknown.
            logger.debug("hubitat automation %r not in cached list; sending anyway", wanted)
            return {"id": wanted, "name": None}, None
        return None, None

    def _automation_url(self, automation_id=None, action=None, value=None,
                        rule_list=False):
        """Build a Rule Machine endpoint-trigger URL (token included).

        Raises ``ValueError`` when the hub URL / app id / access token is
        unset. Call :func:`redact_url` before logging the result.
        """
        if not self.baseUrl:
            raise ValueError("Hubitat base URL is not configured")
        if not self.appId:
            raise ValueError("Hubitat automation app id (appId) is not configured")
        if not self.accessToken:
            raise ValueError("Hubitat access token is not configured")

        base = (
            f"{self.baseUrl.rstrip('/')}/apps/api/"
            f"{quote(str(self.appId), safe='')}/{TRIGGER_PATH}"
        )
        if rule_list:
            path = f"{base}/{RULE_LIST_PATH}"
        elif value is not None:
            # A bare string sets the rule's built-in %value% variable.
            path = f"{base}/{quote(str(value), safe='')}"
        else:
            rule_action = action or DEFAULT_TRIGGER_ACTION
            path = (
                f"{base}/{quote(str(rule_action), safe='')}"
                f"={quote(str(automation_id), safe='')}"
            )
        return f"{path}?access_token={quote(str(self.accessToken), safe='')}"

    def _automation_transport(self, session=None):
        """Resolve the transport: per-call > node > module-level hook."""
        if session is not None:
            return session
        if self.session is not None:
            return self.session
        return globals().get("session")

    def _automation_request(self, http_method, url, automation_id=None,
                            automation_name=None, action=None,
                            session=None, listing=False):
        """Run one automation request and normalise the outcome.

        Returns an :class:`AutomationResult`; ``ok`` means the hub answered 2xx.
        Never raises: transport, auth and HTTP failures become ``ok=False``.
        """
        context = dict(
            automation_id=automation_id, automation_name=automation_name,
            action=action, method=http_method,
        )
        transport = self._automation_transport(session)
        if transport is None:
            # No transport wired up: mirror the simulated sendRequest.
            logger.debug("hubitat %s %s (no transport configured)",
                         http_method, redact_url(url))
            return AutomationResult(
                ok=True, code="ok", url=redact_url(url), message="simulated",
                automations=None, **context,
            )

        request = getattr(transport, "request", None)
        try:
            if request is not None:
                try:
                    response = request(http_method, url, timeout=self.timeout)
                except TypeError:
                    response = request(http_method, url)
            elif http_method == "POST":
                response = transport.post(url, timeout=self.timeout)
            else:
                response = transport.get(url, timeout=self.timeout)
        except (TimeoutError, socket.timeout) as exc:
            return self._automation_fail(
                ERROR_TIMEOUT, "Hubitat hub did not respond in time",
                error=str(exc) or "request timed out", **context,
            )
        except Exception as exc:  # requests raises a broad family of errors
            name = exc.__class__.__name__
            code = (
                ERROR_HUB_UNREACHABLE
                if name in ("RequestException", "ConnectionError", "HTTPError",
                            "URLError", "OSError", "NewConnectionError")
                else ERROR_TRANSPORT_ERROR
            )
            message = (
                "Hubitat hub is unreachable"
                if code == ERROR_HUB_UNREACHABLE
                else "Unexpected error talking to the Hubitat hub"
            )
            return self._automation_fail(
                code, message, error=str(exc) or name, **context
            )

        status = getattr(response, "status_code", None)
        payload = _parse_body(response)
        if isinstance(status, int) and not 200 <= status < 300:
            if status in (401, 403):
                code = ERROR_AUTH_FAILURE
                message = (
                    f"Hubitat rejected the request (HTTP {status}); check the "
                    "app id and access token"
                )
            elif status == 404:
                code = ERROR_HTTP_ERROR
                message = (
                    "Hubitat automation endpoint not found (HTTP 404); the app "
                    "id has no endpoint trigger configured"
                )
            else:
                code = ERROR_HTTP_ERROR
                message = f"Hubitat returned HTTP {status}"
            return self._automation_fail(
                code, message, status_code=status, url=redact_url(url),
                error=_response_text(response) or message, payload=payload,
                **context,
            )

        if listing:
            message = "automation list fetched"
        elif automation_name:
            message = f"automation {automation_name!r} triggered"
        else:
            message = "automation triggered"
        logger.info(
            "hubitat automation %s ok (method=%s, id=%s)",
            "list" if listing else "trigger", http_method, automation_id,
        )
        return AutomationResult(
            ok=True, code="ok", status_code=status, message=message,
            payload=payload, url=redact_url(url), **context,
        )

    def _automation_fail(self, code, message, callback=None, error=None,
                         status_code=None, payload=None, **context):
        """Build a failed :class:`AutomationResult` and log it clearly."""
        result = AutomationResult(
            ok=False, code=code, error=error or message,
            status_code=status_code, payload=payload, message=message, **context,
        )
        logger.warning(
            "hubitat automation failed (%s) id=%r: %s",
            code, context.get("automation_id"), message,
        )
        if callback is not None:
            callback(result.error, result)
        return result

    def _publish_result(self, result, callback=None):
        """Send a trigger result to the dashboard topic and honour ``callback``."""
        self.send(
            payload=result.to_dict(),
            topic=automation_result_topic(result.automation_id),
        )
        if callback is not None:
            callback(None if result.ok else result.error, result)
        return result

    def _publish_list(self, automations, callback=None):
        """Send the automation list to the dashboard topic and honour ``callback``."""
        result = AutomationResult(
            ok=True, code="ok", automations=list(automations), method="GET",
            message=f"{len(automations)} automation(s) available",
        )
        self.send(payload=result.to_dict(), topic=AUTOMATION_TOPIC)
        if callback is not None:
            callback(None, result)
        return result

    def updateAutomation(self, automation_id, data, callback=None):
        """Update an automation (PUT /api/v1/automations/<id>).

        Legacy Node-RED parity shim: Hubitat has no ``/api/v1/automations``
        resource, so this only exercises the simulated transport. Rule
        enable/disable is done on the hub (Rule Machine), not over Maker API.
        """
        return self.sendRequest(
            "PUT",
            f"{self.baseUrl}/api/v1/automations/{automation_id}",
            data,
            callback,
        )

    def deleteAutomation(self, automation_id, callback=None):
        """Delete an automation (DELETE /api/v1/automations/<id>).

        Legacy Node-RED parity shim; see :meth:`updateAutomation`.
        """
        return self.sendRequest(
            "DELETE",
            f"{self.baseUrl}/api/v1/automations/{automation_id}",
            None,
            callback,
        )

    def getAutomationStatus(self, automation_id, callback=None):
        """Fetch automation status (GET /api/v1/automations/<id>/status).

        Legacy Node-RED parity shim; see :meth:`updateAutomation`.
        """
        return self.sendRequest(
            "GET",
            f"{self.baseUrl}/api/v1/automations/{automation_id}/status",
            None,
            callback,
        )

    def refreshDevices(self):
        """Refresh the device list and publish the count in node status."""
        def on_devices(err, devices):
            if err:
                return None
            if isinstance(devices, dict):
                devices = devices.get("devices") or []
            self.devices = devices or []
            self.status({
                "fill": "green",
                "shape": "dot",
                "text": f"{len(self.devices)} devices",
            })
            self.send({"payload": self.devices})
            return None

        injected = getattr(self, "_last_request_response", None)
        if isinstance(injected, dict) and "devices" in injected:
            on_devices(None, injected["devices"])
        else:
            self.getDevices(on_devices)
        return None

    def updateDeviceState(self, device_id):
        """Publish the current state of a device on its state topic."""
        device = None
        injected = getattr(self, "_last_request_response", None)
        if isinstance(injected, dict):
            device = injected.get("device")
            if device is None and "id" in injected:
                device = injected
        if device is None:
            device = self.getDevice(device_id)
        if isinstance(device, dict):
            self.send(
                payload=device,
                topic=f"hubitat/device/{device_id}/state",
            )
            return device
        return None

    def sendRequest(self, method, url, data, callback=None):
        """Simulated HTTP request -- responds with a canned success payload."""
        response = {
            "success": True,
            "data": data or {},
            "message": "Hubitat request completed",
        }
        if callback is not None:
            callback(None, response)
        return response


# Name used by the Node-RED flow registration and the tests.
HUBITAT_NODE = HubitatNode

__all__ = [
    "HubitatNode",
    "HUBITAT_NODE",
    "AutomationResult",
    "Session",
    "HTTPResponse",
    "DEFAULT_BASE_URL",
    "DEFAULT_TIMEOUT",
    "DEFAULT_TRIGGER_ACTION",
    "DEFAULT_METHOD",
    "RULE_LIST_PATH",
    "TRIGGER_PATH",
    "AUTOMATION_TOPIC",
    "AUTOMATION_RESULT_TOPIC",
    "AUTOMATION_RESULT_TOPIC_ID",
    "automation_result_topic",
    "redact_url",
    "session",
]
