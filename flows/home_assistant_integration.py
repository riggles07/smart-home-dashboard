"""Home Assistant integration mirror -- smart home device controls.

Python mirror of ``flows/home-assistant-integration.js``: the
:class:`HomeAssistantNode` class (exported as :data:`HOME_ASSISTANT_NODE`)
provides the Home Assistant API surface used by the dashboard.

Two transports, per docs/REQUIREMENTS_V2.md (Phase 7 migration):

Control path (Dashboard UI -> HA)
    REST service calls -- ``POST /api/services/<domain>/<service>`` with
    ``Authorization: Bearer <LLAT>``.  REST is preferred for one-off
    commands because every call is self-contained.

State path (HA -> Dashboard UI)
    The **WebSocket API** -- ``ws(s)://<host>/api/websocket``.  One
    connection authenticates, then ``get_states`` snapshots every entity
    and ``subscribe_events`` (``state_changed``) pushes updates in real
    time, giving bidirectional sync: a UI action fires a service call, HA
    emits ``state_changed``, and the dashboard re-syncs the widget.

Legacy Hubitat device commands (``on`` / ``off`` / ``setLevel`` /
``setColor`` / ...) are mapped onto HA service calls by
:meth:`HomeAssistantNode.map_hubitat_command`, so dashboard widgets written
against the Hubitat Maker API keep working against HA entities.

Credentials come from the node config (``url`` / ``token`` / ``entityId``)
with ``HA_URL`` / ``HA_TOKEN`` (Long-Lived Access Token) /
``HA_ENTITY_ID`` as environment fallbacks; nothing is hard-coded and the
token is never logged.

Design note (round 2 wires the deployed flow):
    Node-RED's core ``websocket-client`` config node passes its URL
    VERBATIM -- it does not expand ``${HA_URL}`` -- so the env-driven
    WebSocket client must be a ``function`` node using
    ``libs: [{var: "ws", module: "ws"}]`` (``ws`` is a transitive
    dependency of ``@node-red/nodes``, hoisted into Node-RED's
    node_modules; ``functionExternalModules`` defaults to true in
    Node-RED 4.x/5.x).  See ``docs/HOME_ASSISTANT_INTEGRATION.md`` for
    the full design and the round-2 wiring checklist.

Every command returns a :class:`CommandResult` (``ok`` / ``code`` /
``error`` plus ``to_dict()`` for the dashboard) instead of raising, so an
unreachable or misconfigured hub can never take the dashboard down.

Note:
    ``on()`` stays reserved for Node-RED event registration -- it is the
    ``on(event, handler)`` emitter the flow and its tests rely on -- so the
    power commands are ``turn_on()`` / ``turn_off()``, or the generic
    ``call_service(domain, service, entity_id)``.
"""

import json
import logging
import os
from dataclasses import dataclass

DEFAULT_BASE_URL = "http://homeassistant.local:8123"
DEFAULT_TIMEOUT = 10.0

#: WebSocket endpoint (relative to the HA base URL, http -> ws).
WEBSOCKET_PATH = "/api/websocket"

#: State topic one entity's updates are published on (HA -> UI).
STATE_TOPIC_TEMPLATE = "ha/entity/{entity_id}/state"
#: Command topic results are published on (UI -> HA -> UI).
COMMAND_TOPIC_TEMPLATE = "ha/entity/{entity_id}/command"

logger = logging.getLogger(__name__)

#: Module-level transport hook (same idea as ``integration_functions.fetch``):
#: point it at a ``requests``-style session to talk to a real hub, or patch
#: it in tests.  ``HomeAssistantNode.session`` takes precedence when set.
session = None


def _parse_json(text):
    """Parse a JSON string, returning ``None`` when it is empty/invalid."""
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _to_number(value):
    """Coerce a numeric command argument to ``int``/``float`` (``None`` if not numeric)."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


@dataclass(frozen=True)
class CommandResult:
    """Structured outcome of a Home Assistant service call.

    Attributes:
        ok: ``True`` when HA accepted the command.
        code: Machine-readable outcome (``ok``, ``missing_configuration``,
            ``unknown_service``, ``unknown_entity``, ``read_only``,
            ``invalid_argument``, ``invalid_payload``, ``timeout``,
            ``connection_error``, ``http_error``, ``auth_error``,
            ``transport_error``).
        entity_id: Entity the command targeted.
        domain: HA domain (``light``, ``switch``, ...).
        service: HA service name (``turn_on``, ...).
        service_data: Service payload fields (``brightness_pct``, ...).
        status_code: HTTP status code when a real transport answered.
        message: Human-readable summary, safe to publish to the dashboard.
        error: Failure detail (``None`` on success).
        payload: Decoded HA response body.
    """

    ok: bool
    code: str = "ok"
    entity_id: object = None
    domain: object = None
    service: object = None
    service_data: object = None
    status_code: object = None
    message: str = ""
    error: object = None
    payload: object = None
    #: Legacy Hubitat command name, when the action came through the
    #: compatibility mapping (``on`` / ``setLevel`` / ...).
    command: object = None

    def to_dict(self):
        """Serialise the result for the dashboard (camelCase, JSON-safe)."""
        return {
            "ok": self.ok,
            "code": self.code,
            "entityId": self.entity_id,
            "domain": self.domain,
            "service": self.service,
            "serviceData": self.service_data,
            "statusCode": self.status_code,
            "message": self.message,
            "error": self.error,
            "payload": self.payload,
            "command": self.command,
        }

    def __bool__(self):
        return bool(self.ok)


#: Service calls the dashboard can make, keyed ``"<domain>.<service>"``.
#: ``data`` lists the service_data fields the UI may set.
SUPPORTED_SERVICES = {
    "light.turn_on": {
        "domain": "light",
        "service": "turn_on",
        "data": ["brightness_pct", "brightness", "hs_color", "kelvin", "rgb_color"],
        "description": "Turn a light on, optionally setting brightness/colour.",
    },
    "light.turn_off": {
        "domain": "light",
        "service": "turn_off",
        "data": [],
        "description": "Turn a light off.",
    },
    "light.toggle": {
        "domain": "light",
        "service": "toggle",
        "data": ["brightness_pct", "hs_color", "kelvin"],
        "description": "Toggle a light.",
    },
    "switch.turn_on": {
        "domain": "switch",
        "service": "turn_on",
        "data": [],
        "description": "Turn a switch on.",
    },
    "switch.turn_off": {
        "domain": "switch",
        "service": "turn_off",
        "data": [],
        "description": "Turn a switch off.",
    },
    "switch.toggle": {
        "domain": "switch",
        "service": "toggle",
        "data": [],
        "description": "Toggle a switch.",
    },
    "homeassistant.update_entity": {
        "domain": "homeassistant",
        "service": "update_entity",
        "data": [],
        "description": "Ask HA to re-read an entity's state (legacy 'refresh').",
    },
    "homeassistant.turn_off": {
        "domain": "homeassistant",
        "service": "turn_off",
        "data": [],
        "description": "Turn off any controllable entity.",
    },
    "homeassistant.turn_on": {
        "domain": "homeassistant",
        "service": "turn_on",
        "data": [],
        "description": "Turn on any controllable entity.",
    },
}

#: Numeric ranges the dashboard enforces before calling HA.
NUMERIC_RANGES = {
    "brightness_pct": (0, 100),
    "brightness": (0, 255),
    "kelvin": (1000, 10000),
    "hue": (0, 100),  # Hubitat hue scale -- converted to 0-360 on the wire
    "saturation": (0, 100),
    "level": (0, 100),
}

#: Legacy Hubitat Maker API command -> HA service.  The domain comes from the
#: target entity (``light.*`` / ``switch.*``), so one table covers lights,
#: switches and dimmers.  Sensor entities are read-only and have no entry,
#: which is how read-only devices are rejected.
HUBITAT_COMMAND_MAP = {
    "on": {"service": "turn_on", "data": []},
    "off": {"service": "turn_off", "data": []},
    "toggle": {"service": "toggle", "data": []},
    # turn_on/turn_off chosen from the ``state`` argument
    "setSwitch": {"service": None, "data": ["state"]},
    "setLevel": {"service": "turn_on", "data": ["brightness_pct"]},
    "setHue": {"service": "turn_on", "data": ["hs_color"]},
    "setSaturation": {"service": "turn_on", "data": ["hs_color"]},
    "setColor": {"service": "turn_on", "data": ["hs_color", "brightness_pct"]},
    "setColorTemperature": {"service": "turn_on", "data": ["kelvin"]},
    "setColorHex": {"service": "turn_on", "data": ["rgb_color"]},
    "refresh": {"service": "update_entity", "data": []},
}

#: Hubitat capability family -> HA entity domain, used when a legacy widget
#: addresses a device by capability rather than by entity id.
HUBITAT_CAPABILITY_DOMAINS = {
    "switch": "switch",
    "dimmer": "light",
    "color-bulb": "light",
    "sensor": "sensor",
    "common": "homeassistant",
}

#: Entities that can never accept a service call.
READ_ONLY_DOMAINS = [
    "sensor",
    "binary_sensor",
    "input_datetime",
    "weather",
    "zone",
    "device_tracker",
]

#: ``entity_id`` is the service TARGET (body root for REST, ``target`` for
#: the WS protocol) -- it is never valid inside ``service_data``, so the
#: ``data`` allow-lists above never contain it.


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


class HomeAssistantNode:
    """Home Assistant control node (mirror of ``home-assistant-control``)."""

    def __init__(self, node_type, msg, config, node=None):
        self.type = node_type
        self.config = dict(config or {})
        self.baseUrl = (
            self.config.get("url") or os.environ.get("HA_URL") or DEFAULT_BASE_URL
        )
        # Long-Lived Access Token (LLAT) -- Profile -> Security ->
        # Long-Lived Access Tokens in the HA UI.
        self.token = self.config.get("token") or os.environ.get("HA_TOKEN")
        #: Entity the Devices-tab power switch / brightness slider controls.
        self.entityId = (
            self.config.get("entityId")
            or os.environ.get("HA_ENTITY_ID")
        )
        self.timeout = self.config.get("timeout") or DEFAULT_TIMEOUT
        #: Optional ``requests``-style session used as the transport. When
        #: left as ``None`` the module-level :data:`session` hook is used.
        self.session = self.config.get("session")
        #: entity_id -> current HA state object (filled by get_states / WS).
        self.states = {}
        #: WebSocket command id counter (per HA WS protocol).
        self.command_id = 0
        self.devices = []
        self.activeAutomations = []
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
            self.update_entity_state(data.get("entityId"))
        for handler in self._handlers.get(event, []):
            handler(data)

    # -- URL / protocol helpers ---------------------------------------------------
    def rest_url(self, path):
        """Build a REST API URL, raising ``ValueError`` when unconfigured."""
        if not self.baseUrl:
            raise ValueError("Home Assistant URL is not configured")
        if not self.token:
            raise ValueError(
                "Home Assistant token (HA_TOKEN, LLAT) is not configured"
            )
        return f"{self.baseUrl.rstrip('/')}/api/{str(path).lstrip('/')}"

    def websocket_url(self):
        """The WebSocket API URL for the configured base (``http`` -> ``ws``)."""
        if not self.baseUrl:
            raise ValueError("Home Assistant URL is not configured")
        return self.baseUrl.rstrip("/").replace("http", "ws", 1) + WEBSOCKET_PATH

    def next_command_id(self):
        """Next WS command id (monotonic, per the HA WebSocket protocol)."""
        self.command_id += 1
        return self.command_id

    # WebSocket protocol messages (developers.home-assistant.io/docs/api/websocket)
    def build_auth_message(self):
        """The ``auth`` client message carrying the LLAT."""
        if not self.token:
            raise ValueError(
                "Home Assistant token (HA_TOKEN, LLAT) is not configured"
            )
        return {"type": "auth", "access_token": self.token}

    def build_get_states_command(self):
        """The ``get_states`` command -- snapshot of every entity."""
        return {"id": self.next_command_id(), "type": "get_states"}

    def build_subscribe_events_command(self, event_type=None):
        """The ``subscribe_events`` command -- real-time ``state_changed``."""
        return {
            "id": self.next_command_id(),
            "type": "subscribe_events",
            "event_type": event_type or "state_changed",
        }

    def build_call_service_command(self, domain, service, entity_id, service_data=None):
        """The ``call_service`` command for the WebSocket transport.

        Per the HA WebSocket protocol the ``service`` key is REQUIRED
        (a frame without it is rejected with ``required key not provided
        @ data['service']``), and the target is carried in ``target``.
        """
        command = {
            "id": self.next_command_id(),
            "type": "call_service",
            "domain": domain,
            "service": service,
            "target": {"entity_id": entity_id},
        }
        if service_data:
            command["service_data"] = service_data
        return command

    @staticmethod
    def supported_services():
        """Return the service catalogue the dashboard can call (a copy)."""
        return {
            key: {
                "domain": spec["domain"],
                "service": spec["service"],
                "data": list(spec["data"]),
                "description": spec["description"],
            }
            for key, spec in SUPPORTED_SERVICES.items()
        }

    # -- state normalisation ---------------------------------------------------------
    @staticmethod
    def normalize_state(state):
        """Normalise a HA state object into the shape dashboard widgets use.

        Brightness (HA stores 0-255) is surfaced as a 0-100 percentage, and
        ``is_on`` collapses the ``on``/``off`` string for switches.
        """
        if not isinstance(state, dict) or not state.get("entity_id"):
            return None
        attributes = state.get("attributes") or {}
        brightness_pct = None
        if isinstance(attributes.get("brightness_pct"), (int, float)):
            brightness_pct = round(attributes["brightness_pct"])
        elif isinstance(attributes.get("brightness"), (int, float)):
            brightness_pct = round((attributes["brightness"] / 255) * 100)
        return {
            "entityId": state["entity_id"],
            "domain": str(state["entity_id"]).split(".")[0],
            "state": state.get("state"),
            "friendlyName": attributes.get("friendly_name") or state["entity_id"],
            "isOn": state.get("state") == "on",
            "brightnessPct": brightness_pct,
            "lastChanged": state.get("last_changed"),
            "lastUpdated": state.get("last_updated"),
        }

    def handle_state_event(self, event):
        """Fold one ``state_changed`` event into the cache and publish it.

        This is the HA -> UI half of the bidirectional sync: any state
        change (from the dashboard, automations, or the physical device)
        reaches the dashboard over the ``ha/entity/<id>/state`` topic.
        """
        data = (event or {}).get("data") if isinstance(event, dict) else {}
        data = data or {}
        entity_id = data.get("entity_id")
        new_state = data.get("new_state")
        if not entity_id or not isinstance(new_state, dict):
            return None
        self.states[entity_id] = new_state
        normalized = self.normalize_state(new_state)
        if normalized:
            self.send(
                {
                    "payload": normalized,
                    "topic": STATE_TOPIC_TEMPLATE.format(entity_id=entity_id),
                }
            )
        return normalized

    def update_entity_state(self, entity_id):
        """Publish the cached state of one entity on its state topic."""
        state = self.states.get(entity_id)
        if state:
            self.send(
                {
                    "payload": self.normalize_state(state),
                    "topic": STATE_TOPIC_TEMPLATE.format(entity_id=entity_id),
                }
            )
        return state or None

    def handle_server_message(self, message):
        """Dispatch one inbound WebSocket message from HA.

        Returns the list of outbound protocol messages the caller should
        write to the socket next (``auth`` after ``auth_required``, then
        ``get_states`` + ``subscribe_events`` after ``auth_ok``), so a raw
        socket client drives the whole protocol by pairing this with
        ``build_*_command``.
        """
        out = []
        if not isinstance(message, dict) or not message.get("type"):
            return out
        message_type = message["type"]
        if message_type == "auth_required":
            out.append(self.build_auth_message())
        elif message_type == "auth_ok":
            # Snapshot every entity, then subscribe to live changes.
            out.append(self.build_get_states_command())
            out.append(self.build_subscribe_events_command("state_changed"))
        elif message_type == "auth_invalid":
            self.status(
                {"fill": "red", "shape": "ring", "text": "auth failed (bad HA_TOKEN?)"}
            )
        elif message_type == "result":
            if message.get("success") and isinstance(message.get("result"), list):
                # get_states response: refresh the whole cache.
                for state in message["result"]:
                    if isinstance(state, dict) and state.get("entity_id"):
                        self.states[state["entity_id"]] = state
                self.send(
                    {"payload": len(self.states), "topic": "ha/state_count"}
                )
            elif message.get("success") is False:
                # A command frame HA rejected. Dropping it silently would
                # leave the dashboard believing the command succeeded.
                self.status(
                    {
                        "fill": "red",
                        "shape": "ring",
                        "text": (
                            f"command {message.get('id')} failed: "
                            f"{message.get('error', {}).get('message', 'unknown error')}"
                            if isinstance(message.get("error"), dict)
                            else f"command {message.get('id')} failed"
                        ),
                    }
                )
        elif message_type == "event":
            self.handle_state_event(message.get("event"))
        return out

    # -- legacy Hubitat -> HA mapping ---------------------------------------------------
    def map_hubitat_command(self, command, value=None, domain=None, entity_id=None):
        """Map a legacy Hubitat device command onto a HA service call.

        Args:
            command: Hubitat Maker API command name (``"on"``, ``"setLevel"``...).
            value: The command argument (scalar or mapping).
            domain: Optional HA domain override; defaults to the target
                entity's prefix (``light.kitchen`` -> ``light``).
            entity_id: The entity the command targets. Defaults to the
                node's configured entity; used to derive the domain, so a
                legacy action naming its own entity works without a
                global HA_ENTITY_ID.

        Returns:
            dict: ``{"domain", "service", "serviceData"}``.

        Raises:
            ValueError: Unknown command, read-only domain, or bad argument.
        """
        spec = HUBITAT_COMMAND_MAP.get(command)
        if spec is None:
            raise ValueError(
                f"unsupported device command {command!r}; supported: "
                f"{', '.join(sorted(HUBITAT_COMMAND_MAP))}"
            )
        target = entity_id or self.entityId
        resolved_domain = (
            domain
            or (str(target).split(".")[0] if target else None)
        )
        if not resolved_domain:
            raise ValueError(
                "no target entity/domain configured (set HA_ENTITY_ID)"
            )

        service_data = {}
        service = spec["service"]

        if service == "update_entity":
            # ``update_entity`` lives on the ``homeassistant`` domain --
            # ``light.update_entity`` etc. do not exist and HA would 404.
            # It is also valid for read-only domains (it forces a re-poll
            # rather than commanding the device), so route it now and let
            # the read-only check below see the ``homeassistant`` domain.
            resolved_domain = "homeassistant"
        if resolved_domain in READ_ONLY_DOMAINS:
            raise ValueError(
                f"entity domain {resolved_domain!r} is read-only and "
                "accepts no commands"
            )

        if command == "setSwitch":
            wanted = value.get("state") if isinstance(value, dict) else value
            if wanted == "on":
                service = "turn_on"
            elif wanted == "off":
                service = "turn_off"
            else:
                raise ValueError("setSwitch requires state 'on' or 'off'")
        elif command == "setLevel":
            level = _to_number(value)
            if level is None or level < 0 or level > 100:
                raise ValueError("setLevel requires a level between 0 and 100")
            service_data["brightness_pct"] = round(level)
        elif command == "setHue":
            hue = _to_number(value)
            if hue is None or hue < 0 or hue > 100:
                raise ValueError("setHue requires a Hubitat hue between 0 and 100")
            # Hubitat hue is 0-100; HA hs_color hue is 0-360.
            service_data["hs_color"] = [round(hue * 3.6), 100]
        elif command == "setSaturation":
            sat = _to_number(value)
            if sat is None or sat < 0 or sat > 100:
                raise ValueError(
                    "setSaturation requires a saturation between 0 and 100"
                )
            service_data["hs_color"] = [0, round(sat)]
        elif command == "setColor":
            colour = value if isinstance(value, dict) else {}
            hue = _to_number(colour.get("hue"))
            sat = _to_number(colour.get("saturation"))
            if hue is None or sat is None:
                raise ValueError("setColor requires hue and saturation")
            service_data["hs_color"] = [round(hue * 3.6), round(sat)]
            level = _to_number(colour.get("level"))
            if level is not None:
                if level < 0 or level > 100:
                    raise ValueError("setColor level must be between 0 and 100")
                service_data["brightness_pct"] = round(level)
        elif command == "setColorTemperature":
            kelvin = _to_number(value)
            if kelvin is None or kelvin < 1000 or kelvin > 10000:
                raise ValueError(
                    "setColorTemperature requires a Kelvin value between "
                    "1000 and 10000"
                )
            service_data["kelvin"] = round(kelvin)
        elif command == "setColorHex":
            hex_value = (
                str(value.get("hex")) if isinstance(value, dict) else str(value or "")
            ).replace("#", "")
            if len(hex_value) != 6 or not all(
                char in "0123456789abcdefABCDEF" for char in hex_value
            ):
                raise ValueError(
                    "setColorHex requires a 6-digit RGB hex, e.g. 'FF0400'"
                )
            service_data["rgb_color"] = [
                int(hex_value[0:2], 16),
                int(hex_value[2:4], 16),
                int(hex_value[4:6], 16),
            ]

        return {"domain": resolved_domain, "service": service, "serviceData": service_data}

    @staticmethod
    def map_capability_domain(capability):
        """Map a legacy Hubitat capability onto a HA entity domain."""
        return HUBITAT_CAPABILITY_DOMAINS.get(capability)

    # -- REST surface -------------------------------------------------------------------
    def _fail(self, code, message, callback=None, **extra):
        """Build a failing :class:`CommandResult` (and invoke the callback)."""
        result = CommandResult(
            ok=False,
            code=code,
            entity_id=extra.get("entity_id"),
            domain=extra.get("domain"),
            service=extra.get("service"),
            service_data=extra.get("service_data"),
            status_code=extra.get("status_code"),
            message=message,
            error=extra.get("error", message),
            payload=extra.get("payload"),
            command=extra.get("command"),
        )
        logger.debug("home-assistant %s failed (%s): %s", extra.get("service"), code, message)
        if callback is not None:
            callback(result.error, result)
        return result

    def _transport(self, session=None):
        """Resolve the transport: per-call override > node session > module hook."""
        if session is not None:
            return session
        if self.session is not None:
            return self.session
        return globals().get("session")

    def _request(self, method, url, body=None, session=None):
        """Run one REST request against HA, returning a :class:`CommandResult`.

        ``ok`` means "HA answered 2xx"; the decoded body is in ``payload``.
        Transport and HTTP failures come back as ``ok=False`` with the
        matching ``code`` -- this never raises, so the dashboard cannot be
        taken down by a flaky hub.
        """
        import socket

        transport = self._transport(session)
        if transport is None:
            # No transport wired up: behave like the simulated sendRequest.
            logger.debug("home-assistant %s %s (no transport configured)", method, url)
            return CommandResult(
                ok=True,
                code="ok",
                message="simulated",
                payload=body,
            )
        request = getattr(transport, "request", None)
        try:
            if request is not None:
                try:
                    response = request(method, url, timeout=self.timeout)
                except TypeError:
                    # Transport without timeout support (older mock / helper).
                    response = request(method, url)
            else:
                response = transport.get(url, timeout=self.timeout)
        except (TimeoutError, socket.timeout) as exc:
            return self._fail(
                "timeout",
                "Home Assistant did not respond in time",
                error=str(exc) or "request timed out",
            )
        except Exception as exc:  # requests raises a broad family of errors
            name = exc.__class__.__name__
            if name in (
                "RequestException",
                "ConnectionError",
                "HTTPError",
                "URLError",
                "OSError",
            ):
                return self._fail(
                    "connection_error",
                    "Home Assistant is unreachable",
                    error=str(exc) or name,
                )
            return self._fail(
                "transport_error",
                "Unexpected error talking to Home Assistant",
                error=str(exc) or name,
            )

        status = getattr(response, "status_code", None)
        response_body = self._response_body(response)
        if isinstance(status, int) and not 200 <= status < 300:
            code = "auth_error" if status in (401, 403) else "http_error"
            message = (
                f"Home Assistant rejected the token (HTTP {status}) -- "
                "check HA_TOKEN (LLAT)"
                if code == "auth_error"
                else f"Home Assistant returned HTTP {status}"
            )
            return self._fail(
                code,
                message,
                status_code=status,
                error=self._response_error(response_body, status),
                payload=response_body,
            )
        return CommandResult(
            ok=True,
            code="ok",
            status_code=status,
            message="ok",
            payload=response_body,
        )

    @staticmethod
    def _validate_service_data(domain, service, service_data):
        """Validate/normalise service_data before it goes to HA.

        Uses the declared ``NUMERIC_RANGES`` so an out-of-range
        ``brightness_pct`` is rejected locally instead of surfacing as an
        opaque HA error.  Returns a normalised copy, or ``None`` when the
        input was empty/``None`` (nothing to validate).  Raises
        ``ValueError`` on bad input.
        """
        if not service_data:
            return None
        if not isinstance(service_data, dict):
            raise ValueError("service data must be a mapping of field names to values")
        spec = SUPPORTED_SERVICES.get(f"{domain}.{service}")
        allowed = list(spec["data"]) if spec else []
        normalised = {}
        for key, value in (service_data or {}).items():
            if key == "entity_id":
                # The target entity is set by the caller; a second id in
                # service_data is at best redundant, at worst conflicting.
                raise ValueError(
                    "service data may not carry 'entity_id' -- pass it as "
                    "the entity_id argument"
                )
            if allowed and key not in allowed:
                raise ValueError(
                    f"service {domain}.{service} does not accept "
                    f"{key!r}; accepted: {', '.join(allowed)}"
                )
            if key in NUMERIC_RANGES:
                number = _to_number(value)
                low, high = NUMERIC_RANGES[key]
                if number is None or number < low or number > high:
                    raise ValueError(
                        f"{key} must be a number between {low} and {high}"
                    )
                normalised[key] = round(number)
                continue
            if key in ("hs_color", "rgb_color"):
                if not isinstance(value, (list, tuple)) or not value:
                    raise ValueError(f"{key} must be a list of numbers")
                normalised[key] = list(value)
                continue
            normalised[key] = value
        return normalised

    def call_service(self, domain, service, entity_id=None, service_data=None,
                     callback=None, session=None):
        """Trigger a HA service via the REST API.

        ``POST /api/services/<domain>/<service>`` with
        ``Authorization: Bearer <LLAT>``.  ``service_data`` carries extra
        fields (``brightness_pct``, ``hs_color``, ...).

        Returns:
            CommandResult: Structured outcome; never raises for hub failures.
        """
        target = entity_id or self.entityId
        if not target:
            return self._fail(
                "missing_configuration",
                "no target entity configured (set HA_ENTITY_ID or pass entity_id)",
                callback=callback,
            )
        domain_of_target = str(target).split(".")[0]
        use_domain = domain or domain_of_target
        if not service:
            return self._fail(
                "invalid_argument",
                "a service name is required (e.g. turn_on)",
                callback=callback,
                entity_id=target,
                domain=use_domain,
            )
        if use_domain in READ_ONLY_DOMAINS:
            return self._fail(
                "read_only",
                f"entity domain {use_domain!r} is read-only and accepts no commands",
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
            )
        if (
            f"{use_domain}.{service}" not in SUPPORTED_SERVICES
            and f"homeassistant.{service}" not in SUPPORTED_SERVICES
        ):
            return self._fail(
                "unknown_service",
                f"unsupported service {use_domain}.{service}; supported: "
                f"{', '.join(sorted(SUPPORTED_SERVICES))}",
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
            )
        try:
            validated = self._validate_service_data(use_domain, service, service_data)
        except ValueError as exc:
            return self._fail(
                "invalid_argument",
                str(exc),
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
                service_data=service_data,
            )
        if validated is not None:
            service_data = validated
        try:
            url = self.rest_url(f"services/{use_domain}/{service}")
        except ValueError as exc:
            return self._fail(
                "missing_configuration",
                str(exc),
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
            )
        body = {"entity_id": target}
        if service_data:
            body.update(service_data)
        # A stray ``entity_id`` inside service_data must never override the
        # validated target -- drop it rather than send two conflicting ids.
        body["entity_id"] = target
        import json as _json

        transport = self._transport(session)
        if transport is None:
            # Simulated path (mirror of the JS sendRequest) -- no HTTP.
            logger.debug("home-assistant %s.%s (no transport configured)", use_domain, service)
            result = CommandResult(
                ok=True,
                code="ok",
                entity_id=target,
                domain=use_domain,
                service=service,
                service_data=service_data or {},
                message=f"{use_domain}.{service} simulated for {target} "
                "(no HTTP transport configured)",
            )
            self.send(
                {
                    "payload": result.to_dict(),
                    "topic": COMMAND_TOPIC_TEMPLATE.format(entity_id=target),
                }
            )
            if callback is not None:
                callback(None, result)
            return result
        try:
            request = getattr(transport, "request", None)
            if request is not None:
                try:
                    response = request(
                        "POST",
                        url,
                        timeout=self.timeout,
                        data=_json.dumps(body),
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json",
                        },
                    )
                except TypeError:
                    # Transport without keyword support (older mock / helper).
                    response = request("POST", url, body)
            else:
                response = transport.post(
                    url,
                    timeout=self.timeout,
                    data=_json.dumps(body),
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                )
        except (TimeoutError, OSError) as exc:
            return self._fail(
                "connection_error" if not isinstance(exc, TimeoutError) else "timeout",
                "Home Assistant is unreachable"
                if not isinstance(exc, TimeoutError)
                else "Home Assistant did not respond in time",
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
                service_data=service_data,
                error=str(exc) or exc.__class__.__name__,
            )
        except Exception as exc:
            name = exc.__class__.__name__
            return self._fail(
                "transport_error",
                "Unexpected error talking to Home Assistant",
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
                service_data=service_data,
                error=str(exc) or name,
            )

        status = getattr(response, "status_code", None)
        response_body = self._response_body(response)
        if isinstance(status, int) and not 200 <= status < 300:
            code = "auth_error" if status in (401, 403) else "http_error"
            message = (
                f"Home Assistant rejected the token (HTTP {status}) -- "
                "check HA_TOKEN (LLAT)"
                if code == "auth_error"
                else f"Home Assistant returned HTTP {status}"
            )
            return self._fail(
                code,
                message,
                callback=callback,
                entity_id=target,
                domain=use_domain,
                service=service,
                service_data=service_data,
                status_code=status,
                error=self._response_error(response_body, status),
                payload=response_body,
            )
        # A successful service call returns the new entity state(s).
        payload = response_body
        if isinstance(payload, list):
            for state in payload:
                if isinstance(state, dict) and state.get("entity_id"):
                    self.states[state["entity_id"]] = state
        elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
            for state in payload["data"]:
                if isinstance(state, dict) and state.get("entity_id"):
                    self.states[state["entity_id"]] = state
        result = CommandResult(
            ok=True,
            code="ok",
            entity_id=target,
            domain=use_domain,
            service=service,
            service_data=service_data or {},
            status_code=status,
            message=f"{use_domain}.{service} sent to {target}",
            payload=payload,
        )
        logger.info(
            "home-assistant %s.%s entity=%s status=%s",
            use_domain, service, target, status,
        )
        self.send(
            {
                "payload": result.to_dict(),
                "topic": COMMAND_TOPIC_TEMPLATE.format(entity_id=target),
            }
        )
        if callback is not None:
            callback(None, result)
        return result

    def get_states(self, callback=None, session=None):
        """Snapshot every entity state (REST twin of the WS ``get_states``)."""
        try:
            url = self.rest_url("states")
        except ValueError as exc:
            return self._fail("missing_configuration", str(exc), callback=callback)
        result = self._request("GET", url, session=session)
        if not result.ok:
            if callback is not None:
                callback(result.error, result)
            return result
        states = result.payload if isinstance(result.payload, list) else []
        for state in states:
            if isinstance(state, dict) and state.get("entity_id"):
                self.states[state["entity_id"]] = state
        self.status(
            {"fill": "green", "shape": "dot", "text": f"{len(states)} entities"}
        )
        if callback is not None:
            callback(None, states)
        return states

    def get_entity_state(self, entity_id, callback=None, session=None):
        """Fetch one entity's state (``GET /api/states/<entity_id>``)."""
        try:
            url = self.rest_url(f"states/{entity_id}")
        except ValueError as exc:
            return self._fail(
                "missing_configuration", str(exc), callback=callback,
                entity_id=entity_id,
            )
        result = self._request("GET", url, session=session)
        if not result.ok:
            if result.code == "http_error" and result.status_code == 404:
                result = CommandResult(
                    ok=False,
                    code="unknown_entity",
                    entity_id=entity_id,
                    status_code=404,
                    message=f"Home Assistant has no entity {entity_id!r}",
                    error=f"Home Assistant has no entity {entity_id!r}",
                )
            if callback is not None:
                callback(result.error, result)
            return result
        if isinstance(result.payload, dict) and result.payload.get("entity_id"):
            self.states[result.payload["entity_id"]] = result.payload
        if callback is not None:
            callback(None, result.payload)
        return result.payload

    def refresh_states(self):
        """Refresh the entity cache and publish the full state list."""
        def on_states(err, states):
            if err:
                return None
            self.send({"payload": states or [], "topic": "ha/states"})
            return None

        return self.get_states(on_states)

    # -- convenience power commands ---------------------------------------------
    def turn_on(self, entity_id=None, callback=None, service_data=None):
        """Turn an entity on (``light.turn_on`` / ``switch.turn_on``)."""
        return self.call_service(None, "turn_on", entity_id, service_data, callback)

    def turn_off(self, entity_id=None, callback=None, service_data=None):
        """Turn an entity off (``light.turn_off`` / ``switch.turn_off``)."""
        return self.call_service(None, "turn_off", entity_id, service_data, callback)

    def toggle(self, entity_id=None, callback=None):
        """Toggle an entity (``light.toggle`` / ``switch.toggle``)."""
        return self.call_service(None, "toggle", entity_id, None, callback)

    # -- dashboard control surface -------------------------------------------------
    def control_device(self, payload, callback=None, session=None):
        """Map a dashboard control action onto a HA service call.

        Accepts the native shape::

            {"entityId": "light.kitchen", "domain": "light",
             "service": "turn_on", "data": {...}}

        and the legacy Hubitat shape::

            {"deviceId": ..., "command": "on" | "setLevel" | ..., "value": ...}

        so existing widgets keep working after the migration.
        """
        action = payload
        if isinstance(action, dict) and isinstance(action.get("payload"), dict):
            action = action["payload"]  # Node-RED msg wrapper
        if not isinstance(action, dict):
            return self._fail(
                "invalid_payload",
                "expected a mapping with entityId/domain/service or deviceId/command",
                callback=callback,
            )

        if action.get("service"):
            # Native HA service call.
            return self.call_service(
                action.get("domain"),
                action["service"],
                action.get("entityId") or action.get("entity_id") or self.entityId,
                action.get("data") or action.get("service_data") or {},
                callback,
                session=session,
            )

        # Legacy Hubitat command mapping.
        entity_id = (
            action.get("entityId")
            or action.get("entity_id")
            or action.get("deviceId")
            or self.entityId
        )
        command = action.get("command")
        if not command:
            return self._fail(
                "unknown_command",
                "no service or command given",
                callback=callback,
                entity_id=entity_id,
            )
        try:
            mapped = self.map_hubitat_command(
                command,
                action.get("value"),
                action.get("domain"),
                entity_id=entity_id,
            )
        except ValueError as exc:
            return self._fail(
                "invalid_argument",
                str(exc),
                callback=callback,
                entity_id=entity_id,
                command=command,
            )
        return self.call_service(
            mapped["domain"],
            mapped["service"],
            entity_id,
            mapped["serviceData"],
            callback,
            session=session,
        )

    def send_request(self, method, url, data, callback=None):
        """Simulated HTTP request -- responds with a canned success payload."""
        response = {
            "success": True,
            "statusCode": 200,
            "body": data or {},
            "message": "Home Assistant request completed (simulated)",
        }
        if callback is not None:
            callback(None, response)
        return response

    @staticmethod
    def _response_body(response):
        """Decode a transport response body into JSON when possible."""
        if isinstance(response, dict):
            return response
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            for method in ("json",):
                reader = getattr(response, method, None)
                if callable(reader):
                    try:
                        return reader()
                    except Exception:
                        return None
            return None
        return _parse_json(text)

    @staticmethod
    def _response_error(body, status):
        """Build a readable error string from an HA error body."""
        if isinstance(body, dict):
            for key in ("error", "message", "error_description", "detail"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
        return f"HTTP {status}"


#: Dashboard-facing alias: wire a ``home-assistant-control`` node's input
#: straight to this method so a UI action maps onto a HA service call.
#: (Class-level alias -- the JS module does the same on the prototype.)
HomeAssistantNode.handle_control = HomeAssistantNode.control_device

#: Module-level handle for the flow's route wiring (unbound).
handle_control = HomeAssistantNode.control_device

#: Name used by the Node-RED flow registration and the tests.
HOME_ASSISTANT_NODE = HomeAssistantNode


__all__ = [
    "HOME_ASSISTANT_NODE",
    "HomeAssistantNode",
    "CommandResult",
    "SUPPORTED_SERVICES",
    "HUBITAT_COMMAND_MAP",
    "HUBITAT_CAPABILITY_DOMAINS",
    "READ_ONLY_DOMAINS",
    "handle_control",
]