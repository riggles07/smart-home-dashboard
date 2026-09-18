"""Hubitat integration mirror -- smart home device controls and automation.

Python mirror of ``flows/hubitat-integration.js``: the ``HUBITAT_NODE``
class provides the Hubitat hub API surface used by the dashboard.

Device state monitoring
-----------------------
Device state is read through the hub's **Maker API**
(``/apps/api/<app_id>/devices[...]``), the HTTP surface Hubitat exposes for
external integrations:

* ``GET /devices/all``  -- every authorized device with its ``attributes``.
* ``GET /devices/<id>`` -- one device, in the same shape.

Refresh strategy (hybrid, documented in ``docs/hubitat-state-monitoring.md``):

1. **Push first -- hub event subscription.** ``subscribeStateEvents(url)``
   registers a HTTP POST URL with the hub (``/postURL/<url>``); Maker API then
   POSTs every device event to the dashboard, so tiles update the moment
   something changes and the hub is not polled at all.
2. **TTL-cached polling as the fallback.** Push cannot be assumed: the hub may
   be LAN-only (no route back to the dashboard), the POST URL is cleared when
   the dashboard moves, and events that arrive while the dashboard restarts are
   lost. So a cached poll keeps things correct: ``startStatePolling()`` refreshes
   every ``state_poll_interval`` ms (default 60000, matching the JS flow's
   ``refresh || 60000``) and each read is served from a short-lived cache
   (``state_ttl`` seconds, default 5.0, matching the dashboard's 5000 ms UI
   refresh) so a 5-second tile refresh over N devices costs at most one
   ``/devices/all`` request per TTL window instead of N requests.

Every read degrades instead of raising: an unreachable hub, a non-2xx response
or a malformed payload comes back as a :class:`DeviceState` with ``ok=False``
(plus the last known good values flagged ``stale=True`` when available), is
logged once per state transition, and feeds an exponential back-off so a dead
hub is not hammered. Credentials come from the node config
(``url``/``appId``/``accessToken``/``apiKey``) with ``HUBITAT_*`` environment
fallbacks; no token is ever written to the log or published to the dashboard.
"""

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://hubitat.local:8080"

#: Seconds a state read may be served from cache before the hub is asked again.
DEFAULT_STATE_TTL = 5.0

#: Default poll interval (ms) for the polling fallback of the refresh strategy.
DEFAULT_STATE_POLL_MS = 60000

#: HTTP timeout (seconds) for a single Maker API state request.
DEFAULT_STATE_TIMEOUT = 10.0

#: Upper bound on cached devices, so a runaway hub cannot grow memory forever.
DEFAULT_STATE_MAX_ENTRIES = 500

#: Back-off bounds (seconds) applied after a failed poll of an unreachable hub.
STATE_BACKOFF_START = 5.0
STATE_BACKOFF_MAX = 60.0

#: Canonical attributes the dashboard renders on device tiles, in the priority
#: order used to pick a tile's primary reading. The hub reports more attributes
#: than these; the ones below cover switch/dimmer/colour-bulb, sensors and
#: thermostats.
STATE_ATTRIBUTES = (
    "switch",
    "level",
    "windowShade",
    "lock",
    "contact",
    "motion",
    "presence",
    "valve",
    "temperature",
    "humidity",
    "battery",
    "power",
    "energy",
    "voltage",
    "illuminance",
    "pressure",
    "acceleration",
    "water",
    "smoke",
    "carbonMonoxide",
    "colorTemperature",
    "colorMode",
    "hue",
    "saturation",
    "thermostatMode",
    "thermostatSetpoint",
    "heatingSetpoint",
    "coolingSetpoint",
    "thermostatOperatingState",
    "fanSpeed",
    "mode",
)

#: Display unit per attribute (``%`` for percentages, degrees for temperatures).
STATE_UNITS = {
    "level": "%",
    "battery": "%",
    "humidity": "%",
    "temperature": "°C",
    "temperatureF": "°F",
    "thermostatSetpoint": "°C",
    "heatingSetpoint": "°C",
    "coolingSetpoint": "°C",
    "power": "W",
    "energy": "kWh",
    "voltage": "V",
    "illuminance": "lx",
    "pressure": "kPa",
    "colorTemperature": "K",
}

#: String values that mean "yes"/"no" for the enumerated attributes.
BOOL_ATTRIBUTES = {
    "switch": {"on": True, "off": False},
    "motion": {"active": True, "inactive": False},
    "contact": {"open": True, "closed": False},
    "presence": {"present": True, "not present": False},
    "lock": {"locked": True, "unlocked": False},
    "valve": {"open": True, "closed": False},
    "acceleration": {"active": True, "inactive": False},
    "water": {"wet": True, "dry": False},
    "smoke": {"detected": True, "clear": False},
    "carbonMonoxide": {"detected": True, "clear": False},
    "windowShade": {"open": True, "closed": False, "partially open": True},
}

#: Outcome codes returned in ``DeviceState.code``.
STATE_OK = "ok"
STATE_MISSING_CONFIGURATION = "missing_configuration"
STATE_INVALID_DEVICE_ID = "invalid_device_id"
STATE_INVALID_PAYLOAD = "invalid_payload"
STATE_NOT_FOUND = "not_found"
STATE_TIMEOUT = "timeout"
STATE_CONNECTION_ERROR = "connection_error"
STATE_HTTP_ERROR = "http_error"
STATE_TRANSPORT_ERROR = "transport_error"

#: Marker attribute used to flag values carried over from the last good read.
STALE_MARKER = "_stale"

logger = logging.getLogger(__name__)

#: Module-level transport hook: point it at a ``requests``-style session (or any
#: object exposing ``request(method, url, timeout=)`` / ``get(url)``) to talk to
#: a real hub. ``HubitatNode.state_session`` takes precedence when set. State
#: reads never require a third-party dependency -- the default transport is
#: stdlib ``urllib``.
state_transport = None


def _state_json(text):
    """Parse a JSON body, returning ``None`` when it is empty or malformed."""
    if isinstance(text, (bytes, bytearray)):
        try:
            text = text.decode("utf-8", "replace")
        except Exception:  # pragma: no cover - decode fallback cannot fail
            return None
    if not isinstance(text, str) or not text.strip():
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _normalize_device_id(device_id):
    """Return ``device_id`` as a non-empty string, or ``None`` when invalid."""
    if device_id is None or isinstance(device_id, bool):
        return None
    text = str(device_id).strip()
    return text or None


def _is_non_finite(value):
    """True when ``value`` is (or parses to) a non-finite float (NaN/inf).

    Non-finite readings are not JSON-safe and render as garbage on a tile, so
    they are treated as "unknown" rather than presented as a number.
    """
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, float):
        return value != value or value in (float("inf"), float("-inf"))
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return False
        return number != number or number in (float("inf"), float("-inf"))
    return False


def _coerce_number(value):
    """Return ``value`` as ``int``/``float`` when numeric, else ``None``."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    # Reject NaN/infinity: they are not JSON-safe and render as garbage.
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return int(number) if number.is_integer() else number


def parse_state_value(attribute, value):
    """Coerce one raw hub attribute value into a dashboard-friendly value.

    Enumerated attributes (``switch``, ``motion``, ``contact``, ``lock``, ...)
    become booleans; numeric readings become ``int``/``float``; everything else
    (``thermostatMode``, ``colorMode``, ``fanSpeed``) is passed through as text.
    ``None`` is returned for values that cannot be interpreted (malformed
    payloads), so callers can tell "unknown" from "off".
    """
    if value is None:
        return None
    if _is_non_finite(value):
        # NaN/infinity are not JSON-safe; report as unknown rather than as a number.
        return None
    mapping = BOOL_ATTRIBUTES.get(attribute)
    if mapping is not None:
        if isinstance(value, bool):
            return value
        key = str(value).strip().lower()
        if key in mapping:
            return mapping[key]
        number = _coerce_number(value)
        if number is not None:
            return bool(number)
        return None
    if attribute in ("hue", "saturation", "level", "battery", "humidity"):
        number = _coerce_number(value)
        return number if number is not None else (str(value) or None)
    number = _coerce_number(value)
    if number is not None:
        return number
    text = str(value)
    return text if text else None


def format_state_display(attribute, value):
    """Render an attribute value for a device tile (``"on"``, ``"45%"``, ...)."""
    unit = STATE_UNITS.get(attribute, "")
    if attribute in BOOL_ATTRIBUTES:
        if value is True:
            # Prefer the hub's own wording where the mapping has an obvious word.
            return {
                "switch": "on",
                "motion": "active",
                "contact": "open",
                "presence": "present",
                "lock": "locked",
                "valve": "open",
                "acceleration": "active",
                "water": "wet",
                "smoke": "detected",
                "carbonMonoxide": "detected",
                "windowShade": "open",
            }.get(attribute, "on")
        if value is False:
            return {
                "switch": "off",
                "motion": "inactive",
                "contact": "closed",
                "presence": "not present",
                "lock": "unlocked",
                "valve": "closed",
                "acceleration": "inactive",
                "water": "dry",
                "smoke": "clear",
                "carbonMonoxide": "clear",
                "windowShade": "closed",
            }.get(attribute, "off")
        return "unknown"
    if value is None:
        return "unknown"
    if value == "":
        return "unknown"
    return f"{value}{unit}" if unit else str(value)


@dataclass
class DeviceState:
    """A snapshot of one device's attributes as reported by the hub.

    Attributes:
        device_id: Hubitat device id.
        ok: ``True`` when the snapshot came from a successful hub read (or a
            hub-pushed event); ``False`` when it is an error/fallback snapshot.
        code: Machine-readable outcome (see the ``STATE_*`` constants).
        name / label: Device name and dashboard label from the hub.
        attributes: Raw attribute values exactly as the hub reported them.
        values: Interpreted values (booleans for enumerated attributes).
        fetched_at: Wall-clock epoch seconds of the read (for display/age).
        monotonic_at: Monotonic clock reading, used for TTL freshness.
        source: ``hub``, ``event``, ``cache`` or ``fallback``.
        stale: ``True`` when the values are the last known good read carried
            over after a failed refresh.
        error: Failure detail, ``None`` on success.
    """

    device_id: str
    ok: bool = True
    code: str = STATE_OK
    name: object = None
    label: object = None
    attributes: dict = field(default_factory=dict)
    values: dict = field(default_factory=dict)
    fetched_at: float = 0.0
    monotonic_at: float = 0.0
    source: str = "hub"
    stale: bool = False
    error: object = None
    message: str = ""
    status_code: object = None
    payload: object = None

    def age(self, now=None):
        """Seconds since the snapshot was taken (``None`` when never fetched)."""
        if not self.monotonic_at:
            return None
        now = time.monotonic() if now is None else now
        return max(0.0, now - self.monotonic_at)

    def primary_attribute(self):
        """Return the attribute that best summarises the device.

        Walks :data:`STATE_ATTRIBUTES` in priority order and returns the first
        attribute the hub actually reported; ``None`` for an attribute-less
        snapshot.
        """
        for attribute in STATE_ATTRIBUTES:
            if attribute in self.attributes:
                return attribute
        return None

    def as_tile(self):
        """Render the snapshot as a dashboard tile dict (camelCase, JSON-safe)."""
        attribute = self.primary_attribute()
        raw = self.attributes.get(attribute) if attribute else None
        value = self.values.get(attribute) if attribute else None
        return {
            "deviceId": self.device_id,
            "label": self.label or self.name or self.device_id,
            "name": self.name,
            "ok": self.ok,
            "stale": self.stale,
            "code": self.code,
            "source": self.source,
            "ageSeconds": self.age(),
            "primary": None
            if attribute is None
            else {
                "attribute": attribute,
                "value": value,
                "raw": raw,
                "unit": STATE_UNITS.get(attribute, ""),
                "display": format_state_display(attribute, value),
                "on": value if isinstance(value, bool) else None,
            },
            "attributes": dict(self.attributes),
            "message": self.message,
            "error": self.error,
        }

    def to_dict(self):
        """Serialise the snapshot for the dashboard (camelCase, JSON-safe)."""
        return {
            "deviceId": self.device_id,
            "ok": self.ok,
            "code": self.code,
            "name": self.name,
            "label": self.label,
            "attributes": dict(self.attributes),
            "values": dict(self.values),
            "fetchedAt": self.fetched_at,
            "ageSeconds": self.age(),
            "source": self.source,
            "stale": self.stale,
            "message": self.message,
            "error": self.error,
        }

    def __bool__(self):
        return bool(self.ok)


def _state_from_device(payload, device_id=None, source="hub"):
    """Build a :class:`DeviceState` from a Maker API device object.

    Returns ``None`` when ``payload`` is not a device object at all (malformed
    payload), so callers can report ``invalid_payload`` rather than inventing an
    empty device.
    """
    if not isinstance(payload, dict):
        return None
    device = payload
    # Accept the ``{"device": {...}}`` wrapper some hub responses use.
    wrapped = payload.get("device")
    if isinstance(wrapped, dict):
        device = wrapped
    raw_attributes = device.get("attributes")
    if raw_attributes is None and "attribute" in device and "value" in device:
        # Single-attribute response: {"id":"123","attribute":"switch","value":"off"}
        raw_attributes = {device["attribute"]: device["value"]}
    if raw_attributes is None:
        # A bare ``/devices`` entry carries no attributes; keep it as an empty
        # snapshot only when the payload at least identifies a device.
        if "id" not in device and not device_id:
            return None
        raw_attributes = {}
    if not isinstance(raw_attributes, dict):
        return None
    if not raw_attributes and "id" not in device and device_id is None:
        return None

    resolved_id = _normalize_device_id(
        device.get("id", device.get("deviceId", device.get("device_id", device_id)))
    )
    if resolved_id is None:
        return None

    attributes = {}
    for key, value in raw_attributes.items():
        if isinstance(key, str) and key != STALE_MARKER:
            attributes[key] = value
    values = {name: parse_state_value(name, value) for name, value in attributes.items()}
    return DeviceState(
        device_id=resolved_id,
        ok=True,
        code=STATE_OK,
        name=device.get("name"),
        label=device.get("label", device.get("displayName")),
        attributes=attributes,
        values=values,
        fetched_at=time.time(),
        monotonic_at=time.monotonic(),
        source=source,
    )


class StateCache:
    """TTL cache of :class:`DeviceState` snapshots.

    The cache is what keeps the dashboard from hammering the hub: a 5-second
    tile refresh over N devices is served from here, and only the first read per
    TTL window reaches the hub. Hub-pushed events write through
    (:meth:`update_attribute`) so a subscribed dashboard stays live even while
    the polling cache is still fresh.

    Thread-safe: the poll loop and the dashboard's request handlers share one
    instance.
    """

    def __init__(self, ttl=DEFAULT_STATE_TTL, max_entries=DEFAULT_STATE_MAX_ENTRIES):
        self.ttl = float(ttl)
        self.max_entries = int(max_entries)
        self._entries = {}
        self._lock = threading.RLock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "stores": 0,
            "evictions": 0,
            "invalidations": 0,
            "events": 0,
        }

    # -- reads -----------------------------------------------------------------
    def is_fresh(self, device_id, now=None):
        """True when ``device_id`` has a cached snapshot inside the TTL window."""
        device_id = _normalize_device_id(device_id)
        if device_id is None:
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._entries.get(device_id)
            if state is None:
                return False
            return (now - state.monotonic_at) < self.ttl

    def get(self, device_id, allow_stale=False, now=None):
        """Return a cached snapshot, or ``None``.

        Args:
            device_id: Device to look up.
            allow_stale: Also return entries past their TTL (used to serve the
                last known good values after a failed refresh).
            now: Monotonic clock override (tests).
        """
        device_id = _normalize_device_id(device_id)
        if device_id is None:
            return None
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._entries.get(device_id)
            fresh = state is not None and (now - state.monotonic_at) < self.ttl
            if state is None or (not fresh and not allow_stale):
                self._stats["misses"] += 1
                return None
            self._stats["hits"] += 1
            return state

    # -- writes ----------------------------------------------------------------
    def put(self, state, now=None):
        """Store a snapshot; evicts the oldest entry past ``max_entries``."""
        if not isinstance(state, DeviceState):
            return None
        now = time.monotonic() if now is None else now
        with self._lock:
            if len(self._entries) >= self.max_entries and state.device_id not in self._entries:
                oldest = min(
                    self._entries.items(), key=lambda item: item[1].monotonic_at
                )[0]
                self._entries.pop(oldest, None)
                self._stats["evictions"] += 1
            if not state.monotonic_at:
                state.monotonic_at = now
            if not state.fetched_at:
                state.fetched_at = time.time()
            self._entries[state.device_id] = state
            self._stats["stores"] += 1
            return state

    def update_attribute(self, device_id, attribute, value, label=None, now=None):
        """Write one hub-pushed attribute through to the cache.

        Creates the entry when the device has not been read yet (a push can
        arrive before the first poll). Returns the updated snapshot, or ``None``
        for an invalid device id / attribute name.
        """
        device_id = _normalize_device_id(device_id)
        if device_id is None or not isinstance(attribute, str) or not attribute:
            return None
        if attribute == STALE_MARKER:
            return None
        now = time.monotonic() if now is None else now
        with self._lock:
            state = self._entries.get(device_id)
            if state is None:
                state = DeviceState(device_id=device_id, source="event")
            state.attributes[attribute] = value
            state.values[attribute] = parse_state_value(attribute, value)
            state.ok = True
            state.code = STATE_OK
            state.message = "ok"
            state.error = None
            state.stale = False
            state.source = "event"
            state.fetched_at = time.time()
            state.monotonic_at = now
            if label and not state.label:
                state.label = label
            self._entries[device_id] = state
            self._stats["events"] += 1
            return state

    def invalidate(self, device_id=None):
        """Drop one device's snapshot, or the whole cache when ``None``."""
        with self._lock:
            if device_id is None:
                removed = len(self._entries)
                self._entries.clear()
            else:
                device_id = _normalize_device_id(device_id)
                removed = 1 if self._entries.pop(device_id, None) is not None else 0
            self._stats["invalidations"] += removed
            return removed

    # -- introspection ---------------------------------------------------------
    def entries(self):
        """Shallow copy of the cached snapshots, keyed by device id."""
        with self._lock:
            return dict(self._entries)

    def stats(self):
        """Cache counters plus current size/TTL, for the dashboard."""
        with self._lock:
            data = dict(self._stats)
            data.update(
                {
                    "size": len(self._entries),
                    "ttlSeconds": self.ttl,
                    "maxEntries": self.max_entries,
                }
            )
            return data

    def __len__(self):
        with self._lock:
            return len(self._entries)

    def __contains__(self, device_id):
        return _normalize_device_id(device_id) in self.entries()


class _UrllibTransport:
    """Default transport: stdlib only, so no third-party dependency is required.

    Mirrors the ``requests`` surface the rest of the repo uses
    (``request(method, url, timeout=)`` plus ``.status_code``/``.text``/
    ``.json()`` on the response), so the same code path works with an injected
    ``requests.Session`` in production or a ``Mock`` in tests.
    """

    def request(self, method, url, timeout=None, **kwargs):
        """Perform one HTTP request and return a lightweight response object."""
        request = Request(url, method=method, headers={"Accept": "application/json"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return _UrllibResponse(response.status, response.read())
        except HTTPError as exc:  # non-2xx: still a response the caller inspects
            return _UrllibResponse(exc.code, exc.read())

    def get(self, url, timeout=None, **kwargs):
        """GET ``url``."""
        return self.request("GET", url, timeout=timeout)


class _UrllibResponse:
    """Minimal response object matching the ``requests`` attribute surface."""

    def __init__(self, status_code, body):
        self.status_code = status_code
        self.content = body or b""
        try:
            self.text = self.content.decode("utf-8", "replace")
        except Exception:  # pragma: no cover - decode("replace") cannot fail
            self.text = ""

    @property
    def ok(self):
        """True for a 2xx status."""
        return isinstance(self.status_code, int) and 200 <= self.status_code < 300

    def json(self):
        """Decoded JSON body (``None`` when it is not JSON)."""
        return _state_json(self.text)


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
        self.baseUrl = self.config.get("url") or DEFAULT_BASE_URL
        self.apiKey = self.config.get("apiKey")
        self.devices = []
        self.activeAutomations = []
        self.send = _CallRecorder()
        self.status = _CallRecorder()
        self._handlers = {}
        # Device state monitoring (lazy cache, so construction stays cheap).
        self.deviceStates = {}
        self.stateTtl = self.config.get("stateTtl")
        self.statePollInterval = self.config.get("statePollInterval")
        self.stateSubscriptionUrl = self.config.get("stateSubscriptionUrl")
        self.stateSession = None
        self._state_cache = None
        self._state_lock = threading.RLock()
        self._state_snapshot_at = 0.0
        self._state_last_refresh = None
        self._state_backoff = 0.0
        self._state_backoff_until = 0.0
        self._state_poll_thread = None
        self._state_poll_stop = None

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
        if event == "subscribe" and data.get("type") == "device-event":
            self.handleDeviceEvent(data)
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

    # -- device state monitoring ------------------------------------------------
    @property
    def state_cache(self):
        """The node's :class:`StateCache`, created on first use."""
        cache = self._state_cache
        if cache is None:
            with self._state_lock:
                cache = self._state_cache
                if cache is None:
                    cache = StateCache(ttl=self.state_ttl)
                    self._state_cache = cache
        return cache

    @property
    def state_ttl(self):
        """Cache TTL in seconds (``stateTtl`` config, else ``HUBITAT_STATE_TTL``)."""
        configured = self.stateTtl
        if configured is None:
            configured = os.environ.get("HUBITAT_STATE_TTL")
        if configured is None:
            return DEFAULT_STATE_TTL
        try:
            ttl = float(configured)
        except (TypeError, ValueError):
            return DEFAULT_STATE_TTL
        return ttl if ttl >= 0 else DEFAULT_STATE_TTL

    @property
    def state_poll_interval(self):
        """Poll interval in ms (``statePollInterval``, else ``HUBITAT_STATE_POLL_MS``)."""
        configured = self.statePollInterval
        if configured is None:
            configured = os.environ.get("HUBITAT_STATE_POLL_MS")
        if configured is None:
            return DEFAULT_STATE_POLL_MS
        try:
            interval = int(float(configured))
        except (TypeError, ValueError):
            return DEFAULT_STATE_POLL_MS
        return interval if interval > 0 else DEFAULT_STATE_POLL_MS

    @property
    def state_timeout(self):
        """HTTP timeout in seconds for a single state request."""
        configured = self.config.get("stateTimeout")
        if configured is None:
            configured = os.environ.get("HUBITAT_STATE_TIMEOUT")
        if configured is None:
            return DEFAULT_STATE_TIMEOUT
        try:
            timeout = float(configured)
        except (TypeError, ValueError):
            return DEFAULT_STATE_TIMEOUT
        return timeout if timeout > 0 else DEFAULT_STATE_TIMEOUT

    # .. credentials / URLs .....................................................
    @property
    def maker_api_url(self):
        """Maker API base URL (``http://<hub>/apps/api/<app_id>``).

        Accepts either a bare hub URL plus ``appId`` in the config, or a
        ``baseUrl`` that already points at a Maker API instance.
        """
        base = (self.baseUrl or "").rstrip("/")
        if not base:
            return None
        if "/apps/api/" in base:
            return base
        app_id = self.app_id
        if not app_id:
            return None
        return f"{base}/apps/api/{quote(str(app_id), safe='')}"

    @property
    def app_id(self):
        """Maker API app id (config ``appId``, else ``HUBITAT_APP_ID``)."""
        app_id = self.config.get("appId") or getattr(self, "appId", None)
        if not app_id:
            app_id = os.environ.get("HUBITAT_APP_ID")
        if not app_id:
            base = self.baseUrl or ""
            marker = "/apps/api/"
            if marker in base:
                app_id = base.split(marker, 1)[1].split("/", 1)[0]
        return app_id or None

    @property
    def access_token(self):
        """Maker API access token (config, else ``HUBITAT_*`` env, else apiKey)."""
        token = (
            self.config.get("accessToken")
            or self.config.get("token")
            or getattr(self, "accessToken", None)
        )
        if not token:
            token = os.environ.get("HUBITAT_ACCESS_TOKEN")
        if not token:
            token = self.apiKey or os.environ.get("HUBITAT_API_KEY")
        return token or None

    def state_url(self, path="", segment=None):
        """Build a Maker API URL; raises ``ValueError`` when unconfigured.

        Args:
            path: Slash-separated path after ``/apps/api/<app_id>/``; each
                segment is percent-encoded (``devices/101/attribute/switch``).
            segment: Extra *opaque* path segment appended after ``path`` and
                encoded as a whole, ``"/"`` and all. Needed by ``/postURL``,
                whose argument is a full URL that must stay one segment
                (encoding it twice would make the hub POST to a literal
                ``http%3A%2F%2F...`` URL).

        Raises:
            ValueError: Missing base URL, app id or access token. Callers turn
                this into a ``missing_configuration`` snapshot rather than
                letting it escape.
        """
        base = self.maker_api_url
        if not base:
            if self.baseUrl and not self.app_id:
                raise ValueError(
                    "Hubitat Maker API app id is not configured: set appId in "
                    "the node config, set HUBITAT_APP_ID, or point url at "
                    "http://<hub>/apps/api/<app_id>"
                )
            raise ValueError(
                "Hubitat Maker API is not configured (need url + appId, or a "
                "url already pointing at /apps/api/<app_id>)"
            )
        token = self.access_token
        if not token:
            raise ValueError(
                "Hubitat Maker API access token is not configured "
                "(set accessToken/apiKey in the node config, or "
                "HUBITAT_ACCESS_TOKEN / HUBITAT_API_KEY)"
            )
        segments = [
            quote(part, safe="")
            for part in str(path or "").strip("/").split("/")
            if part
        ]
        if segment is not None:
            segments.append(quote(str(segment), safe=""))
        url = f"{base}/{'/'.join(segments)}" if segments else base
        return f"{url}?access_token={quote(str(token), safe='')}"

    # .. single device ..........................................................
    def getDeviceState(self, device_id, force_refresh=False, session=None, callback=None):
        """Return the current state of one device.

        Served from the TTL cache when fresh (so the dashboard's 5-second tile
        refresh does not hammer the hub); otherwise read from the hub via
        ``GET /apps/api/<app>/devices/<id>`` and cached.

        Args:
            device_id: Hubitat device id.
            force_refresh: Bypass the cache and read from the hub.
            session: Optional per-call transport override.
            callback: Optional ``callback(err, state)``.

        Returns:
            DeviceState: On failure the snapshot has ``ok=False`` with the
            matching ``code``; if a previous good snapshot exists its values are
            carried over with ``stale=True`` so tiles can show last-known state
            instead of blanking out.
        """
        resolved = _normalize_device_id(device_id)
        if resolved is None:
            state = DeviceState(
                device_id=str(device_id),
                ok=False,
                code=STATE_INVALID_DEVICE_ID,
                source="fallback",
                stale=True,
                error=f"device id must be a non-empty string or integer, got {device_id!r}",
            )
            return self._finish_state(state, callback)

        cache = self.state_cache
        if not force_refresh:
            cached = cache.get(resolved)
            if cached is not None:
                return self._finish_state(cached, callback)

        result = self._state_get(f"devices/{resolved}", session=session, device_id=resolved)
        if result.ok:
            state = _state_from_device(result.payload, device_id=resolved)
            if state is None:
                return self._finish_state(
                    self._state_failure(
                        STATE_INVALID_PAYLOAD,
                        resolved,
                        "hub returned a payload that is not a device object",
                        error=result.payload,
                    ),
                    callback,
                )
            state.status_code = getattr(result, "status_code", None)
            cache.put(state)
            self.deviceStates[resolved] = state
            self._note_state_success()
            return self._finish_state(state, callback)

        return self._finish_state(self._state_failed_with_fallback(resolved, result), callback)

    def invalidateDeviceState(self, device_id):
        """Drop one device's cached state so the next read hits the hub."""
        return self.state_cache.invalidate(device_id)

    def clearStateCache(self):
        """Drop every cached snapshot."""
        return self.state_cache.invalidate(None)

    def stateCacheStats(self):
        """Cache counters plus refresh bookkeeping, for the dashboard."""
        stats = self.state_cache.stats()
        stats.update({"lastRefresh": self._state_last_refresh})
        return stats

    # .. all devices ............................................................
    def getAllDeviceStates(self, force_refresh=False, session=None, callback=None):
        """Return the state of every authorized device, keyed by device id.

        Uses the single ``GET /devices/all`` request (one call for the whole
        hub, rather than one per device) and falls back to per-device reads when
        the hub does not expose it. The all-device snapshot is itself cached for
        ``state_ttl`` seconds.

        Failures are per device: a device that cannot be read keeps its last
        known values flagged ``stale`` while the rest of the snapshot stays
        usable -- a partially broken hub never blanks the dashboard.

        Returns:
            dict: ``{device_id: DeviceState}`` (empty when the hub is
            unreachable and nothing is cached).
        """
        cache = self.state_cache
        now = time.monotonic()
        if not force_refresh and self._state_snapshot_at:
            if (now - self._state_snapshot_at) < self.state_ttl:
                snapshot = {
                    device_id: state for device_id, state in cache.entries().items()
                }
                if snapshot:
                    for state in snapshot.values():
                        state.source = "cache"
                    return self._finish_all(snapshot, callback)

        result = self._state_get("devices/all", session=session)
        states = {}
        failure = None
        if result.ok:
            devices = self._device_list(result.payload)
            if devices is None:
                result = self._state_failure(
                    STATE_INVALID_PAYLOAD,
                    None,
                    "hub returned a payload that is not a device list",
                    error=result.payload,
                )
            else:
                for device in devices:
                    state = _state_from_device(device)
                    if state is None:
                        logger.warning(
                            "hubitat: skipping malformed device entry in "
                            "/devices/all: %r",
                            type(device).__name__,
                        )
                        continue
                    cache.put(state)
                    states[state.device_id] = state

        if not result.ok:
            # Degrade to per-device reads, then to the last known snapshot.
            failure = result
            states = self._states_from_device_list(session=session)
            if not states:
                states = self._stale_entries(result)

        self._state_snapshot_at = time.monotonic()
        self.deviceStates = dict(states)
        self._state_last_refresh = time.time()
        if result.ok:
            self._note_state_success()
        else:
            self._note_state_failure()
        return self._finish_all(states, callback, failure)

    # .. dashboard status view ..................................................
    def refreshDeviceStates(self, force_refresh=False, session=None):
        """Refresh every device and publish the status view (dashboard entry point).

        This is what the dashboard's status view calls on its refresh tick: it
        fetches the snapshot, publishes each device on
        ``hubitat/device/<id>/state``, publishes the tile list on
        ``hubitat/devices/state``, and updates the node status indicator to
        green/red (with the stale count) so an unreachable hub is visible at a
        glance.

        Returns:
            dict: The status view (see :meth:`getStatusView`).
        """
        states = self.getAllDeviceStates(
            force_refresh=force_refresh, session=session
        )
        for state in states.values():
            self.send(
                payload=state.to_dict(),
                topic=f"hubitat/device/{state.device_id}/state",
            )
        view = self.status_view(states)
        self.status({
            "fill": self._status_fill(view),
            "shape": "dot",
            "text": f"{view['deviceCount']} devices"
            + (f", {view['staleCount']} stale" if view["staleCount"] else "")
            + (f", {view['errorCount']} failed" if view["errorCount"] and not view["staleCount"] else ""),
        })
        self.send(payload=view, topic="hubitat/devices/state")
        return view

    @staticmethod
    def _status_fill(view):
        """Pick the node status colour for a device-state view.

        * ``green``  -- every device read cleanly (no stale, no errors).
        * ``yellow`` -- degraded: some devices failed, or values are being
          served from cache because the hub is unreachable. The dashboard still
          has data worth showing, so this is a warning rather than a failure.
        * ``red``    -- nothing usable (no devices, or every read failed).
        """
        if view["deviceCount"] and not view["errorCount"] and not view["staleCount"]:
            return "green"
        if view["deviceCount"] and (view["staleCount"] or view["errorCount"] < view["deviceCount"]):
            return "yellow"
        return "red"

    def getStatusView(self, force_refresh=False, session=None):
        """Return the dashboard status view for device state.

        Shape: ``{"view", "title", "ok", "deviceCount", "staleCount",
        "errorCount", "lastRefresh", "refreshStrategy", "cache", "tiles"}`` where
        ``tiles`` is one :meth:`DeviceState.as_tile` dict per device, ready for
        the devices view of the dashboard.
        """
        states = self.getAllDeviceStates(
            force_refresh=force_refresh, session=session
        )
        return self.status_view(states)

    def status_view(self, states=None):
        """Build the status view dict from the node's current snapshot."""
        if states is None:
            states = self.deviceStates or self.state_cache.entries()
        tiles = [state.as_tile() for state in states.values()]
        stale_count = sum(1 for tile in tiles if tile["stale"])
        error_count = sum(1 for tile in tiles if not tile["ok"])
        return {
            "view": "devices",
            "title": "Device Status",
            "ok": error_count == 0 and not stale_count and bool(tiles),
            "deviceCount": len(tiles),
            "staleCount": stale_count,
            "errorCount": error_count,
            "lastRefresh": self._state_last_refresh,
            "refreshStrategy": self.stateRefreshStrategy(),
            "cache": self.stateCacheStats(),
            "tiles": tiles,
        }

    #: Alias kept for dashboard code that calls the view a "status".
    statusView = status_view

    def stateRefreshStrategy(self):
        """Describe the refresh strategy in force (documented, dashboard-visible)."""
        return {
            "mode": "hybrid",
            "primary": "hub-event-subscription",
            "fallback": "ttl-cached-polling",
            "pollIntervalMs": self.state_poll_interval,
            "cacheTtlSeconds": self.state_ttl,
            "subscriptionUrl": self.stateSubscriptionUrl,
            "subscriptionEnabled": bool(self.stateSubscriptionUrl),
            "polling": bool(self._state_poll_thread and self._state_poll_thread.is_alive()),
            "documentation": "docs/hubitat-state-monitoring.md",
        }

    # .. hub-pushed events ......................................................
    def handleDeviceEvent(self, payload):
        """Apply a hub-pushed device event to the state cache (push path).

        Accepts either the Maker API ``postURL`` body
        (``{"content": {"name": "switch", "value": "on", "deviceId": "101",
        ...}}``) or a flat ``{"deviceId": ..., "attribute"/"name": ...,
        "value": ...}`` mapping. The attribute is written straight through to
        the cache, so a subscribed dashboard reflects changes without polling.

        Returns:
            DeviceState: The updated snapshot, or ``None`` for a malformed event.
        """
        if not isinstance(payload, dict):
            logger.warning("hubitat: ignoring malformed device event of type %s",
                           type(payload).__name__)
            return None
        event = payload.get("content")
        if not isinstance(event, dict):
            event = payload

        device_id = _normalize_device_id(
            event.get(
                "deviceId",
                event.get("device_id", event.get("device", {}).get("id")
                          if isinstance(event.get("device"), dict) else None),
            )
        )
        attribute = event.get("name", event.get("attribute"))
        if device_id is None or not isinstance(attribute, str) or not attribute:
            logger.warning(
                "hubitat: ignoring device event without a device id/attribute: %r",
                sorted(event.keys()),
            )
            return None
        value = event.get("value")
        label = event.get("displayName") or event.get("label")
        state = self.state_cache.update_attribute(
            device_id, attribute, value, label=label
        )
        if state is None:
            return None
        self.deviceStates[device_id] = state
        self.send(
            payload=state.to_dict(),
            topic=f"hubitat/device/{device_id}/state",
        )
        logger.debug(
            "hubitat: event device=%s %s=%r", device_id, attribute, value
        )
        return state

    #: Node-RED-friendly alias.
    onDeviceEvent = handleDeviceEvent

    def subscribeStateEvents(self, url=None, session=None, clear=False):
        """Register the dashboard's HTTP POST URL with the hub (push path).

        Maker API then POSTs every device event to ``url``; ``/postURL`` is the
        Maker API endpoint that sets it.

        Args:
            url: URL the hub should POST events to. Defaults to the configured
                ``stateSubscriptionUrl``.
            session: Optional per-call transport override.
            clear: Remove the subscription instead of setting one
                (``/postURL`` with no argument stops the event stream).

        Returns:
            DeviceState: ``ok=True`` when the hub accepted the change (the
            ``payload`` holds the hub's response, when any).
        """
        target = None if clear else (url or self.stateSubscriptionUrl)
        if not clear and not target:
            return self._state_failure(
                STATE_MISSING_CONFIGURATION,
                None,
                "no state subscription URL configured (pass url= or set "
                "stateSubscriptionUrl / HUBITAT_STATE_SUBSCRIPTION_URL)",
            )
        # ``/postURL`` takes one opaque segment, so the URL is encoded once here
        # (``state_url`` must not encode it again).
        result = self._state_get(
            "postURL", session=session, segment=target
        )
        if result.ok:
            self.stateSubscriptionUrl = target
            logger.info(
                "hubitat: device event subscription %s",
                "cleared" if target is None else f"set to {target}",
            )
            return DeviceState(
                device_id="",
                ok=True,
                code=STATE_OK,
                source="hub",
                payload=getattr(result, "payload", None),
            )
        return self._state_failed_with_fallback(None, result)

    def clearStateEvents(self, session=None):
        """Stop the hub pushing device events (``/postURL`` with no URL)."""
        return self.subscribeStateEvents(session=session, clear=True)

    # .. polling fallback .......................................................
    def pollDeviceStates(self, force_refresh=False, session=None):
        """Run one poll tick (the fallback path), honouring failure back-off.

        While an unreachable hub is in back-off the tick is skipped, so a hub
        outage produces one attempt per back-off window instead of a request per
        dashboard refresh.

        Returns:
            dict: ``{}`` when skipped by back-off, else the fresh snapshot.
        """
        now = time.monotonic()
        if not force_refresh and now < self._state_backoff_until:
            logger.debug(
                "hubitat: state poll skipped, backing off for %.1fs",
                self._state_backoff_until - now,
            )
            return {}
        return self.getAllDeviceStates(force_refresh=True, session=session)

    def startStatePolling(self, stop_event=None, session=None):
        """Start the background poll loop (polling fallback of the strategy).

        Each tick calls :meth:`pollDeviceStates`. The loop stops when
        ``stop_event`` is set (Node-RED sets this on node close) or when
        :meth:`stopStatePolling` is called.

        Returns:
            threading.Thread: The (daemon) poll thread.
        """
        existing = self._state_poll_thread
        if existing is not None and existing.is_alive():
            return existing
        if stop_event is None:
            stop_event = threading.Event()
        self._state_poll_stop = stop_event
        thread = threading.Thread(
            target=self._state_poll_loop,
            args=(stop_event, session),
            name=f"hubitat-state-poll-{self.type}",
            daemon=True,
        )
        self._state_poll_thread = thread
        thread.start()
        logger.info(
            "hubitat: state polling started every %dms", self.state_poll_interval
        )
        return thread

    def stopStatePolling(self, timeout=None):
        """Stop the background poll loop and join it."""
        stop_event = self._state_poll_stop
        if stop_event is not None:
            stop_event.set()
        thread = self._state_poll_thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=timeout)
        self._state_poll_thread = None
        self._state_poll_stop = None
        return None

    def _state_poll_loop(self, stop_event, session=None):
        interval = max(0.05, self.state_poll_interval / 1000.0)
        while not stop_event.is_set():
            try:
                self.pollDeviceStates(session=session)
            except Exception:  # a poll must never kill the loop
                logger.exception("hubitat: unexpected error during state poll")
            stop_event.wait(interval)

    def setupStateMonitoring(self, force_refresh=True, session=None):
        """Wire up state monitoring the way the dashboard expects (one call).

        Subscribes to hub-pushed events when a subscription URL is configured,
        takes an initial snapshot so tiles are populated immediately, and starts
        the polling fallback. Returns the status view.
        """
        if self.stateSubscriptionUrl:
            result = self.subscribeStateEvents(session=session)
            if not result.ok:
                logger.warning(
                    "hubitat: could not set device event subscription (%s); "
                    "falling back to polling only",
                    result.code,
                )
        view = self.refreshDeviceStates(force_refresh=force_refresh, session=session)
        self.startStatePolling(session=session)
        return view

    # .. transport ..............................................................
    def _state_transport(self, session=None):
        """Resolve the transport: per-call override > node session > module hook.

        Defaults to the stdlib transport so state monitoring works with no
        third-party dependency.
        """
        if session is not None:
            return session
        if self.stateSession is not None:
            return self.stateSession
        hook = globals().get("state_transport")
        return hook if hook is not None else _UrllibTransport()

    def _state_get(self, path, session=None, device_id=None, segment=None):
        """GET one Maker API path; returns a success/failure DeviceState carrier.

        ``segment`` is an extra opaque path segment (``/postURL``), encoded once
        by :meth:`state_url`.

        The returned object is a :class:`DeviceState` used purely as a result
        carrier (``ok``/``code``/``status_code``/``payload``/``error``) -- it is
        never cached and never published.
        """
        device_id = _normalize_device_id(device_id) if device_id is not None else None
        try:
            url = self.state_url(path, segment=segment)
        except ValueError as exc:
            return self._state_failure(
                STATE_MISSING_CONFIGURATION, device_id, str(exc)
            )

        transport = self._state_transport(session)
        try:
            request = getattr(transport, "request", None)
            if callable(request):
                try:
                    response = request("GET", url, timeout=self.state_timeout)
                except TypeError:
                    # Transport without timeout support (older mock/helper).
                    response = request("GET", url)
            else:
                response = transport.get(url, timeout=self.state_timeout)
        except TimeoutError as exc:
            # NB: ``socket.timeout`` is an alias of ``TimeoutError`` on py3.10+.
            return self._state_failure(
                STATE_TIMEOUT, device_id, "hub did not respond in time", error=str(exc)
            )
        except URLError as exc:
            return self._state_failure(
                STATE_CONNECTION_ERROR,
                device_id,
                "hub is unreachable",
                error=str(getattr(exc, "reason", exc)),
            )
        except Exception as exc:
            name = exc.__class__.__name__
            if name in ("RequestException", "ConnectionError", "HTTPError", "OSError"):
                return self._state_failure(
                    STATE_CONNECTION_ERROR, device_id, "hub is unreachable", error=str(exc) or name
                )
            return self._state_failure(
                STATE_TRANSPORT_ERROR,
                device_id,
                "unexpected error talking to the hub",
                error=str(exc) or name,
            )

        status = getattr(response, "status_code", None)
        payload = self._state_response_body(response)
        if isinstance(status, int) and not 200 <= status < 300:
            code = STATE_HTTP_ERROR
            message = f"hub returned HTTP {status}"
            if status == 404:
                code = STATE_NOT_FOUND
                message = "hub does not expose this device (is it authorized in Maker API?)"
            elif status in (401, 403):
                message = "hub rejected the Maker API access token"
            return self._state_failure(
                code, device_id, message, status_code=status, error=self._state_error_text(payload, status), payload=payload
            )
        return self._state_result(device_id, payload, status)

    @staticmethod
    def _state_response_body(response):
        """Decode a transport response body to JSON (``None`` on malformed)."""
        if isinstance(response, (dict, list)):
            return response
        text = getattr(response, "text", None)
        if not isinstance(text, str):
            reader = getattr(response, "json", None)
            if callable(reader):
                try:
                    return reader()
                except Exception:
                    return None
            content = getattr(response, "content", None)
            return _state_json(content)
        return _state_json(text)

    @staticmethod
    def _state_error_text(payload, status):
        """Build a readable error string from a hub error body."""
        if isinstance(payload, dict):
            for key in ("error", "message", "error_description", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
        if isinstance(payload, list) and payload:
            return "hub rejected the request"
        return f"HTTP {status}"

    def _states_from_device_list(self, session=None):
        """Fall back to per-device reads when ``/devices/all`` is unavailable.

        Uses the known device list when present, otherwise tries the legacy
        ``getDevices()`` mock surface. Partial failures keep the good devices.
        """
        known = self.devices if isinstance(self.devices, list) else []
        ids = []
        for device in known:
            if isinstance(device, dict):
                device_id = _normalize_device_id(device.get("id"))
                if device_id:
                    ids.append(device_id)
        if not ids:
            injected = getattr(self, "_last_request_response", None)
            if isinstance(injected, dict) and isinstance(injected.get("devices"), list):
                for device in injected["devices"]:
                    if isinstance(device, dict):
                        device_id = _normalize_device_id(device.get("id"))
                        if device_id:
                            ids.append(device_id)
        if not ids:
            logger.warning(
                "hubitat: cannot refresh device states (%s) and no device list "
                "is cached -- call refreshDevices() or getDevices() first",
                STATE_CONNECTION_ERROR,
            )
            return {}
        logger.info("hubitat: falling back to %d per-device state reads", len(ids))
        states = {}
        for device_id in ids:
            state = self.getDeviceState(device_id, session=session)
            if state is not None:
                states[device_id] = state
        return states

    def _device_list(self, payload):
        """Normalise ``/devices/all`` payloads into a device list (or ``None``)."""
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("devices", "data", "items"):
                value = payload.get(key)
                if isinstance(value, list):
                    return value
            # A single-device payload is still a valid list of one.
            if "id" in payload or "attributes" in payload:
                return [payload]
        return None

    # .. failure handling ........................................................
    def _state_failure(self, code, device_id, message, status_code=None, error=None, payload=None):
        """Build a failed result-carrier snapshot and log it.

        ``message`` is the friendly, dashboard-safe summary; ``error`` keeps the
        raw transport/hub detail for the log and for operators.
        """
        logger.warning(
            "hubitat state read failed (%s) device=%r: %s",
            code, device_id, message,
        )
        return DeviceState(
            device_id=device_id or "",
            ok=False,
            code=code,
            message=message,
            status_code=status_code,
            error=error or message,
            payload=payload,
            source="fallback",
            stale=False,
        )

    def _state_result(self, device_id, payload, status_code):
        """Build a successful result-carrier snapshot."""
        return DeviceState(
            device_id=device_id or "",
            ok=True,
            code=STATE_OK,
            message="ok",
            status_code=status_code,
            payload=payload,
            source="hub",
        )

    def _stale_entries(self, result):
        """Serve the last known good snapshots after a failed all-device read."""
        entries = self.state_cache.entries()
        if not entries:
            return {}
        logger.warning(
            "hubitat: serving %d cached device state(s) as stale (%s)",
            len(entries), result.code,
        )
        states = {}
        for device_id, cached in entries.items():
            stale = DeviceState(
                device_id=device_id,
                ok=False,
                code=result.code,
                name=cached.name,
                label=cached.label,
                attributes=dict(cached.attributes),
                values=dict(cached.values),
                fetched_at=cached.fetched_at,
                monotonic_at=cached.monotonic_at,
                source="fallback",
                stale=True,
                message=result.message or result.error,
                error=result.error,
                status_code=getattr(result, "status_code", None),
            )
            states[device_id] = stale
        return states

    def _state_failed_with_fallback(self, device_id, result):
        """Per-device failure: prefer the stale cached snapshot over nothing."""
        cached = self.state_cache.get(device_id, allow_stale=True) if device_id else None
        if cached is None:
            state = self._state_failure(
                result.code,
                device_id or result.device_id,
                result.message or result.error or "device state unavailable",
                status_code=getattr(result, "status_code", None),
                error=result.error,
                payload=getattr(result, "payload", None),
            )
            self._note_state_failure()
            return state
        stale = DeviceState(
            device_id=cached.device_id,
            ok=False,
            code=result.code,
            name=cached.name,
            label=cached.label,
            attributes=dict(cached.attributes),
            values=dict(cached.values),
            fetched_at=cached.fetched_at,
            monotonic_at=cached.monotonic_at,
            source="fallback",
            stale=True,
            message=result.message or result.error,
            error=result.error,
            status_code=getattr(result, "status_code", None),
        )
        self._note_state_failure()
        return stale

    def _note_state_success(self):
        """Clear the failure back-off after a successful read."""
        self._state_backoff = 0.0
        self._state_backoff_until = 0.0

    def _note_state_failure(self):
        """Grow the exponential back-off so a dead hub is not hammered."""
        self._state_backoff = min(
            STATE_BACKOFF_MAX,
            STATE_BACKOFF_START if not self._state_backoff else self._state_backoff * 2,
        )
        self._state_backoff_until = time.monotonic() + self._state_backoff

    @staticmethod
    def _finish_state(state, callback=None):
        """Hand ``state`` to ``callback`` (err-first) and return it."""
        if callback is not None:
            callback(None if state.ok else state.error, state)
        return state

    @staticmethod
    def _finish_all(states, callback=None, failure=None):
        """Hand an all-device snapshot to ``callback`` (err-first) and return it.

        An error is reported when the snapshot is empty and the underlying read
        failed (``failure``), or when *every* device in a non-empty snapshot
        failed. A partial failure is a valid, usable snapshot: the dashboard
        shows the working tiles and flags the rest as stale, so it is not an
        error.
        """
        if callback is not None:
            error = None
            if not states:
                error = getattr(failure, "message", None) or getattr(failure, "error", None)
            else:
                failed = [state for state in states.values() if not state.ok]
                if failed and len(failed) == len(states):
                    error = failed[0].message or failed[0].error or "no device state available"
            callback(error, states)
        return states

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
    "DEFAULT_BASE_URL",
    "DEFAULT_STATE_TTL",
    "DEFAULT_STATE_POLL_MS",
    "STATE_ATTRIBUTES",
    "STATE_UNITS",
    "BOOL_ATTRIBUTES",
    "STALE_MARKER",
    "DeviceState",
    "StateCache",
    "parse_state_value",
    "format_state_display",
    "state_transport",
]
