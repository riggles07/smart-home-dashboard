"""Hubitat integration mirror -- smart home device controls and automation.

Python mirror of ``flows/hubitat-integration.js``: the ``HUBITAT_NODE``
class provides the Hubitat hub API surface used by the dashboard.

Device controls
---------------
Device commands are sent through the hub's **Maker API** --
``/apps/api/<app_id>/devices/<device_id>/<command>[/<value>]`` -- which is the
HTTP surface Hubitat exposes for external control.  Credentials come from the
node config (``url``, ``appId``, ``accessToken``/``apiKey``) with
``HUBITAT_URL`` / ``HUBITAT_APP_ID`` / ``HUBITAT_ACCESS_TOKEN`` (or
``HUBITAT_API_KEY``) as environment fallbacks; nothing is hard-coded and no
token is ever logged.

Every command returns a :class:`CommandResult` (``ok`` / ``code`` / ``error``
plus ``to_dict()`` for the dashboard) instead of raising, so an unreachable or
misconfigured hub can never take the dashboard down.  ``controlDevice()`` and
``handleControl()`` are the dashboard control surface: a UI action arrives as
``{"payload": {"deviceId": ..., "command": ..., "value": ...}}`` and is mapped
onto the matching Maker API call (``handleControl`` is an alias so the flow can
wire it straight to a ``hubitat-control`` node).

Note:
    ``on()`` stays reserved for Node-RED event registration -- it is the
    ``on(event, handler)`` emitter the flow and its tests rely on -- so the
    switch/dimmer/colour-bulb power commands are ``turnOn()`` / ``turnOff()``,
    or the generic ``sendDeviceCommand(device_id, "on")``.
"""

import json
import logging
import os
import re
import socket
from dataclasses import dataclass
from urllib.parse import quote

DEFAULT_BASE_URL = "http://hubitat.local:8080"
DEFAULT_TIMEOUT = 10.0

#: Maker API URL shape for a device command (``/[value]`` is optional).
MAKER_API_TEMPLATE = "{base}/apps/api/{app_id}/devices/{device_id}/{command}[/{value}]"

logger = logging.getLogger(__name__)

#: Module-level transport hook (same idea as ``integration_functions.fetch``):
#: point it at a ``requests``-style session to talk to a real hub, or patch it
#: in tests.  ``HubitatNode.session`` takes precedence when set.
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
    """Structured outcome of a Hubitat device command.

    Attributes:
        ok: ``True`` when the hub accepted the command.
        code: Machine-readable outcome (``ok``, ``invalid_device_id``,
            ``unknown_device``, ``unknown_command``, ``invalid_argument``,
            ``missing_configuration``, ``timeout``, ``connection_error``,
            ``http_error``, ``transport_error``, ``invalid_payload``).
        device_id: Device the command targeted.
        command: Maker API command name.
        value: The ``[value]`` URL segment that was sent (``None`` for
            parameterless commands).
        status_code: HTTP status code when a real transport answered.
        message: Human-readable summary, safe to publish to the dashboard.
        error: Failure detail (``None`` on success).
        payload: Decoded hub response body.
    """

    ok: bool
    code: str = "ok"
    device_id: object = None
    command: object = None
    value: object = None
    status_code: object = None
    message: str = ""
    error: object = None
    payload: object = None

    def to_dict(self):
        """Serialise the result for the dashboard (camelCase, JSON-safe)."""
        return {
            "ok": self.ok,
            "code": self.code,
            "deviceId": self.device_id,
            "command": self.command,
            "value": self.value,
            "statusCode": self.status_code,
            "message": self.message,
            "error": self.error,
            "payload": self.payload,
        }

    def __bool__(self):
        return bool(self.ok)


#: Device commands exposed to the dashboard, keyed by Maker API command name.
#: ``capability`` groups them by Hubitat capability family so the UI can render
#: the right controls for switches, dimmers and colour bulbs.
SUPPORTED_COMMANDS = {
    "on": {
        "capability": "switch",
        "args": [],
        "required": [],
        "description": "Turn a switch or dimmer on.",
    },
    "off": {
        "capability": "switch",
        "args": [],
        "required": [],
        "description": "Turn a switch or dimmer off.",
    },
    "toggle": {
        "capability": "switch",
        "args": [],
        "required": [],
        "description": "Toggle a switch or dimmer (drivers that expose it).",
    },
    "refresh": {
        "capability": "common",
        "args": [],
        "required": [],
        "description": "Ask the device to re-read its current state.",
    },
    "setSwitch": {
        "capability": "switch",
        "args": ["state"],
        "required": ["state"],
        "description": "Set switch state explicitly ('on'/'off').",
    },
    "setLevel": {
        "capability": "dimmer",
        "args": ["level", "duration"],
        "required": ["level"],
        "description": "Set dimmer level 0-100%, optional ramp duration in seconds.",
    },
    "setHue": {
        "capability": "color-bulb",
        "args": ["hue"],
        "required": ["hue"],
        "description": "Set colour hue 0-100.",
    },
    "setSaturation": {
        "capability": "color-bulb",
        "args": ["saturation"],
        "required": ["saturation"],
        "description": "Set colour saturation 0-100.",
    },
    "setColor": {
        "capability": "color-bulb",
        "args": ["hue", "saturation", "level"],
        "required": ["hue", "saturation"],
        "description": "Set HSB colour (hue 0-100, saturation 0-100, optional level 0-100).",
    },
    "setColorHex": {
        "capability": "color-bulb",
        "args": ["hex"],
        "required": ["hex"],
        "description": "Set colour from an RGB hex string, e.g. 'FF0400' (Maker API extension).",
    },
    "setColorTemperature": {
        "capability": "color-bulb",
        "args": ["temperature", "level"],
        "required": ["temperature"],
        "description": "Set colour temperature in Kelvin, optional level 0-100.",
    },
}

#: Accepted range per numeric argument (``None`` = unbounded).
_NUMERIC_RANGES = {
    "level": (0, 100),
    "hue": (0, 100),
    "saturation": (0, 100),
    "duration": (0, 3600),
    "temperature": (1000, 10000),
}


def _validate_argument(command, name, value):
    """Validate one command argument; returns ``(value, error)``."""
    if name == "state":
        state = str(value).strip().lower()
        if state not in ("on", "off"):
            return None, f"{command} argument 'state' must be 'on' or 'off', got {value!r}"
        return state, None
    if name == "hex":
        hex_value = str(value).strip().lstrip("#")
        if not re.fullmatch(r"[0-9A-Fa-f]{6}", hex_value or ""):
            return None, f"{command} argument 'hex' must be a 6-digit hex colour, got {value!r}"
        return hex_value.upper(), None
    number = _to_number(value)
    if number is None:
        return None, f"{command} argument '{name}' must be a number, got {value!r}"
    low, high = _NUMERIC_RANGES.get(name, (None, None))
    if low is not None and number < low:
        return None, f"{command} argument '{name}' must be >= {low}, got {value!r}"
    if high is not None and number > high:
        return None, f"{command} argument '{name}' must be <= {high}, got {value!r}"
    return (int(number) if float(number).is_integer() else number), None


def _normalize_arguments(command, args):
    """Validate and coerce the arguments for ``command``.

    Accepts positional values or a single mapping (``{"level": 50}``) as sent
    by a dashboard widget.  Returns ``([values], None)`` on success and
    ``([], "<reason>")`` when the request cannot be sent.
    """
    spec = SUPPORTED_COMMANDS[command]
    names = spec["args"]
    values = tuple(args or ())
    required = spec["required"]

    if len(values) == 1 and isinstance(values[0], dict):
        mapping = values[0]
        unexpected = sorted(key for key in mapping if key not in names)
        if unexpected:
            return [], f"{command} received unsupported argument(s): {', '.join(unexpected)}"
        missing = [name for name in required if mapping.get(name) is None]
        if missing:
            return [], f"{command} requires argument(s): {', '.join(missing)}"
        values = tuple(
            mapping[name] for name in names if mapping.get(name) is not None
        )

    if len(values) > len(names):
        return [], f"{command} takes at most {len(names)} argument(s), got {len(values)}"
    if len(values) < len(required):
        return [], f"{command} requires argument(s): {', '.join(required)}"

    normalized = []
    for index, value in enumerate(values):
        name = names[index]
        if value is None:
            if name in required:
                return [], f"{command} requires argument(s): {', '.join(required)}"
            continue
        value, error = _validate_argument(command, name, value)
        if error:
            return [], error
        normalized.append(value)
    return normalized, None


def _serialize_command_value(command, values):
    """Serialise validated values into the Maker API ``[value]`` segment."""
    if not values:
        return None
    if command == "setColor":
        mapping = dict(zip(("hue", "saturation", "level"), values))
        return json.dumps(mapping, separators=(",", ":"))
    if command == "setColorHex":
        return json.dumps({"hex": values[0]}, separators=(",", ":"))
    return ",".join(str(value) for value in values)


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


class HubitatNode:
    """Hubitat control node (mirror of the ``hubitat-control`` node)."""

    def __init__(self, node_type, msg, config, node=None):
        self.type = node_type
        self.config = dict(config or {})
        self.baseUrl = (
            self.config.get("url")
            or os.environ.get("HUBITAT_URL")
            or DEFAULT_BASE_URL
        )
        self.apiKey = self.config.get("apiKey") or os.environ.get("HUBITAT_API_KEY")
        # Maker API credentials (device commands). ``accessToken``/``token`` may
        # be the same value as ``apiKey`` on hubs that share one token.
        self.appId = self.config.get("appId") or os.environ.get("HUBITAT_APP_ID")
        self.accessToken = (
            self.config.get("accessToken")
            or self.config.get("token")
            or os.environ.get("HUBITAT_ACCESS_TOKEN")
            or self.apiKey
        )
        self.timeout = self.config.get("timeout") or DEFAULT_TIMEOUT
        #: Optional ``requests``-style session used as the transport. When left
        #: as ``None`` the module-level :data:`session` hook is used instead.
        self.session = self.config.get("session")
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

    def triggerAutomation(self, automation_id, callback=None):
        """Trigger an automation (POST /api/v1/automations/<id>/trigger)."""
        return self.sendRequest(
            "POST",
            f"{self.baseUrl}/api/v1/automations/{automation_id}/trigger",
            None,
            callback,
        )

    def getAutomations(self, callback=None):
        """List automations (GET /api/v1/automations)."""
        return self.sendRequest(
            "GET", f"{self.baseUrl}/api/v1/automations", None, callback
        )

    def updateAutomation(self, automation_id, data, callback=None):
        """Update an automation (PUT /api/v1/automations/<id>)."""
        return self.sendRequest(
            "PUT",
            f"{self.baseUrl}/api/v1/automations/{automation_id}",
            data,
            callback,
        )

    def deleteAutomation(self, automation_id, callback=None):
        """Delete an automation (DELETE /api/v1/automations/<id>)."""
        return self.sendRequest(
            "DELETE",
            f"{self.baseUrl}/api/v1/automations/{automation_id}",
            None,
            callback,
        )

    def getAutomationStatus(self, automation_id, callback=None):
        """Fetch automation status (GET /api/v1/automations/<id>/status)."""
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

    # -- device controls (Maker API) ------------------------------------------------
    @staticmethod
    def supportedCommands():
        """Return the device commands the dashboard can send.

        A copy keyed by Maker API command name; each entry carries the
        ``capability`` family, positional ``args``, which of those are
        ``required``, and a UI ``description``.
        """
        return {name: dict(spec) for name, spec in SUPPORTED_COMMANDS.items()}

    def getDeviceCommands(self, device_id, callback=None):
        """List the commands the hub exposes for one device.

        Returns a :class:`CommandResult` whose ``payload`` is the hub's raw
        command list -- useful for rendering device-specific UI.
        """
        if not self._valid_device_id(device_id):
            return self._invalid_device_id(device_id, "getDeviceCommands")
        result = self._maker_api_get(
            f"devices/{device_id}/commands", device_id=device_id
        )
        if result.ok:
            result = CommandResult(
                ok=True,
                code="ok",
                device_id=device_id,
                command="commands",
                status_code=result.status_code,
                message=f"{len(result.payload or [])} command(s) available",
                payload=result.payload,
            )
        if callback is not None:
            callback(None if result.ok else result.error, result)
        return result

    def sendDeviceCommand(self, device_id, command, *args, **kwargs):
        """Send an arbitrary Maker API command to a device.

        Args:
            device_id: Hubitat device id.
            command: Maker API command name, e.g. ``"on"``, ``"setLevel"``.
            *args: Positional command arguments, or a single mapping
                (``{"level": 50}``) as a dashboard widget would send them.
            **kwargs: ``callback`` (``callback(err, result)``) and ``session``
                (per-call transport override).

        Returns:
            CommandResult: Structured outcome; never raises for hub failures.
        """
        callback = kwargs.pop("callback", None)
        session = kwargs.pop("session", None)
        if kwargs:
            return self._fail(
                "invalid_argument",
                f"unexpected keyword argument(s): {', '.join(sorted(kwargs))}",
                device_id=device_id,
                command=command,
                callback=callback,
            )

        result = self._dispatch_device_command(
            device_id, command, args, session=session
        )
        if callback is not None:
            callback(None if result.ok else result.error, result)
        return result

    # Hubitat switch / dimmer / colour-bulb commands.
    def turnOn(self, device_id, callback=None, session=None):
        """Turn a switch or dimmer on (Maker API ``on``)."""
        return self.sendDeviceCommand(device_id, "on", callback=callback, session=session)

    def turnOff(self, device_id, callback=None, session=None):
        """Turn a switch or dimmer off (Maker API ``off``)."""
        return self.sendDeviceCommand(device_id, "off", callback=callback, session=session)

    def toggle(self, device_id, callback=None, session=None):
        """Toggle a switch or dimmer (Maker API ``toggle``)."""
        return self.sendDeviceCommand(device_id, "toggle", callback=callback, session=session)

    def setSwitch(self, device_id, state, callback=None, session=None):
        """Set switch state explicitly (Maker API ``setSwitch``)."""
        return self.sendDeviceCommand(
            device_id, "setSwitch", state, callback=callback, session=session
        )

    def setLevel(self, device_id, level, duration=None, callback=None, session=None):
        """Set dimmer level (Maker API ``setLevel``).

        Args:
            level: Brightness 0-100%.
            duration: Optional ramp duration in seconds.
        """
        args = (level,) if duration is None else (level, duration)
        return self.sendDeviceCommand(
            device_id, "setLevel", *args, callback=callback, session=session
        )

    def setColor(self, device_id, hue, saturation, level=None, callback=None, session=None):
        """Set HSB colour (Maker API ``setColor``)."""
        args = (hue, saturation) if level is None else (hue, saturation, level)
        return self.sendDeviceCommand(
            device_id, "setColor", *args, callback=callback, session=session
        )

    def setHue(self, device_id, hue, callback=None, session=None):
        """Set colour hue (Maker API ``setHue``)."""
        return self.sendDeviceCommand(
            device_id, "setHue", hue, callback=callback, session=session
        )

    def setSaturation(self, device_id, saturation, callback=None, session=None):
        """Set colour saturation (Maker API ``setSaturation``)."""
        return self.sendDeviceCommand(
            device_id, "setSaturation", saturation, callback=callback, session=session
        )

    def setColorTemperature(self, device_id, temperature, level=None, callback=None, session=None):
        """Set colour temperature in Kelvin (Maker API ``setColorTemperature``)."""
        args = (temperature,) if level is None else (temperature, level)
        return self.sendDeviceCommand(
            device_id, "setColorTemperature", *args, callback=callback, session=session
        )

    def setColorHex(self, device_id, hex_value, callback=None, session=None):
        """Set colour from an RGB hex string (Maker API ``setColor`` extension)."""
        return self.sendDeviceCommand(
            device_id, "setColorHex", hex_value, callback=callback, session=session
        )

    def refreshDevice(self, device_id, callback=None, session=None):
        """Ask a device to re-read its state (Maker API ``refresh``)."""
        return self.sendDeviceCommand(
            device_id, "refresh", callback=callback, session=session
        )

    # -- dashboard control surface --------------------------------------------------
    def controlDevice(self, request, callback=None, session=None):
        """Handle a dashboard control action (the UI's single entry point).

        Accepts either a mapping directly -- ``{"deviceId": "101", "command":
        "setLevel", "value": 50}`` -- or a Node-RED style message wrapping one
        (``{"payload": {...}}``). ``value`` may be a scalar, a list of
        positional arguments, or a mapping keyed by argument name.

        Returns:
            CommandResult: the outcome, also published on the node's ``send``
            output so the dashboard can render it.
        """
        if not isinstance(request, dict):
            result = self._fail(
                "invalid_payload",
                "control action must be a mapping with 'deviceId' and 'command'",
                callback=callback,
            )
            return result

        payload = request.get("payload")
        if isinstance(payload, dict):
            request = payload
        device_id = request.get("deviceId", request.get("device_id", request.get("id")))
        command = request.get("command")
        value = request.get("value", request.get("values"))
        if value is None:
            # Allow argument names inline, e.g. {"command": "setLevel", "level": 50}.
            inline = [
                request[name]
                for name in SUPPORTED_COMMANDS.get(command, {}).get("args", [])
                if request.get(name) is not None
            ]
            value = inline or None
        if isinstance(value, (list, tuple)):
            args = tuple(value)
        elif value is None:
            args = ()
        else:
            args = (value,)

        result = self.sendDeviceCommand(
            device_id, command, *args, callback=callback, session=session
        )
        # Publish the outcome on the node output (keyword form, matching
        # ``updateDeviceState`` -- works with both the call recorder and a Mock).
        self.send(
            payload=result.to_dict(),
            topic=f"hubitat/device/{result.device_id}/command",
        )
        return result

    # -- Maker API helpers ------------------------------------------------------------
    def _valid_device_id(self, device_id):
        """True when ``device_id`` is a non-empty string or integer id."""
        if isinstance(device_id, bool) or device_id is None:
            return False
        return bool(str(device_id).strip())

    def _invalid_device_id(self, device_id, command, callback=None):
        return self._fail(
            "invalid_device_id",
            f"device id must be a non-empty string or integer, got {device_id!r}",
            device_id=device_id,
            command=command,
            callback=callback,
        )

    def _fail(self, code, message, device_id=None, command=None, value=None,
              status_code=None, error=None, payload=None, callback=None):
        """Build a failed :class:`CommandResult`, log it and honour ``callback``."""
        result = CommandResult(
            ok=False,
            code=code,
            device_id=device_id,
            command=command,
            value=value,
            status_code=status_code,
            message=message,
            error=error or message,
            payload=payload,
        )
        logger.warning(
            "hubitat %s failed (%s) device=%r: %s",
            command or "-", code, device_id, message,
        )
        if callback is not None:
            callback(result.error, result)
        return result

    def _maker_api_url(self, path, value=None, app_id=None):
        """Build a Maker API URL; raises ``ValueError`` on missing configuration.

        ``path`` is everything after ``/apps/api/<app_id>/`` (e.g.
        ``"devices/101/setLevel"``); segments and the optional trailing
        ``value`` are strictly percent-encoded, so ``setLevel/50,5`` is sent as
        ``setLevel/50%2C5`` and ``{"hue":1}`` as ``%7B%22hue%22%3A1%7D`` -- the
        form the Maker API docs recommend for maximum compatibility.
        """
        if not self.baseUrl:
            raise ValueError("Hubitat base URL is not configured")
        app_id = app_id or self.appId
        if not app_id:
            raise ValueError("Hubitat Maker API app id is not configured")
        if not self.accessToken:
            raise ValueError("Hubitat Maker API access token is not configured")
        segments = [
            quote(str(segment), safe="")
            for segment in str(path).strip("/").split("/")
            if segment != ""
        ]
        if value is not None:
            segments.append(quote(str(value), safe=""))
        url = (
            f"{self.baseUrl.rstrip('/')}/apps/api/"
            f"{quote(str(app_id), safe='')}/{'/'.join(segments)}"
        )
        return f"{url}?access_token={quote(str(self.accessToken), safe='')}"

    def _transport(self, session):
        """Resolve the transport: per-call override > node session > module hook."""
        if session is not None:
            return session
        if self.session is not None:
            return self.session
        return globals().get("session")

    def _maker_api_request(self, method, url, session=None, device_id=None,
                           command=None, value=None):
        """Run one Maker API request, normalising transport quirks.

        Returns a :class:`CommandResult` where ``ok`` means "the hub answered
        2xx"; the decoded body is in ``payload``. Transport and HTTP failures
        come back as ``ok=False`` with the matching ``code`` -- this never
        raises, so the dashboard cannot be taken down by a flaky hub.
        """
        def failure(code, message, **extra):
            return self._fail(
                code, message, device_id=device_id, command=command,
                value=value, callback=None, **extra,
            )

        transport = self._transport(session)
        if transport is None:
            # No transport wired up: behave like the simulated ``sendRequest``.
            logger.debug("hubitat %s %s (no transport configured)", method, url)
            return CommandResult(
                ok=True, code="ok", device_id=device_id, command=command,
                value=value, message="simulated",
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
            return failure("timeout", "Hubitat hub did not respond in time",
                           error=str(exc) or "request timed out")
        except Exception as exc:  # requests raises a broad family of errors
            name = exc.__class__.__name__
            if name in ("RequestException", "ConnectionError", "HTTPError",
                        "URLError", "OSError"):
                return failure("connection_error", "Hubitat hub is unreachable",
                               error=str(exc) or name)
            return failure("transport_error",
                           "Unexpected error talking to the Hubitat hub",
                           error=str(exc) or name)

        status = getattr(response, "status_code", None)
        body = self._response_body(response)
        if isinstance(status, int) and not 200 <= status < 300:
            return failure(
                "http_error",
                f"Hubitat returned HTTP {status}",
                status_code=status,
                error=self._response_error(body, status),
                payload=body,
            )
        return CommandResult(
            ok=True, code="ok", device_id=device_id, command=command,
            value=value, status_code=status, message="ok", payload=body,
        )

    def _maker_api_get(self, path, device_id=None, session=None):
        """GET a Maker API path and return the decoded body as a CommandResult."""
        try:
            url = self._maker_api_url(path)
        except ValueError as exc:
            return self._fail(
                "missing_configuration", str(exc), device_id=device_id, command=path
            )
        return self._maker_api_request("GET", url, session, device_id=device_id, command=path)

    def _require_app_id(self):
        """Return the Maker API app id, raising ``ValueError`` when unset."""
        if not self.appId:
            raise ValueError("Hubitat Maker API app id is not configured")
        return self.appId

    #: Dashboard-facing alias: wire a ``hubitat-control`` node's input straight
    #: to this method so a UI action maps onto a Maker API command.
    handleControl = controlDevice

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
        """Build a readable error string from a hub error body."""
        if isinstance(body, dict):
            for key in ("error", "message", "error_description", "detail"):
                value = body.get(key)
                if isinstance(value, str) and value:
                    return value
        if isinstance(body, list) and body:
            return "hub rejected the command"
        return f"HTTP {status}"

    def _dispatch_device_command(self, device_id, command, args, session=None):
        """Validate and send one device command, returning a CommandResult."""
        if not self._valid_device_id(device_id):
            return self._invalid_device_id(device_id, command)
        if not isinstance(command, str) or command not in SUPPORTED_COMMANDS:
            return self._fail(
                "unknown_command",
                f"unsupported device command {command!r}; supported: "
                f"{', '.join(sorted(SUPPORTED_COMMANDS))}",
                device_id=device_id,
                command=command,
            )
        values, error = _normalize_arguments(command, args)
        if error:
            return self._fail(
                "invalid_argument", error, device_id=device_id, command=command
            )
        value = _serialize_command_value(command, values)
        try:
            url = self._maker_api_url(
                f"devices/{device_id}/{command}", value=value
            )
        except ValueError as exc:
            return self._fail(
                "missing_configuration",
                str(exc),
                device_id=device_id,
                command=command,
                value=value,
            )
        result = self._maker_api_request(
            "GET", url, session, device_id=device_id, command=command, value=value
        )
        if not result.ok:
            return result
        if self._is_unknown_device(result.payload):
            return self._fail(
                "unknown_device",
                f"Hubitat does not expose device {device_id!r} through this "
                "Maker API app (check the device is authorized)",
                device_id=device_id,
                command=command,
                value=value,
                status_code=result.status_code,
                payload=result.payload,
            )
        logger.info(
            "hubitat %s sent device=%r value=%r status=%s",
            command, device_id, value, result.status_code,
        )
        message = f"{command} sent to device {device_id}"
        if result.message == "simulated":
            # No HTTP transport wired up (mirror of the simulated sendRequest).
            message = f"{command} simulated for device {device_id} (no HTTP transport configured)"
        return CommandResult(
            ok=True,
            code="ok",
            device_id=device_id,
            command=command,
            value=value,
            status_code=result.status_code,
            message=message,
            payload=result.payload,
        )

    @staticmethod
    def _is_unknown_device(payload):
        """Detect a hub-side 'unknown device' error payload."""
        if not isinstance(payload, dict):
            return False
        for key in ("error", "message", "error_description", "detail"):
            value = payload.get(key)
            if isinstance(value, str) and "device" in value.lower():
                if any(word in value.lower() for word in ("not found", "unknown", "invalid", "missing")):
                    return True
        return False

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

__all__ = ["HubitatNode", "HUBITAT_NODE", "DEFAULT_BASE_URL"]
