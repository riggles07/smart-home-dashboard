"""Hubitat integration mirror -- smart home device controls and automation.

Python mirror of ``flows/hubitat-integration.js``: the ``HUBITAT_NODE``
class provides the Hubitat hub API surface used by the dashboard.
"""

DEFAULT_BASE_URL = "http://hubitat.local:8080"


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
