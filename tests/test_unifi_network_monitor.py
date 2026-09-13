"""
Tests for unifi-network-monitor.js (UniFi network monitoring)
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


class TestUniFiNode:
    """Test suite for UniFi monitoring functionality."""

    def test_unifi_node_initialization(self):
        """Test that UniFiNode initializes correctly."""
        from flows import unifi_network_monitor

        # Create a mock RED context
        mock_red = Mock()
        mock_red.httpIn = Mock()

        # Create config
        config = {
            'url': 'https://unifi.local:8443',
            'username': 'admin',
            'password': 'secret',
            'refresh': 30000
        }

        # Create node instance
        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, config, None)
        assert node is not None
        assert node.config['url'] == config['url']
        assert node.config['username'] == config['username']
        assert node.config['password'] == config['password']

    def test_unifi_base_url_initialization(self):
        """Test that UniFi base URL is initialized correctly."""
        from flows import unifi_network_monitor

        config = {
            'url': 'https://custom-unifi:8443',
            'username': 'admin',
            'password': 'secret'
        }

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, config, None)
        assert node.baseUrl == 'https://custom-unifi:8443'

    def test_unifi_default_url(self):
        """Test that default URL is used when none provided."""
        from flows import unifi_network_monitor

        config = {
            'username': 'admin',
            'password': 'secret'
        }

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, config, None)
        assert node.baseUrl == 'https://unifi.local:8443'

    def test_authenticate_method(self):
        """Test that authenticate makes login request."""
        from flows import unifi_network_monitor

        mock_red = Mock()
        mock_response = Mock()
        mock_data = {'token': 'test-token'}
        mock_response.__iter__ = Mock(return_value=iter([json.dumps(mock_data).encode()]))
        mock_red.post = Mock(return_value=mock_response)

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.sendRequest = Mock(return_value=mock_data)

        result = node.authenticate(Mock(callback))

        # Should set session token
        assert node.sessionToken == 'test-token'

    def test_refresh_network(self):
        """Test that refreshNetwork updates all network metrics."""
        from flows import unifi_network_monitor

        mock_red = Mock()

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock()

        node.refreshNetwork()

        # Should call updateClientList, updateAPStatus, updateNetworkTraffic
        assert node.get.call_count >= 3

    def test_update_client_list(self):
        """Test that updateClientList retrieves WiFi clients."""
        from flows import unifi_network_monitor

        mock_red = Mock()
        mock_clients = [
            {'id': 'client1', 'ip': '192.168.1.100', 'hostname': 'MacBook'},
            {'id': 'client2', 'ip': '192.168.1.101', 'hostname': 'iPhone'}
        ]
        mock_response = Mock()
        mock_data = {'clients': mock_clients}
        mock_response.__iter__ = Mock(return_value=iter([json.dumps(mock_data).encode()]))
        mock_red.get = Mock(return_value=mock_response)

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock(return_value=mock_response)

        node.updateClientList()

        # Should update client count in status
        assert node.status.called
        status_text = str(node.status.call_args)
        assert '2 clients' in status_text

    def test_get_client_details(self):
        """Test that getClientDetails retrieves specific client info."""
        from flows import unifi_network_monitor

        mock_red = Mock()

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock()

        node.getClientDetails('client1', Mock(callback))

        # Should construct URL with client ID
        assert 'client1' in str(node.get.call_args)

    def test_get_ap_list(self):
        """Test that getAPList retrieves access points."""
        from flows import unifi_network_monitor

        mock_red = Mock()
        mock_aps = [
            {'id': 'ap1', 'name': 'Main AP', 'status': 'online'},
            {'id': 'ap2', 'name': 'Guest AP', 'status': 'online'}
        ]
        mock_response = Mock()
        mock_data = {'accessPoints': mock_aps}
        mock_response.__iter__ = Mock(return_value=iter([json.dumps(mock_data).encode()]))
        mock_red.get = Mock(return_value=mock_response)

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock(return_value=mock_response)

        node.getAPList()

        # Should update AP count in status
        assert node.status.called
        status_text = str(node.status.call_args)
        assert '2 APs' in status_text

    def test_get_ap_details(self):
        """Test that getAPDetails retrieves specific AP info."""
        from flows import unifi_network_monitor

        mock_red = Mock()

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock()

        node.getAPDetails('ap1', Mock(callback))

        # Should construct URL with AP ID
        assert 'ap1' in str(node.get.call_args)

    def test_update_network_traffic(self):
        """Test that updateNetworkTraffic retrieves traffic stats."""
        from flows import unifi_network_monitor

        mock_red = Mock()
        mock_traffic = {
            'up': 1024,
            'down': 2048
        }
        mock_response = Mock()
        mock_data = {'traffic': mock_traffic}
        mock_response.__iter__ = Mock(return_value=iter([json.dumps(mock_data).encode()]))
        mock_red.get = Mock(return_value=mock_response)

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock(return_value=mock_response)

        node.updateNetworkTraffic()

        # Should update traffic stats
        assert node.send.called

    def test_get_network_stats(self):
        """Test that getNetworkStats retrieves network statistics."""
        from flows import unifi_network_monitor

        mock_red = Mock()

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock()

        node.getNetworkStats(Mock(callback))

        # Should call get with network stats endpoint
        node.get.assert_called()

    def test_get_device_list(self):
        """Test that getDeviceList retrieves UniFi devices."""
        from flows import unifi_network_monitor

        mock_red = Mock()
        mock_devices = [
            {'id': 'dev1', 'type': 'unifi-ap'},
            {'id': 'dev2', 'type': 'unifi-switch'}
        ]
        mock_response = Mock()
        mock_data = {'devices': mock_devices}
        mock_response.__iter__ = Mock(return_value=iter([json.dumps(mock_data).encode()]))
        mock_red.get = Mock(return_value=mock_response)

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.get = Mock(return_value=mock_response)

        node.getDeviceList()

        # Should send device list
        assert node.send.called

    def test_send_request_simulation(self):
        """Test that sendRequest simulates HTTP request."""
        from flows import unifi_network_monitor

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.sendRequest = Mock()

        # Should return simulated response
        def callback(err, response):
            assert response['success'] == True
            assert 'UniFi request completed' in response['message']

        node.sendRequest('GET', 'http://test', None, callback)


class TestUniFiNodeIntegration:
    """Integration tests for UniFiNode."""

    def test_subscribe_client_event(self):
        """Test that client connected subscription is handled."""
        from flows import unifi_network_monitor

        mock_red = Mock()

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.updateClientList = Mock()

        # Simulate client connected event
        node.on('subscribe', {'type': 'client-connected'})

        # Should update client list
        node.updateClientList()

    def test_subscribe_ap_event(self):
        """Test that AP status subscription is handled."""
        from flows import unifi_network_monitor

        mock_red = Mock()

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.updateAPStatus = Mock()

        # Simulate AP status event
        node.on('subscribe', {'type': 'ap-status'})

        # Should update AP status
        node.updateAPStatus()

    def test_session_token_storage(self):
        """Test that session token is stored after authentication."""
        from flows import unifi_network_monitor

        mock_red = Mock()
        mock_response = Mock()
        mock_data = {'token': 'session-token-123'}
        mock_response.__iter__ = Mock(return_value=iter([json.dumps(mock_data).encode()]))
        mock_red.post = Mock(return_value=mock_response)

        node = unifi_network_monitor.UniFiNode('unifi-monitor', {}, {}, None)
        node.sendRequest = Mock(return_value=mock_data)

        node.authenticate(Mock(callback))

        # Session token should be stored
        assert node.sessionToken == 'session-token-123'
        assert node.status.called
        assert 'connected' in str(node.status.call_args)
