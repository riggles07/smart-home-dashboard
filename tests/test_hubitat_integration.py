"""
Tests for hubitat-integration.js (Smart home device controls)

Device state monitoring
-----------------------
The state-monitoring tests below drive the node through fake HTTP transports
(no live hub required).  Three seams are used:

* ``session=``          -- per-call transport override on each public method.
* ``node.stateSession`` -- transport stored on the node.
* ``hubitat_integration.state_transport`` -- module-level transport hook
  (monkeypatched per test, so it cannot leak between tests).

A transport is anything exposing ``request(method, url, timeout=)`` or
``get(url)``; :class:`FakeSession` records the calls and replays queued
responses/exceptions, so URL construction, caching and error mapping are all
assertable without a network.
"""
import pytest
import sys
import io
import json
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from urllib.error import HTTPError, URLError

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))

from flows import hubitat_integration


def callback(*args, **kwargs):
    """No-op callback used as a placeholder in Mock(callback) calls."""
    return None


# ---------------------------------------------------------------------------
# Fake HTTP transports (no network, no live hub)
# ---------------------------------------------------------------------------
class FakeResponse:
    """Minimal stand-in for a ``requests`` response."""

    def __init__(self, body=None, status_code=200, text=None):
        self.status_code = status_code
        if text is None:
            text = "" if body is None else json.dumps(body)
        self.text = text
        self.content = text.encode('utf-8')

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        try:
            return json.loads(self.text)
        except ValueError:
            return None


class FakeSession:
    """Transport that records requests and replays a queue of results.

    Each queued item is a :class:`FakeResponse`, an exception instance (raised),
    or a callable taking the URL and returning a response.
    """

    def __init__(self, *results):
        self.queue = list(results)
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append({'method': method, 'url': url, 'timeout': timeout})
        if not self.queue:
            return FakeResponse([])
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(url)
        return item

    def get(self, url, timeout=None, **kwargs):
        return self.request('GET', url, timeout=timeout)

    @property
    def call_count(self):
        return len(self.calls)

    @property
    def last_url(self):
        return self.calls[-1]['url'] if self.calls else None


def make_node(session=None, **config):
    """Build a node configured for a Maker API hub, optionally with a transport."""
    cfg = {
        'url': 'http://hub.local:8080',
        'appId': '99',
        'accessToken': 'test-access-token',
    }
    cfg.update(config)
    node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, cfg, None)
    if session is not None:
        node.stateSession = session
    return node


DEVICE_ALL = [
    {
        'id': '101',
        'name': 'Living Room Light',
        'label': 'Living Room Light',
        'attributes': {'switch': 'on', 'level': '45', 'hue': '12',
                       'saturation': '80', 'battery': '88'},
        'capabilities': ['SwitchLevel', 'ColorControl'],
    },
    {
        'id': '102',
        'name': 'Hallway Motion',
        'label': 'Hallway Motion',
        'attributes': {'motion': 'inactive', 'temperature': '21.5',
                       'battery': '12'},
    },
]

SINGLE_DEVICE = {
    'id': '101',
    'name': 'Living Room Light',
    'label': 'Living Room Light',
    'attributes': {'switch': 'on', 'level': '45'},
}


# ---------------------------------------------------------------------------
# Value parsing / display helpers
# ---------------------------------------------------------------------------
class TestStateValueParsing:
    """Unit tests for the attribute interpretation helpers."""

    def test_switch_values_become_booleans(self):
        assert hubitat_integration.parse_state_value('switch', 'on') is True
        assert hubitat_integration.parse_state_value('switch', 'off') is False
        assert hubitat_integration.parse_state_value('switch', 'ON') is True

    def test_enumerated_sensor_values_become_booleans(self):
        assert hubitat_integration.parse_state_value('motion', 'active') is True
        assert hubitat_integration.parse_state_value('contact', 'open') is True
        assert hubitat_integration.parse_state_value('contact', 'closed') is False
        assert hubitat_integration.parse_state_value('lock', 'unlocked') is False
        assert hubitat_integration.parse_state_value('presence', 'present') is True

    def test_numeric_attributes_become_numbers(self):
        assert hubitat_integration.parse_state_value('level', '45') == 45
        assert hubitat_integration.parse_state_value('level', 45) == 45
        assert hubitat_integration.parse_state_value('temperature', '21.5') == 21.5
        assert hubitat_integration.parse_state_value('battery', '88') == 88
        assert hubitat_integration.parse_state_value('hue', '12') == 12

    def test_text_attributes_pass_through(self):
        assert hubitat_integration.parse_state_value('colorMode', 'CT') == 'CT'
        assert hubitat_integration.parse_state_value('thermostatMode', 'heat') == 'heat'

    def test_unparseable_values_return_none(self):
        assert hubitat_integration.parse_state_value('switch', 'banana') is None
        assert hubitat_integration.parse_state_value('switch', None) is None
        assert hubitat_integration.parse_state_value('level', 'not-a-number') == 'not-a-number'

    def test_non_finite_numbers_are_rejected(self):
        assert hubitat_integration.parse_state_value('temperature', 'NaN') is None
        assert hubitat_integration.parse_state_value('temperature', float('inf')) is None

    def test_display_renders_units(self):
        assert hubitat_integration.format_state_display('switch', True) == 'on'
        assert hubitat_integration.format_state_display('switch', False) == 'off'
        assert hubitat_integration.format_state_display('level', 45) == '45%'
        assert hubitat_integration.format_state_display('battery', 88) == '88%'
        assert hubitat_integration.format_state_display('temperature', 21.5) == '21.5°C'
        assert hubitat_integration.format_state_display('colorTemperature', 2700) == '2700K'
        assert hubitat_integration.format_state_display('colorMode', 'CT') == 'CT'

    def test_display_handles_unknown_values(self):
        assert hubitat_integration.format_state_display('switch', None) == 'unknown'
        assert hubitat_integration.format_state_display('level', None) == 'unknown'


class TestDeviceStateSnapshot:
    """Tests for building a snapshot out of a Maker API device payload."""

    def test_builds_from_device_payload(self):
        state = hubitat_integration._state_from_device(SINGLE_DEVICE)
        assert state.ok is True
        assert state.code == 'ok'
        assert state.device_id == '101'
        assert state.label == 'Living Room Light'
        assert state.attributes['switch'] == 'on'
        assert state.values['switch'] is True
        assert state.values['level'] == 45

    def test_accepts_wrapped_device_payload(self):
        state = hubitat_integration._state_from_device({'device': SINGLE_DEVICE})
        assert state.device_id == '101'
        assert state.values['switch'] is True

    def test_accepts_single_attribute_payload(self):
        payload = {'id': '123', 'attribute': 'switch', 'value': 'off'}
        state = hubitat_integration._state_from_device(payload)
        assert state.device_id == '123'
        assert state.attributes == {'switch': 'off'}
        assert state.values['switch'] is False

    def test_rejects_malformed_payloads(self):
        assert hubitat_integration._state_from_device('not-a-dict') is None
        assert hubitat_integration._state_from_device([]) is None
        assert hubitat_integration._state_from_device({'attributes': 'nope'}) is None
        assert hubitat_integration._state_from_device({}) is None

    def test_primary_attribute_prefers_switch(self):
        state = hubitat_integration._state_from_device(DEVICE_ALL[0])
        assert state.primary_attribute() == 'switch'
        motion = hubitat_integration._state_from_device(DEVICE_ALL[1])
        assert motion.primary_attribute() == 'motion'

    def test_primary_attribute_is_none_without_attributes(self):
        state = hubitat_integration._state_from_device({'id': '5'})
        assert state.primary_attribute() is None
        tile = state.as_tile()
        assert tile['primary'] is None
        assert tile['label'] == '5'

    def test_tile_renders_display_value(self):
        tile = hubitat_integration._state_from_device(DEVICE_ALL[0]).as_tile()
        assert tile['deviceId'] == '101'
        assert tile['primary']['attribute'] == 'switch'
        assert tile['primary']['display'] == 'on'
        assert tile['primary']['unit'] == ''
        assert tile['stale'] is False
        assert tile['ok'] is True

    def test_snapshot_never_exposes_the_access_token(self):
        node = make_node()
        state = hubitat_integration._state_from_device(SINGLE_DEVICE)
        node.access_token  # ensure the property resolves without touching state
        blob = json.dumps(state.to_dict()) + json.dumps(state.as_tile())
        assert 'test-access-token' not in blob


# ---------------------------------------------------------------------------
# Cache behaviour
# ---------------------------------------------------------------------------
class TestStateCache:
    """TTL cache: freshness, stale fallback, invalidation, eviction, events."""

    def _state(self, device_id='101', monotonic_at=0.0, **kwargs):
        state = hubitat_integration.DeviceState(
            device_id=device_id,
            attributes={'switch': 'on'},
            values={'switch': True},
            monotonic_at=monotonic_at,
            **kwargs,
        )
        return state

    def test_fresh_entry_is_returned(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state(monotonic_at=100.0))
        assert cache.is_fresh('101', now=105.0) is True
        assert cache.get('101', now=105.0) is not None

    def test_entry_expires_after_ttl(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state(monotonic_at=100.0))
        assert cache.is_fresh('101', now=111.0) is False
        assert cache.get('101', now=111.0) is None

    def test_expired_entry_is_available_as_stale(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state(monotonic_at=100.0))
        stale = cache.get('101', allow_stale=True, now=999.0)
        assert stale is not None
        assert stale.attributes['switch'] == 'on'

    def test_unknown_device_is_a_miss(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        assert cache.get('nope') is None
        assert cache.is_fresh('nope') is False

    def test_invalidate_one_and_all(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state('101'))
        cache.put(self._state('102'))
        assert cache.invalidate('101') == 1
        assert len(cache) == 1
        assert cache.get('101') is None
        assert cache.invalidate() == 1
        assert len(cache) == 0

    def test_invalidate_ignores_unknown_ids(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        assert cache.invalidate('missing') == 0
        assert cache.invalidate(None) == 0

    def test_eviction_respects_max_entries(self):
        cache = hubitat_integration.StateCache(ttl=10.0, max_entries=2)
        cache.put(self._state('old', monotonic_at=1.0))
        cache.put(self._state('mid', monotonic_at=5.0))
        cache.put(self._state('new', monotonic_at=9.0))
        assert len(cache) == 2
        assert cache.get('old', allow_stale=True) is None
        assert cache.get('new', allow_stale=True) is not None

    def test_update_attribute_writes_through(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state('101', monotonic_at=1.0))
        updated = cache.update_attribute('101', 'switch', 'off', now=20.0)
        assert updated.values['switch'] is False
        assert updated.source == 'event'
        # A pushed event refreshes the entry past its TTL window.
        assert cache.is_fresh('101', now=20.5) is True

    def test_update_attribute_creates_missing_entry(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        created = cache.update_attribute('999', 'battery', '55', label='Sensor')
        assert created is not None
        assert created.values['battery'] == 55
        assert created.label == 'Sensor'

    def test_update_attribute_rejects_bad_input(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        assert cache.update_attribute(None, 'switch', 'on') is None
        assert cache.update_attribute('101', '', 'on') is None
        assert cache.update_attribute('101', None, 'on') is None
        assert cache.update_attribute('101', hubitat_integration.STALE_MARKER, 'on') is None

    def test_stats_track_activity(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state('101', monotonic_at=1.0))
        cache.get('101', now=2.0)
        cache.get('missing')
        cache.update_attribute('102', 'switch', 'on')
        stats = cache.stats()
        assert stats['stores'] == 1
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['events'] == 1
        assert stats['size'] == 2
        assert stats['ttlSeconds'] == 10.0

    def test_put_ignores_non_snapshots(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        assert cache.put('not-a-state') is None
        assert len(cache) == 0

    def test_membership_operator_uses_device_id(self):
        cache = hubitat_integration.StateCache(ttl=10.0)
        cache.put(self._state('101'))
        assert '101' in cache
        assert '202' not in cache


# ---------------------------------------------------------------------------
# Single-device fetch
# ---------------------------------------------------------------------------
class TestSingleDeviceState:
    """getDeviceState(): URL shape, success, caching and every failure path."""

    def test_fetch_returns_interpreted_state(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is True
        assert state.device_id == '101'
        assert state.values['switch'] is True
        assert state.values['level'] == 45
        assert state.source == 'hub'

    def test_fetch_calls_the_maker_api_device_endpoint(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE))
        node = make_node(session)
        node.getDeviceState('101')
        assert session.call_count == 1
        url = session.last_url
        assert '/apps/api/99/devices/101' in url
        assert 'access_token=test-access-token' in url

    def test_fetch_sends_the_configured_timeout(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE))
        node = make_node(session, stateTimeout=3)
        node.getDeviceState('101')
        assert session.calls[0]['timeout'] == 3.0

    def test_second_read_is_served_from_cache(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE))
        node = make_node(session)
        node.getDeviceState('101')
        node.getDeviceState('101')
        assert session.call_count == 1

    def test_force_refresh_bypasses_the_cache(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE), FakeResponse(SINGLE_DEVICE))
        node = make_node(session)
        node.getDeviceState('101')
        node.getDeviceState('101', force_refresh=True)
        assert session.call_count == 2

    def test_zero_ttl_always_reads_the_hub(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE), FakeResponse(SINGLE_DEVICE))
        node = make_node(session, stateTtl=0)
        node.getDeviceState('101')
        node.getDeviceState('101')
        assert session.call_count == 2

    def test_invalidate_forces_a_fresh_read(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE), FakeResponse(SINGLE_DEVICE))
        node = make_node(session)
        node.getDeviceState('101')
        node.invalidateDeviceState('101')
        node.getDeviceState('101')
        assert session.call_count == 2

    def test_per_call_session_overrides_the_node_transport(self):
        node_session = FakeSession(FakeResponse(SINGLE_DEVICE))
        other = FakeSession(FakeResponse(SINGLE_DEVICE))
        node = make_node(node_session)
        node.getDeviceState('101', session=other)
        assert other.call_count == 1
        assert node_session.call_count == 0

    def test_callback_receives_the_state(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE))
        node = make_node(session)
        seen = []
        node.getDeviceState('101', callback=lambda err, state: seen.append((err, state)))
        assert len(seen) == 1
        assert seen[0][0] is None
        assert seen[0][1].device_id == '101'

    def test_invalid_device_id_never_reaches_the_hub(self):
        session = FakeSession()
        node = make_node(session)
        for bad in (None, '', '   ', True):
            state = node.getDeviceState(bad)
            assert state.ok is False
            assert state.code == 'invalid_device_id'
        assert session.call_count == 0

    def test_integer_device_ids_are_supported(self):
        session = FakeSession(FakeResponse({'id': 101, 'attributes': {'switch': 'on'}}))
        node = make_node(session)
        state = node.getDeviceState(101)
        assert state.ok is True
        assert '/devices/101' in session.last_url

    # -- failure paths ------------------------------------------------------
    def test_missing_app_id_reports_missing_configuration(self):
        session = FakeSession()
        node = make_node(session, appId=None, url='http://hub.local:8080')
        node.appId = None
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'missing_configuration'
        assert 'app id' in state.message.lower()
        assert 'HUBITAT_APP_ID' in state.message
        assert session.call_count == 0

    def test_missing_token_reports_missing_configuration(self):
        session = FakeSession()
        node = make_node(session, accessToken=None, apiKey=None)
        node.accessToken = None
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'missing_configuration'
        assert session.call_count == 0

    def test_hub_unreachable_reports_connection_error(self):
        session = FakeSession(URLError('connection refused'))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'connection_error'
        assert state.stale is False

    def test_timeout_is_reported_as_timeout(self):
        session = FakeSession(TimeoutError('timed out'))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'timeout'

    def test_unknown_device_404_is_reported(self):
        session = FakeSession(FakeResponse(text='device not found', status_code=404))
        node = make_node(session)
        state = node.getDeviceState('404')
        assert state.ok is False
        assert state.code == 'not_found'
        assert state.status_code == 404

    def test_auth_failure_is_reported(self):
        session = FakeSession(FakeResponse(body={'error': 'Unauthorized'}, status_code=401))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'http_error'
        # Friendly summary is shown to the dashboard; raw body stays in ``error``.
        assert 'token' in state.message.lower()
        assert state.error == 'Unauthorized'
        assert state.status_code == 401

    def test_server_error_is_reported(self):
        session = FakeSession(FakeResponse(text='boom', status_code=500))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'http_error'
        assert state.status_code == 500

    def test_malformed_json_is_reported(self):
        session = FakeSession(FakeResponse(text='<html>not json</html>'))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'invalid_payload'

    def test_non_device_json_is_reported(self):
        session = FakeSession(FakeResponse(body=[1, 2, 3]))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'invalid_payload'

    def test_unexpected_transport_error_is_contained(self):
        session = FakeSession(RuntimeError('weird transport'))
        node = make_node(session)
        state = node.getDeviceState('101')
        assert state.ok is False
        assert state.code == 'transport_error'

    def test_failure_after_success_serves_last_known_values_as_stale(self):
        session = FakeSession(FakeResponse(SINGLE_DEVICE), URLError('hub down'))
        node = make_node(session)
        good = node.getDeviceState('101')
        assert good.ok is True
        stale = node.getDeviceState('101', force_refresh=True)
        assert stale.ok is False
        assert stale.stale is True
        assert stale.code == 'connection_error'
        # Last known good values are preserved so tiles do not blank out.
        assert stale.values['switch'] is True
        assert stale.attributes['level'] == '45'

    def test_transport_without_timeout_support_still_works(self):
        class NoTimeout:
            def __init__(self):
                self.calls = []

            def request(self, method, url):
                self.calls.append(url)
                return FakeResponse(SINGLE_DEVICE)

        transport = NoTimeout()
        node = make_node()
        state = node.getDeviceState('101', session=transport)
        assert state.ok is True
        assert len(transport.calls) == 1

    def test_transport_without_request_falls_back_to_get(self):
        class GetOnly:
            def __init__(self):
                self.urls = []

            def get(self, url, timeout=None):
                self.urls.append(url)
                return FakeResponse(SINGLE_DEVICE)

        transport = GetOnly()
        node = make_node()
        state = node.getDeviceState('101', session=transport)
        assert state.ok is True
        assert len(transport.urls) == 1


# ---------------------------------------------------------------------------
# All-device fetch
# ---------------------------------------------------------------------------
class TestAllDeviceStates:
    """getAllDeviceStates(): /devices/all, one request per refresh, partial failure."""

    def test_fetch_returns_every_device(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        states = node.getAllDeviceStates()
        assert set(states) == {'101', '102'}
        assert states['101'].values['switch'] is True
        assert states['102'].values['motion'] is False

    def test_fetch_uses_a_single_request_for_the_whole_hub(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.getAllDeviceStates()
        assert session.call_count == 1
        assert '/apps/api/99/devices/all' in session.last_url

    def test_wrapped_devices_payload_is_accepted(self):
        session = FakeSession(FakeResponse({'devices': DEVICE_ALL}))
        node = make_node(session)
        states = node.getAllDeviceStates()
        assert set(states) == {'101', '102'}

    def test_second_refresh_within_ttl_is_cached(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.getAllDeviceStates()
        node.getAllDeviceStates()
        assert session.call_count == 1

    def test_force_refresh_reads_the_hub_again(self):
        session = FakeSession(FakeResponse(DEVICE_ALL), FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.getAllDeviceStates()
        node.getAllDeviceStates(force_refresh=True)
        assert session.call_count == 2

    def test_populates_the_node_device_state_map(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.getAllDeviceStates()
        assert set(node.deviceStates) == {'101', '102'}

    def test_callback_reports_success_without_error(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        seen = []
        node.getAllDeviceStates(callback=lambda err, states: seen.append((err, states)))
        assert seen[0][0] is None
        assert len(seen[0][1]) == 2

    def test_malformed_device_entries_are_skipped_not_fatal(self):
        payload = [DEVICE_ALL[0], 'garbage', None, {'id': '103', 'attributes': {'switch': 'off'}}]
        session = FakeSession(FakeResponse(payload))
        node = make_node(session)
        states = node.getAllDeviceStates()
        assert set(states) == {'101', '103'}

    def test_unreachable_hub_with_no_cache_returns_empty(self):
        session = FakeSession(URLError('hub down'))
        node = make_node(session)
        states = node.getAllDeviceStates()
        assert states == {}

    def test_all_devices_unreachable_but_cached_serves_stale(self):
        session = FakeSession(FakeResponse(DEVICE_ALL), URLError('hub down'))
        node = make_node(session)
        node.getAllDeviceStates()
        stale = node.getAllDeviceStates(force_refresh=True)
        assert set(stale) == {'101', '102'}
        assert all(state.stale is True for state in stale.values())
        assert all(state.ok is False for state in stale.values())
        # Values survive the outage.
        assert stale['101'].values['switch'] is True

    def test_falls_back_to_per_device_reads_when_all_endpoint_fails(self):
        session = FakeSession(
            URLError('no /devices/all'),
            FakeResponse(SINGLE_DEVICE),
            FakeResponse({'id': '102', 'attributes': {'switch': 'off'}}),
        )
        node = make_node(session)
        node.devices = [{'id': '101'}, {'id': '102'}]
        states = node.getAllDeviceStates()
        assert set(states) == {'101', '102'}
        assert session.call_count == 3

    def test_partial_failure_keeps_the_working_devices(self):
        session = FakeSession(
            URLError('no /devices/all'),
            FakeResponse(SINGLE_DEVICE),
            FakeResponse(text='not authorized', status_code=404),
        )
        node = make_node(session)
        node.devices = [{'id': '101'}, {'id': '102'}]
        states = node.getAllDeviceStates()
        assert states['101'].ok is True
        assert states['102'].ok is False
        assert states['102'].code == 'not_found'
        assert states['102'].stale is False

    def test_malformed_all_payload_falls_back_and_then_reports_error(self):
        session = FakeSession(FakeResponse(text='<html/>'), FakeResponse(text='<html/>'))
        node = make_node(session)
        states = node.getAllDeviceStates()
        assert states == {}

    def test_no_device_list_available_logs_and_returns_empty(self):
        session = FakeSession(URLError('hub down'))
        node = make_node(session)
        node.devices = []
        states = node.getAllDeviceStates()
        assert states == {}

    def test_callback_reports_error_only_when_everything_failed(self):
        session = FakeSession(URLError('hub down'), URLError('hub down'))
        node = make_node(session)
        errors = []
        node.getAllDeviceStates(callback=lambda err, states: errors.append(err))
        assert errors and errors[0] is not None

    def test_callback_stays_silent_when_only_some_devices_failed(self):
        session = FakeSession(
            URLError('no /devices/all'),
            FakeResponse(SINGLE_DEVICE),
            FakeResponse(text='nope', status_code=404),
        )
        node = make_node(session)
        node.devices = [{'id': '101'}, {'id': '102'}]
        errors = []
        node.getAllDeviceStates(callback=lambda err, states: errors.append(err))
        assert errors == [None]


# ---------------------------------------------------------------------------
# Dashboard status view wiring
# ---------------------------------------------------------------------------
class TestDashboardStatusView:
    """The dashboard-facing surface: status view, tiles and publish topics."""

    def test_status_view_shape(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        view = node.getStatusView()
        assert view['view'] == 'devices'
        assert view['title'] == 'Device Status'
        assert view['ok'] is True
        assert view['deviceCount'] == 2
        assert view['staleCount'] == 0
        assert view['errorCount'] == 0
        assert len(view['tiles']) == 2
        assert view['tiles'][0]['primary']['display'] == 'on'

    def test_status_view_is_json_serialisable(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        json.dumps(node.getStatusView())

    def test_refresh_publishes_each_device_and_the_tile_list(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.refreshDeviceStates()
        topics = [call[1].get('topic') for call in node.send._calls]
        assert 'hubitat/device/101/state' in topics
        assert 'hubitat/device/102/state' in topics
        assert 'hubitat/devices/state' in topics

    def test_refresh_sets_green_status_when_healthy(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.refreshDeviceStates()
        status = node.status._calls[-1][0][0]
        assert status['fill'] == 'green'
        assert '2 devices' in status['text']

    def test_refresh_sets_red_status_when_hub_is_down(self):
        session = FakeSession(URLError('hub down'))
        node = make_node(session)
        view = node.refreshDeviceStates()
        status = node.status._calls[-1][0][0]
        assert status['fill'] == 'red'
        assert view['ok'] is False
        assert view['deviceCount'] == 0

    def test_refresh_flags_stale_devices_in_status_text(self):
        session = FakeSession(FakeResponse(DEVICE_ALL), URLError('hub down'))
        node = make_node(session)
        node.refreshDeviceStates()
        node.refreshDeviceStates(force_refresh=True)
        status = node.status._calls[-1][0][0]
        assert 'stale' in status['text']
        # Degraded (serving cache after an outage) is a warning, not green.
        assert status['fill'] == 'yellow'

    def test_status_view_reports_the_refresh_strategy(self):
        node = make_node()
        strategy = node.stateRefreshStrategy()
        assert strategy['mode'] == 'hybrid'
        assert strategy['primary'] == 'hub-event-subscription'
        assert strategy['fallback'] == 'ttl-cached-polling'
        assert strategy['pollIntervalMs'] == 60000
        assert strategy['cacheTtlSeconds'] == 5.0
        assert strategy['documentation'] == 'docs/hubitat-state-monitoring.md'

    def test_cache_stats_are_surfaced_on_the_view(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        stats = node.getStatusView()['cache']
        assert stats['size'] == 2
        assert stats['ttlSeconds'] == 5.0

    def test_status_view_without_data_is_not_ok(self):
        node = make_node()
        assert node.status_view({})['ok'] is False

    def test_cleanup_helpers_empty_the_cache(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.getAllDeviceStates()
        assert node.stateCacheStats()['size'] == 2
        assert node.clearStateCache() == 2
        assert node.stateCacheStats()['size'] == 0

    def test_tile_list_never_contains_the_token(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        blob = json.dumps(node.getStatusView())
        assert 'test-access-token' not in blob


# ---------------------------------------------------------------------------
# Hub-pushed events (the primary refresh path)
# ---------------------------------------------------------------------------
class TestDeviceEventPush:
    """handleDeviceEvent()/subscribeStateEvents(): the push half of the strategy."""

    def test_posturl_event_updates_the_cache(self):
        node = make_node()
        event = {'content': {'name': 'switch', 'value': 'off', 'deviceId': '101',
                             'displayName': 'Living Room Light'}}
        state = node.handleDeviceEvent(event)
        assert state.device_id == '101'
        assert state.values['switch'] is False
        assert state.source == 'event'
        assert node.deviceStates['101'].values['switch'] is False

    def test_flat_event_mapping_is_accepted(self):
        node = make_node()
        state = node.handleDeviceEvent(
            {'deviceId': '102', 'name': 'battery', 'value': '55'}
        )
        assert state.values['battery'] == 55

    def test_event_publishes_on_the_device_state_topic(self):
        node = make_node()
        node.handleDeviceEvent({'deviceId': '101', 'attribute': 'switch', 'value': 'on'})
        assert node.send._calls[-1][1]['topic'] == 'hubitat/device/101/state'

    def test_event_for_unknown_device_creates_an_entry(self):
        node = make_node()
        node.handleDeviceEvent({'deviceId': '777', 'name': 'temp', 'value': '19'})
        assert '777' in node.deviceStates

    def test_events_refresh_an_expired_entry(self):
        node = make_node(stateTtl=0)
        node.state_cache.update_attribute('101', 'switch', 'on')
        node.handleDeviceEvent({'deviceId': '101', 'name': 'switch', 'value': 'off'})
        cached = node.state_cache.get('101', allow_stale=True)
        assert cached.values['switch'] is False

    def test_malformed_events_are_ignored_not_fatal(self):
        node = make_node()
        for bad in (None, 'text', [], {}, {'deviceId': '101'}, {'name': 'switch', 'value': 'on'}):
            assert node.handleDeviceEvent(bad) is None

    def test_subscribe_event_dispatch_reaches_the_handler(self):
        node = make_node()
        node.on('subscribe', {'type': 'device-event', 'deviceId': '101',
                              'name': 'switch', 'value': 'on'})
        assert node.deviceStates['101'].values['switch'] is True

    def test_subscribe_state_events_registers_the_post_url(self):
        session = FakeSession(FakeResponse(text='ok'))
        node = make_node(session)
        result = node.subscribeStateEvents('http://dash.local:1880/hubitat/events')
        assert result.ok is True
        assert '/postURL/' in session.last_url
        assert 'dash.local' in session.last_url
        assert node.stateSubscriptionUrl == 'http://dash.local:1880/hubitat/events'

    def test_subscribe_uses_the_configured_url_by_default(self):
        session = FakeSession(FakeResponse(text='ok'))
        node = make_node(session, stateSubscriptionUrl='http://dash.local/hook')
        node.subscribeStateEvents()
        # The URL is one opaque segment, percent-encoded exactly once.
        assert 'postURL/http%3A%2F%2Fdash.local%2Fhook' in session.last_url
        assert '%253A' not in session.last_url

    def test_subscribe_without_a_url_reports_missing_configuration(self):
        session = FakeSession()
        node = make_node(session)
        result = node.subscribeStateEvents()
        assert result.ok is False
        assert result.code == 'missing_configuration'
        assert session.call_count == 0

    def test_clear_state_events_removes_the_subscription(self):
        session = FakeSession(FakeResponse(text='ok'), FakeResponse(text='ok'))
        node = make_node(session, stateSubscriptionUrl='http://dash.local/hook')
        node.clearStateEvents()
        assert node.stateSubscriptionUrl is None
        assert session.last_url.endswith('/postURL?access_token=test-access-token')

    def test_subscribe_failure_is_reported(self):
        session = FakeSession(URLError('hub down'))
        node = make_node(session)
        result = node.subscribeStateEvents('http://dash.local/hook')
        assert result.ok is False
        assert result.code == 'connection_error'

    def test_setup_state_monitoring_snapshots_and_subscribes(self):
        session = FakeSession(FakeResponse(text='ok'), FakeResponse(DEVICE_ALL))
        node = make_node(session, stateSubscriptionUrl='http://dash.local/hook')
        view = node.setupStateMonitoring()
        assert view['deviceCount'] == 2
        assert node.stateSubscriptionUrl == 'http://dash.local/hook'
        node.stopStatePolling()

    def test_setup_state_monitoring_survives_a_failed_subscription(self):
        session = FakeSession(URLError('cannot subscribe'), FakeResponse(DEVICE_ALL))
        node = make_node(session, stateSubscriptionUrl='http://dash.local/hook')
        view = node.setupStateMonitoring()
        assert view['deviceCount'] == 2
        node.stopStatePolling()

    def test_setup_state_monitoring_without_subscription_url_polls_only(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.setupStateMonitoring()
        assert node.stateRefreshStrategy()['subscriptionEnabled'] is False
        node.stopStatePolling()


# ---------------------------------------------------------------------------
# Polling fallback
# ---------------------------------------------------------------------------
class TestStatePolling:
    """The polling fallback: back-off, background loop lifecycle."""

    def test_poll_reads_every_device(self):
        session = FakeSession(FakeResponse(DEVICE_ALL))
        node = make_node(session)
        states = node.pollDeviceStates()
        assert set(states) == {'101', '102'}

    def test_poll_skips_while_backing_off(self):
        session = FakeSession(URLError('hub down'))
        node = make_node(session)
        node.pollDeviceStates()
        calls_after_failure = session.call_count
        assert node.pollDeviceStates() == {}
        assert session.call_count == calls_after_failure

    def test_force_refresh_poll_ignores_the_backoff(self):
        session = FakeSession(URLError('hub down'), URLError('hub down'))
        node = make_node(session)
        node.pollDeviceStates()
        node.pollDeviceStates(force_refresh=True)
        assert session.call_count == 2

    def test_backoff_grows_and_is_capped(self):
        session = FakeSession(*[URLError('hub down')] * 8)
        node = make_node(session)
        for _ in range(7):
            node.pollDeviceStates(force_refresh=True)
        assert node._state_backoff <= hubitat_integration.STATE_BACKOFF_MAX

    def test_success_clears_the_backoff(self):
        session = FakeSession(URLError('hub down'), FakeResponse(DEVICE_ALL))
        node = make_node(session)
        node.pollDeviceStates()
        assert node._state_backoff > 0
        node.pollDeviceStates(force_refresh=True)
        assert node._state_backoff == 0
        assert node._state_backoff_until == 0

    def test_start_polling_runs_a_daemon_thread(self):
        session = FakeSession()
        node = make_node(session, statePollInterval=20)
        thread = node.startStatePolling()
        assert thread.daemon is True
        assert thread.is_alive()
        node.stopStatePolling(timeout=2)
        assert not node._state_poll_thread

    def test_start_polling_is_idempotent(self):
        node = make_node(FakeSession(), statePollInterval=20)
        first = node.startStatePolling()
        second = node.startStatePolling()
        assert first is second
        node.stopStatePolling(timeout=2)

    def test_poll_loop_survives_transport_explosions(self):
        class Exploding:
            def __init__(self):
                self.calls = 0

            def request(self, method, url, timeout=None):
                self.calls += 1
                raise RuntimeError('kaboom')

        transport = Exploding()
        node = make_node(statePollInterval=20)
        node.stateSession = transport
        node.startStatePolling()
        # The loop backs off between failures, so poll until it ticks again.
        deadline = time.time() + 5
        while transport.calls < 2 and time.time() < deadline:
            node._state_backoff_until = 0.0  # skip the back-off wait for the test
            time.sleep(0.02)
        node.stopStatePolling(timeout=2)
        assert transport.calls >= 2

    def test_stop_polling_without_starting_is_safe(self):
        node = make_node()
        assert node.stopStatePolling() is None

    def test_strategy_reports_polling_active(self):
        node = make_node(FakeSession(), statePollInterval=20)
        node.startStatePolling()
        assert node.stateRefreshStrategy()['polling'] is True
        node.stopStatePolling(timeout=2)
        assert node.stateRefreshStrategy()['polling'] is False


# ---------------------------------------------------------------------------
# Configuration resolution
# ---------------------------------------------------------------------------
class TestStateConfiguration:
    """Credentials and tuning knobs come from config, then HUBITAT_* env."""

    def test_app_id_and_token_come_from_the_config(self):
        node = make_node()
        assert node.app_id == '99'
        assert node.access_token == 'test-access-token'

    def test_env_vars_are_used_as_fallbacks(self, monkeypatch):
        monkeypatch.setenv('HUBITAT_APP_ID', '77')
        monkeypatch.setenv('HUBITAT_ACCESS_TOKEN', 'env-token')
        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {'url': 'http://hub:8080'}, None)
        assert node.app_id == '77'
        assert node.access_token == 'env-token'

    def test_api_key_is_used_as_the_token_fallback(self, monkeypatch):
        monkeypatch.delenv('HUBITAT_ACCESS_TOKEN', raising=False)
        node = hubitat_integration.HUBITAT_NODE(
            'hubitat-control', {}, {'url': 'http://hub:8080', 'appId': '1', 'apiKey': 'key-123'}, None
        )
        assert node.access_token == 'key-123'

    def test_app_id_can_be_parsed_out_of_a_maker_api_url(self):
        node = hubitat_integration.HUBITAT_NODE(
            'hubitat-control', {}, {'url': 'http://hub:8080/apps/api/55', 'accessToken': 't'}, None
        )
        assert node.app_id == '55'
        assert node.maker_api_url == 'http://hub:8080/apps/api/55'

    def test_poll_interval_comes_from_config_then_env(self, monkeypatch):
        node = make_node(statePollInterval=15000)
        assert node.state_poll_interval == 15000
        monkeypatch.setenv('HUBITAT_STATE_POLL_MS', '3000')
        plain = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        assert plain.state_poll_interval == 3000

    def test_invalid_tuning_values_fall_back_to_defaults(self):
        node = make_node(statePollInterval='nonsense', stateTtl='nonsense', stateTimeout='nonsense')
        assert node.state_poll_interval == hubitat_integration.DEFAULT_STATE_POLL_MS
        assert node.state_ttl == hubitat_integration.DEFAULT_STATE_TTL
        assert node.state_timeout == hubitat_integration.DEFAULT_STATE_TIMEOUT

    def test_non_positive_tuning_values_fall_back_to_defaults(self):
        node = make_node(statePollInterval=0, stateTtl=-1, stateTimeout=-1)
        assert node.state_poll_interval == hubitat_integration.DEFAULT_STATE_POLL_MS
        assert node.state_ttl == hubitat_integration.DEFAULT_STATE_TTL
        assert node.state_timeout == hubitat_integration.DEFAULT_STATE_TIMEOUT

    def test_zero_ttl_means_never_cache(self):
        # 0 is a legitimate "always read the hub" setting, not a typo.
        node = make_node(stateTtl=0)
        assert node.state_ttl == 0

    def test_state_url_requires_credentials(self):
        node = make_node(appId=None, accessToken=None)
        node.appId = None
        node.accessToken = None
        with pytest.raises(ValueError):
            node.state_url('devices/all')

    def test_state_url_encodes_the_path(self):
        node = make_node()
        url = node.state_url('devices/101/attribute/switch')
        assert url.startswith('http://hub.local:8080/apps/api/99/devices/101/attribute/switch?')

    def test_access_token_is_never_logged(self, caplog):
        import logging as _logging

        session = FakeSession(FakeResponse(DEVICE_ALL), URLError('hub down'))
        node = make_node(session)
        with caplog.at_level(_logging.DEBUG, logger='flows.hubitat_integration'):
            node.refreshDeviceStates()
            node.refreshDeviceStates(force_refresh=True)
        assert 'test-access-token' not in caplog.text


# ---------------------------------------------------------------------------
# Default stdlib transport
# ---------------------------------------------------------------------------
class TestUrllibTransport:
    """The built-in transport, so state monitoring needs no extra dependency."""

    def test_successful_request_decodes_json(self, monkeypatch):
        payload = json.dumps(DEVICE_ALL).encode('utf-8')

        class FakeHttpResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(hubitat_integration, 'urlopen', lambda *a, **k: FakeHttpResponse())
        response = hubitat_integration._UrllibTransport().get('http://hub/devices/all', timeout=5)
        assert response.status_code == 200
        assert response.json()[0]['id'] == '101'
        assert response.ok is True

    def test_http_error_becomes_a_response(self, monkeypatch):
        def raise_http_error(*args, **kwargs):
            raise HTTPError('http://hub/x', 404, 'Not Found', None, io.BytesIO(b'{"error":"nope"}'))

        monkeypatch.setattr(hubitat_integration, 'urlopen', raise_http_error)
        response = hubitat_integration._UrllibTransport().get('http://hub/x')
        assert response.status_code == 404
        assert response.ok is False
        assert response.json() == {'error': 'nope'}

    def test_node_uses_the_default_transport_when_none_is_injected(self, monkeypatch):
        payload = json.dumps(SINGLE_DEVICE).encode('utf-8')

        class FakeHttpResponse:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return payload

        monkeypatch.setattr(hubitat_integration, 'urlopen', lambda *a, **k: FakeHttpResponse())
        node = make_node()
        state = node.getDeviceState('101')
        assert state.ok is True
        assert state.values['switch'] is True

    def test_module_level_transport_hook_is_used(self, monkeypatch):
        module_session = FakeSession(FakeResponse(SINGLE_DEVICE))
        monkeypatch.setattr(hubitat_integration, 'state_transport', module_session)
        node = make_node()
        state = node.getDeviceState('101')
        assert state.ok is True
        assert module_session.call_count == 1


# ===========================================================================
# Baseline tests (unchanged from the pre-existing suite) -- the API surface
# these cover is untouched by device state monitoring, so they must keep
# passing exactly as before.
# ===========================================================================
class TestHubitatNode:
    """Test suite for Hubitat integration functionality."""

    def test_hubitat_node_initialization(self):
        """Test that HubitatNode initializes correctly."""
        from flows import hubitat_integration

        # Create a mock RED context
        mock_red = Mock()
        mock_red.httpIn = Mock()

        # Create config
        config = {
            'url': 'http://hubitat.local:8080',
            'apiKey': 'test-api-key',
            'refresh': 60000
        }

        # Create node instance
        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, config, None)
        assert node is not None
        assert node.config['url'] == config['url']
        assert node.config['apiKey'] == config['apiKey']

    def test_hubitat_api_url_initialization(self):
        """Test that API URL is initialized correctly."""
        from flows import hubitat_integration

        config = {
            'url': 'http://custom-hubitat:8080',
            'apiKey': 'my-key'
        }

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, config, None)
        assert node.baseUrl == 'http://custom-hubitat:8080'

    def test_hubitat_default_url(self):
        """Test that default URL is used when none provided."""
        from flows import hubitat_integration

        config = {
            'apiKey': 'my-key'
        }

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, config, None)
        assert node.baseUrl == 'http://hubitat.local:8080'

    def test_refresh_devices_method(self):
        """Test that refreshDevices retrieves all devices."""
        from flows import hubitat_integration

        mock_red = Mock()
        mock_response = Mock()
        mock_devices = [
            {'id': 'dev1', 'name': 'Light 1', 'deviceType': 'light'},
            {'id': 'dev2', 'name': 'Switch 1', 'deviceType': 'switch'}
        ]
        mock_response.__iter__ = Mock(return_value=iter([b'{"devices":' + json.dumps(mock_devices).encode() + b'}']))
        mock_red.get = Mock(return_value=mock_response)

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()
        node.sendRequest.return_value = None

        # Mock the sendRequest to return devices
        node._last_request_response = {'devices': mock_devices}
        node.devices = []
        node.status = Mock()

        node.refreshDevices()

        # Should update device count in status
        assert node.status.called
        status_text = str(node.status.call_args)
        assert '2 devices' in status_text

    def test_get_devices_request(self):
        """Test that getDevices makes correct API request."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.getDevices(Mock(callback))

        # Should call sendRequest with GET method
        node.sendRequest.assert_called()

    def test_get_device_details(self):
        """Test that getDevice retrieves specific device details."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.getDevice('dev1', Mock(callback))

        # Should construct URL with device ID
        assert 'dev1' in str(node.sendRequest.call_args)

    def test_update_device(self):
        """Test that updateDevice makes PUT request."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.updateDevice('dev1', {'state': 'on'}, Mock(callback))

        # Should call sendRequest with PUT method
        call_args = node.sendRequest.call_args
        assert call_args[0][0] == 'PUT'

    def test_trigger_automation(self):
        """Test that triggerAutomation triggers automation."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.triggerAutomation('aut1', Mock(callback))

        # Should call sendRequest with POST method
        call_args = node.sendRequest.call_args
        assert call_args[0][0] == 'POST'
        assert 'automations/aut1/trigger' in call_args[0][1]

    def test_get_automations(self):
        """Test that getAutomations retrieves automation list."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.getAutomations(Mock(callback))

        # Should call sendRequest with GET method
        node.sendRequest.assert_called()

    def test_update_automation(self):
        """Test that updateAutomation updates automation config."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.updateAutomation('aut1', {'enabled': True}, Mock(callback))

        # Should call sendRequest with PUT method
        call_args = node.sendRequest.call_args
        assert call_args[0][0] == 'PUT'

    def test_delete_automation(self):
        """Test that deleteAutomation removes automation."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.deleteAutomation('aut1', Mock(callback))

        # Should call sendRequest with DELETE method
        call_args = node.sendRequest.call_args
        assert call_args[0][0] == 'DELETE'

    def test_update_device_state(self):
        """Test that updateDeviceState publishes state event."""
        from flows import hubitat_integration

        mock_red = Mock()
        mock_device = {'id': 'dev1', 'name': 'Light 1', 'state': 'on'}

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock(return_value=mock_device)

        node.updateDeviceState('dev1')

        # Should send message with topic
        assert node.send.called
        topic = node.send.call_args[1].get('topic', '')
        assert 'hubitat/device/dev1/state' in topic

    def test_get_automation_status(self):
        """Test that getAutomationStatus retrieves automation status."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        node.getAutomationStatus('aut1', Mock(callback))

        # Should call sendRequest with GET method
        node.sendRequest.assert_called()


class TestHubitatNodeIntegration:
    """Integration tests for HubitatNode."""

    def test_subscribe_device_event(self):
        """Test that device state subscription is handled."""
        from flows import hubitat_integration

        mock_red = Mock()

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.send = Mock()

        # Simulate device state event
        node.on('subscribe', {'type': 'device-state', 'deviceId': 'dev1'})

        # Should update device state
        node.updateDeviceState('dev1')

    def test_send_request_simulation(self):
        """Test that sendRequest simulates HTTP request."""
        from flows import hubitat_integration

        node = hubitat_integration.HUBITAT_NODE('hubitat-control', {}, {}, None)
        node.sendRequest = Mock()

        # Should return simulated response
        def callback(err, response):
            assert response['success'] == True
            assert 'Hubitat request completed' in response['message']

        node.sendRequest('GET', 'http://test', None, callback)
