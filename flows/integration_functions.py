"""Integration functions mirror -- API integration logic and utilities.

Python mirror of ``flows/integration-functions.js``: the ``hubitatAPI``
and ``unifiAPI`` clients, the ``httpHelper`` transport and the ``utils``
toolbox.

Notes:
    * The API clients are singletons whose ``init()`` applies only the
      first configuration (later calls are no-ops), mirroring the JS
      module-level objects which are initialised once at flow load.
    * HTTP calls go through the module-level :data:`fetch` transport so
      tests can patch ``integration_functions.fetch``.
"""

import json
import time

HUBITAT_DEFAULT_URL = "http://hubitat.local:8080"
UNIFI_DEFAULT_URL = "https://unifi.local:8443"


def _missing_fetch(*args, **kwargs):
    raise RuntimeError(
        "No fetch transport configured; set integration_functions.fetch"
    )


# Module-level HTTP transport hook (patched by tests).
fetch = _missing_fetch


class HubitatAPIClient:
    """Hubitat API client (mirror of the ``hubitatAPI`` object in JS)."""

    def __init__(self):
        self.BASE_URL = None
        self.API_KEY = None
        self._initialized = False

    def init(self, config):
        """Initialise the client from a config dict (url/apiKey).

        Only the first call applies the configuration; subsequent calls
        are no-ops (the singleton keeps its original settings).
        """
        if self._initialized:
            return None
        config = config or {}
        self.BASE_URL = config.get("url") or HUBITAT_DEFAULT_URL
        self.API_KEY = config.get("apiKey")
        self._initialized = True
        return None

    def _headers(self, content_type=None):
        headers = {
            "Authorization": f"Bearer {self.API_KEY}",
            "Accept": "application/json",
        }
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def _request(self, method, url, data=None):
        response = fetch(url, method=method, headers=self._headers(), data=data)
        return response.json()

    def getStatus(self):
        """GET /api/v1/status."""
        return self._request("GET", f"{self.BASE_URL}/api/v1/status")

    def getDevices(self):
        """GET /api/v1/devices."""
        return self._request("GET", f"{self.BASE_URL}/api/v1/devices")

    def getDevice(self, device_id):
        """GET /api/v1/devices/<id>."""
        return self._request("GET", f"{self.BASE_URL}/api/v1/devices/{device_id}")

    def updateDevice(self, device_id, data):
        """PUT /api/v1/devices/<id>."""
        return self._request(
            "PUT",
            f"{self.BASE_URL}/api/v1/devices/{device_id}",
            data=data,
        )

    def triggerAutomation(self, automation_id):
        """POST /api/v1/automations/<id>/trigger."""
        return self._request(
            "POST",
            f"{self.BASE_URL}/api/v1/automations/{automation_id}/trigger",
        )


class UniFiAPIClient:
    """UniFi API client (mirror of the ``unifiAPI`` object in JS)."""

    CLIENTS_PATH = "/rest/smartapi/apis/smart/v2/ubnt/network/clients"
    AP_PATH = "/rest/proprietory/rest/cap/wlan"
    TRAFFIC_PATH = "/rest/smartapi/apis/smart/v2/ubnt/network/traffic"

    def __init__(self):
        self.BASE_URL = None
        self.USERNAME = None
        self.PASSWORD = None
        self.SESSION_TOKEN = None
        self._initialized = False

    def init(self, config):
        """Initialise the client from a config dict (url/username/password).

        Only the first call applies the configuration; subsequent calls
        are no-ops (the singleton keeps its original settings).
        """
        if self._initialized:
            return None
        config = config or {}
        self.BASE_URL = config.get("url") or UNIFI_DEFAULT_URL
        self.USERNAME = config.get("username")
        self.PASSWORD = config.get("password")
        self._initialized = True
        return None

    def _request(self, method, url, data=None, headers=None):
        response = fetch(url, method=method, headers=headers, data=data)
        return response.json()

    def authenticate(self):
        """POST /api/login with the credentials; store the session token."""
        result = self._request(
            "POST",
            f"{self.BASE_URL}/api/login",
            data={"username": self.USERNAME, "password": self.PASSWORD},
            headers={"Content-Type": "application/json"},
        )
        self.SESSION_TOKEN = result.get("token")
        return result

    def _auth_headers(self):
        return {
            "Authorization": f"Bearer {self.SESSION_TOKEN}",
            "Content-Type": "application/json",
        }

    def get(self, url):
        """GET ``url`` against the controller with the session token."""
        return self._request(
            "GET", f"{self.BASE_URL}{url}", headers=self._auth_headers()
        )

    def post(self, url, data):
        """POST ``data`` to ``url`` with the session token."""
        return self._request(
            "POST",
            f"{self.BASE_URL}{url}",
            data=data,
            headers=self._auth_headers(),
        )

    def getClients(self):
        """GET the WiFi client list."""
        return self.get(self.CLIENTS_PATH)

    def getAccessPoints(self):
        """GET the access point list."""
        return self.get(self.AP_PATH)

    def getNetworkTraffic(self):
        """GET the network traffic stats."""
        return self.get(self.TRAFFIC_PATH)


class HTTPHelper:
    """HTTP helper (mirror of the ``httpHelper`` object in JS).

    ``request(options, callback)`` performs the transport call and hands
    ``(err, res)`` to ``callback`` when a real transport is configured.
    """

    def __init__(self):
        self.request = None

    def _request(self, options, callback=None):
        if self.request is not None:
            return self.request(options, callback)
        return fetch(options.get("url"), method=options.get("method"), headers={})

    def get(self, url, callback=None):
        """GET ``url``."""
        return self._request({"url": url, "method": "GET"}, callback)

    def post(self, url, data, callback=None):
        """POST ``data`` to ``url``."""
        return self._request(
            {"url": url, "method": "POST", "body": data}, callback
        )

    def put(self, url, data, callback=None):
        """PUT ``data`` to ``url``."""
        return self._request(
            {"url": url, "method": "PUT", "body": data}, callback
        )

    def delete(self, url, callback=None):
        """DELETE ``url``."""
        return self._request({"url": url, "method": "DELETE"}, callback)


class Utils:
    """Utility toolbox (mirror of the ``utils`` object in JS)."""

    @staticmethod
    def formatDate(date):
        """Format a date to an ISO-8601 string ('' for falsy input)."""
        if not date:
            return ""
        from datetime import datetime, timezone

        parsed = datetime.fromisoformat(str(date).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

    @staticmethod
    def parseJSON(string):
        """Parse JSON, returning None on invalid input."""
        try:
            return json.loads(string)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def validateConfig(config, required_fields):
        """Raise when required fields are missing from ``config``."""
        missing = [field for field in required_fields if not config.get(field)]
        if missing:
            raise ValueError(f"Missing required fields: {', '.join(missing)}")
        return True

    @staticmethod
    def debounce(func, wait):
        """Leading-edge debounce: calls within ``wait`` ms are dropped."""
        state = {"last": None}

        def wrapper(*args, **kwargs):
            now = time.monotonic() * 1000
            if state["last"] is None or now - state["last"] >= wait:
                state["last"] = now
                return func(*args, **kwargs)
            return None

        return wrapper

    @staticmethod
    def throttle(func, limit):
        """Throttle: only the first call within ``limit`` ms executes."""
        return Utils.debounce(func, limit)


hubitatAPI = HubitatAPIClient()
unifiAPI = UniFiAPIClient()
httpHelper = HTTPHelper()
utils = Utils()

__all__ = [
    "hubitatAPI",
    "unifiAPI",
    "httpHelper",
    "utils",
    "HubitatAPIClient",
    "UniFiAPIClient",
    "HTTPHelper",
    "Utils",
    "fetch",
]
