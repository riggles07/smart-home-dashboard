"""
Tests for dashboard-configuration.js (Device Status view wiring)

Covers the seam between the dashboard layout and the Hubitat state-monitoring
node: the ``hubitat-device-state`` registration, ``device_state_view()`` and
``render_device_status()``.  A fake Hubitat node stands in for the real one, so
no hub (and no HTTP) is involved.
"""
import json
import sys
from pathlib import Path

import pytest

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))

# ``flows.dashboard_configuration`` re-exports the *function* of that name, but
# this suite needs the module (``DEVICE_STATE_NODE``, ``device_state_view``), so
# import it directly -- ``tests/__init__.py`` has already put ``flows/`` on
# ``sys.path``.
import dashboard_configuration


class FakeHubitatState:
    """Stand-in for HubitatNode exposing only the state-view surface."""

    def __init__(self, view):
        self._view = view
        self.calls = []

    def getStatusView(self, force_refresh=False, session=None):
        self.calls.append({'force_refresh': force_refresh, 'session': session})
        return self._view

    def refreshDeviceStates(self, force_refresh=False, session=None):
        self.calls.append({'force_refresh': force_refresh, 'session': session})
        return self._view


def healthy_view():
    return {
        'view': 'devices',
        'title': 'Device Status',
        'ok': True,
        'deviceCount': 2,
        'staleCount': 0,
        'errorCount': 0,
        'lastRefresh': 1234.5,
        'refreshStrategy': {'mode': 'hybrid'},
        'cache': {'size': 2, 'ttlSeconds': 5.0},
        'tiles': [
            {'deviceId': '101', 'label': 'Light', 'ok': True, 'stale': False,
             'primary': {'attribute': 'switch', 'display': 'on'}},
            {'deviceId': '102', 'label': 'Motion', 'ok': True, 'stale': False,
             'primary': {'attribute': 'motion', 'display': 'inactive'}},
        ],
    }


class TestDeviceStateRegistration:
    """The dashboard advertises a device-state node the tiles bind to."""

    def test_device_state_node_is_registered(self):
        dashboard = dashboard_configuration.dashboard_configuration()
        assert dashboard_configuration.DEVICE_STATE_NODE in dashboard

    def test_device_state_node_has_tile_configuration(self):
        node = dashboard_configuration.device_state_view()
        assert node['label'] == 'Device Status'
        assert node['view'] == 'devices'
        assert node['layout'] == 'grid'
        assert node['refresh'] == 5000
        assert node['ttl'] == 5

    def test_device_state_node_renders_the_state_attributes(self):
        node = dashboard_configuration.device_state_view()
        for attribute in ('switch', 'level', 'hue', 'saturation',
                          'temperature', 'battery'):
            assert attribute in node['attributes']

    def test_devices_view_binds_the_state_node(self):
        dashboard = dashboard_configuration.dashboard_configuration()
        nodes = dashboard['tabs']['dashboard']['views']['devices']['nodes']
        assert len(nodes) == 1
        assert nodes[0]['type'] == dashboard_configuration.DEVICE_STATE_NODE

    def test_existing_node_registrations_are_preserved(self):
        dashboard = dashboard_configuration.dashboard_configuration()
        for name in ('home-lab-monitor', 'hubitat-control', 'unifi-monitor', 'kanban-card'):
            assert name in dashboard

    def test_device_state_view_accepts_an_explicit_config(self):
        custom = {dashboard_configuration.DEVICE_STATE_NODE: {'label': 'Custom'}}
        assert dashboard_configuration.device_state_view(custom)['label'] == 'Custom'

    def test_device_state_view_defaults_to_an_empty_dict(self):
        assert dashboard_configuration.device_state_view({}) == {}


class TestRenderDeviceStatus:
    """render_device_status() maps the node's view onto the dashboard view."""

    def test_healthy_view_renders_tiles(self):
        node = FakeHubitatState(healthy_view())
        rendered = dashboard_configuration.render_device_status(node)
        assert rendered['status'] == 'ok'
        assert rendered['ok'] is True
        assert rendered['deviceCount'] == 2
        assert len(rendered['tiles']) == 2
        assert rendered['tiles'][0]['primary']['display'] == 'on'

    def test_render_names_the_node_type_and_view(self):
        rendered = dashboard_configuration.render_device_status(FakeHubitatState(healthy_view()))
        assert rendered['node'] == dashboard_configuration.DEVICE_STATE_NODE
        assert rendered['view'] == 'devices'

    def test_render_forwards_force_refresh_and_session(self):
        node = FakeHubitatState(healthy_view())
        session = object()
        dashboard_configuration.render_device_status(node, force_refresh=True, session=session)
        assert node.calls == [{'force_refresh': True, 'session': session}]

    def test_stale_snapshot_renders_as_degraded(self):
        view = healthy_view()
        view.update({'ok': False, 'staleCount': 2,
                     'tiles': [dict(t, ok=False, stale=True) for t in view['tiles']]})
        rendered = dashboard_configuration.render_device_status(FakeHubitatState(view))
        assert rendered['status'] == 'degraded'
        assert rendered['staleCount'] == 2
        # Tiles are still delivered so the dashboard shows last known values.
        assert len(rendered['tiles']) == 2

    def test_hub_outage_renders_as_error_with_no_tiles(self):
        view = healthy_view()
        view.update({'ok': False, 'deviceCount': 0, 'errorCount': 0, 'tiles': []})
        rendered = dashboard_configuration.render_device_status(FakeHubitatState(view))
        assert rendered['status'] == 'error'
        assert rendered['tiles'] == []

    def test_missing_node_degrades_instead_of_raising(self):
        rendered = dashboard_configuration.render_device_status(None)
        assert rendered['status'] == 'error'
        assert rendered['ok'] is False
        assert rendered['tiles'] == []
        assert 'no Hubitat node' in rendered['error']

    def test_object_without_the_state_surface_is_treated_as_missing(self):
        rendered = dashboard_configuration.render_device_status(object())
        assert rendered['status'] == 'error'
        assert rendered['tiles'] == []

    def test_rendered_view_is_json_serialisable(self):
        rendered = dashboard_configuration.render_device_status(FakeHubitatState(healthy_view()))
        json.dumps(rendered)

    def test_cache_and_strategy_are_surfaced(self):
        rendered = dashboard_configuration.render_device_status(FakeHubitatState(healthy_view()))
        assert rendered['cache']['size'] == 2
        assert rendered['refreshStrategy']['mode'] == 'hybrid'
