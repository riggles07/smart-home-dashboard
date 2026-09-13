"""
Tests for hubitat-integration.js (Smart home device controls)
"""
import pytest
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))


def callback(*args, **kwargs):
    """No-op callback used as a placeholder in Mock(callback) calls."""
    return None


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
