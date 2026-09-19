"""Fake HTTP transports for the Hubitat automation-trigger tests.

These stand in for ``requests.Session`` (the interface ``hubitat_integration``
talks to) so the automation tests never need a live hub. Every call is
recorded and a canned response is returned.
"""

import json
import socket


class FakeResponse:
    """Stand-in for a ``requests.Response``."""

    def __init__(self, status_code=200, body=None, text=None):
        self.status_code = status_code
        self._body = body
        self.text = text if text is not None else (
            json.dumps(body) if body is not None else ""
        )

    def json(self):
        """Decode the canned body (raises ``ValueError`` when it is not JSON)."""
        if self._body is None:
            raise ValueError("no json body")
        return self._body


class FakeSession:
    """Records every request and returns queued/canned responses.

    ``responses`` may be:
      * a list, consumed in order (the last one repeats);
      * a single :class:`FakeResponse`;
      * a callable ``f(method, url, kwargs) -> FakeResponse``;
      * a plain exception instance/class, raised on every call.
    """

    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses
        self._index = 0

    # -- requests.Session surface -------------------------------------------
    def request(self, method, url, data=None, timeout=None, **kwargs):
        """Record the call and return/raise the configured response."""
        self.calls.append({
            "method": method, "url": url, "data": data,
            "timeout": timeout, **kwargs,
        })
        return self._resolve(method, url, {"data": data, "timeout": timeout, **kwargs})

    def get(self, url, timeout=None, **kwargs):
        """GET ``url``."""
        return self.request("GET", url, None, timeout, **kwargs)

    def post(self, url, data=None, timeout=None, **kwargs):
        """POST ``data`` to ``url``."""
        return self.request("POST", url, data, timeout, **kwargs)

    # -- helpers ------------------------------------------------------------
    def _resolve(self, method, url, kwargs):
        responses = self.responses
        if responses is None:
            return FakeResponse(200, {})
        if callable(responses) and not isinstance(responses, type):
            return responses(method, url, kwargs)
        if isinstance(responses, type) and issubclass(responses, BaseException):
            raise responses("boom")
        if isinstance(responses, BaseException):
            raise responses
        if isinstance(responses, list):
            if not responses:
                return FakeResponse(200, {})
            index = min(self._index, len(responses) - 1)
            self._index += 1
            item = responses[index]
            if isinstance(item, BaseException):
                raise item
            if callable(item):
                return item(method, url, kwargs)
            return item
        return responses

    @property
    def last_call(self):
        """The most recent recorded call, or ``None``."""
        return self.calls[-1] if self.calls else None

    @property
    def call_count(self):
        """Number of recorded calls."""
        return len(self.calls)


class TimeoutSession(FakeSession):
    """Transport that always raises ``socket.timeout``."""

    def request(self, method, url, data=None, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url})
        raise socket.timeout("timed out")


class UnreachableSession(FakeSession):
    """Transport that always raises a connection-style error."""

    def request(self, method, url, data=None, timeout=None, **kwargs):
        self.calls.append({"method": method, "url": url})
        raise ConnectionError("connection refused")
