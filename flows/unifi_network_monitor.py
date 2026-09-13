"""UniFi network monitor mirror -- network monitoring and client tracking.

Python mirror of ``flows/unifi-network-monitor.js``: the ``UniFiNode``
class talks to a UniFi controller for clients, APs and traffic stats.
"""

import json

DEFAULT_BASE_URL = "https://unifi.local:8443"


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


class UniFiNode:
    """UniFi monitor node (mirror of the ``unifi-monitor`` node)."""

    CLIENTS_PATH = "/rest/smartapi/apis/smart/v2/ubnt/network/clients"
    AP_PATH = "/rest/proprietory/rest/cap/wlan"
    TRAFFIC_PATH = "/rest/smartapi/apis/smart/v2/ubnt/network/traffic"
    DEVICES_PATH = "/rest/smartapi/apis/smart/v2/ubnt/devices"
    STATS_PATH = "/rest/smartapi/apis/smart/v2/ubnt/network/stats"

    def __init__(self, node_type, msg, config, node=None):
        self.type = node_type
        self.config = dict(config or {})
        self.baseUrl = self.config.get("url") or DEFAULT_BASE_URL
        self.username = self.config.get("username")
        self.password = self.config.get("password")
        self.clients = []
        self.accessPoints = []
        self.networkTraffic = {"upload": 0, "download": 0, "total": 0}
        self.sessionToken = None
        self.send = _CallRecorder()
        self.status = _CallRecorder()
        self._handlers = {}

    # -- events ------------------------------------------------------------------
    def on(self, event, handler):
        """Register a handler, or dispatch immediately when given a dict."""
        if callable(handler):
            self._handlers.setdefault(event, []).append(handler)
        elif isinstance(handler, dict):
            self._dispatch(event, handler)

    def _dispatch(self, event, data):
        if event == "subscribe":
            if data.get("type") == "client-connected":
                self.updateClientList()
            elif data.get("type") == "ap-status":
                self.updateAPStatus()
        for handler in self._handlers.get(event, []):
            handler(data)

    # -- authentication ------------------------------------------------------------
    def authenticate(self, callback=None):
        """Log in to the controller and store the session token."""
        url = f"{self.baseUrl}/api/login"
        payload = {"username": self.username, "password": self.password}
        data = self.sendRequest("POST", url, payload, None)
        if isinstance(data, dict) and data.get("token"):
            self.sessionToken = data["token"]
            self.status({"fill": "green", "shape": "dot", "text": "connected"})
        if callback is not None:
            callback(None, self.sessionToken)
        return self.sessionToken

    # -- monitoring ------------------------------------------------------------------
    def refreshNetwork(self):
        """Refresh clients, APs and traffic in one pass."""
        self.updateClientList()
        self.updateAPStatus()
        self.updateNetworkTraffic()

    def updateClientList(self):
        """Fetch the WiFi client list and publish the count."""
        data = self._decode(self.get(self.CLIENTS_PATH))
        self.clients = data.get("clients") or []
        self.status({
            "fill": "blue",
            "shape": "dot",
            "text": f"{len(self.clients)} clients",
        })
        self.send({"payload": self.clients})

    def getClientDetails(self, client_id, callback=None):
        """Fetch one client's details by id."""
        return self.get(f"{self.CLIENTS_PATH}/{client_id}", callback)

    def updateAPStatus(self):
        """Fetch the AP list and publish the count."""
        self.getAPList()

    def getAPList(self):
        """Fetch access points and publish the count."""
        data = self._decode(self.get(self.AP_PATH))
        self.accessPoints = data.get("accessPoints") or []
        self.status({
            "fill": "green",
            "shape": "dot",
            "text": f"{len(self.accessPoints)} APs",
        })
        self.send({"payload": self.accessPoints})

    def getAPDetails(self, ap_id, callback=None):
        """Fetch one AP's details by id."""
        return self.get(f"{self.AP_PATH}/{ap_id}", callback)

    def updateNetworkTraffic(self):
        """Fetch traffic stats and publish the running totals."""
        data = self._decode(self.get(self.TRAFFIC_PATH))
        traffic = data.get("traffic") or {}
        self.networkTraffic["upload"] = traffic.get("up", 0)
        self.networkTraffic["download"] = traffic.get("down", 0)
        self.networkTraffic["total"] = (
            traffic.get("up", 0) + traffic.get("down", 0)
        )
        self.send({"payload": dict(self.networkTraffic)})

    def getNetworkStats(self, callback=None):
        """Fetch network statistics."""
        return self.get(self.STATS_PATH, callback)

    def getDeviceList(self):
        """Fetch the UniFi device list."""
        data = self._decode(self.get(self.DEVICES_PATH))
        self.send({"payload": data.get("devices") or []})

    # -- transport ---------------------------------------------------------------------
    def get(self, path, callback=None):
        """GET ``path`` against the controller base URL."""
        return self.sendRequest("GET", f"{self.baseUrl}{path}", None, callback)

    def post(self, path, data, callback=None):
        """POST ``data`` to ``path`` against the controller base URL."""
        return self.sendRequest("POST", f"{self.baseUrl}{path}", data, callback)

    def put(self, path, data, callback=None):
        """PUT ``data`` to ``path`` against the controller base URL."""
        return self.sendRequest("PUT", f"{self.baseUrl}{path}", data, callback)

    def delete(self, path, callback=None):
        """DELETE ``path`` against the controller base URL."""
        return self.sendRequest("DELETE", f"{self.baseUrl}{path}", None, callback)

    def sendRequest(self, method, url, data, callback=None):
        """Simulated HTTP request -- responds with a canned success payload."""
        response = {
            "success": True,
            "data": data or {},
            "message": "UniFi request completed",
        }
        if callback is not None:
            callback(None, response)
        return response

    @staticmethod
    def _decode(response):
        """Decode a transport response into a dict (``{}`` on failure)."""
        if isinstance(response, dict):
            if "success" in response and "data" in response:
                inner = response["data"]
                return inner if isinstance(inner, dict) else {}
            return response
        try:
            body = b"".join(response.__iter__())
            return json.loads(body)
        except Exception:  # mirror must not raise on mocked transports
            return {}


__all__ = ["UniFiNode", "DEFAULT_BASE_URL"]
