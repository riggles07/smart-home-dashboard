"""
Tests for integration-functions.js (API integration logic)
"""
import pytest
import sys
import asyncio
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))


def callback(*args, **kwargs):
    """No-op callback used as a placeholder in Mock(callback) calls."""
    return None


class TestHubitatAPI:
    """Test suite for Hubitat API integration."""

    def test_hubitat_api_initialization(self):
        """Test that HubitatAPI initializes correctly."""
        from flows import integration_functions

        config = {
            'url': 'http://hubitat.local:8080',
            'apiKey': 'test-api-key'
        }

        api = integration_functions.hubitatAPI
        api.init(config)

        assert api.BASE_URL == config['url']
        assert api.API_KEY == config['apiKey']

    def test_hubitat_api_default_url(self):
        """Test that HubitatAPI uses default URL when none provided."""
        from flows import integration_functions

        config = {
            'apiKey': 'test-api-key'
        }

        api = integration_functions.hubitatAPI
        api.init(config)

        assert api.BASE_URL == 'http://hubitat.local:8080'

    def test_hubitat_get_status(self):
        """Test that getStatus makes correct API call."""
        from flows import integration_functions

        api = integration_functions.hubitatAPI
        api.init({'url': 'http://test.local', 'apiKey': 'key'})

        mock_response = Mock()
        mock_response.json = Mock(return_value={'status': 'online', 'version': '1.0'})
        api.fetch = Mock(return_value=mock_response)

        # Mock fetch to return status
        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'status': 'online'})
            mock_fetch.return_value = mock_response

            result = api.getStatus()

            # Should construct correct URL
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[0][0]
            assert 'hubitat.local:8080' in call_args
            assert '/api/v1/status' in call_args

    def test_hubitat_get_devices(self):
        """Test that getDevices makes correct API call."""
        from flows import integration_functions

        api = integration_functions.hubitatAPI
        api.init({'url': 'http://test.local', 'apiKey': 'key'})

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={
                'devices': [
                    {'id': 'dev1', 'name': 'Light 1'},
                    {'id': 'dev2', 'name': 'Switch 1'}
                ]
            })
            mock_fetch.return_value = mock_response

            result = api.getDevices()

            # Should call with devices endpoint
            mock_fetch.assert_called()
            call_args = mock_fetch.call_args[0][0]
            assert 'devices' in call_args

    def test_hubitat_get_device(self):
        """Test that getDevice retrieves specific device."""
        from flows import integration_functions

        api = integration_functions.hubitatAPI
        api.init({'url': 'http://test.local', 'apiKey': 'key'})

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'id': 'dev1', 'name': 'Test Device'})
            mock_fetch.return_value = mock_response

            result = api.getDevice('dev1')

            # Should include device ID in URL
            call_args = mock_fetch.call_args[0][0]
            assert 'dev1' in call_args

    def test_hubitat_update_device(self):
        """Test that updateDevice makes PUT request."""
        from flows import integration_functions

        api = integration_functions.hubitatAPI
        api.init({'url': 'http://test.local', 'apiKey': 'key'})

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'id': 'dev1', 'state': 'on'})
            mock_fetch.return_value = mock_response

            result = api.updateDevice('dev1', {'state': 'on'})

            # Should use PUT method
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args
            assert call_args[1]['method'] == 'PUT'

    def test_hubitat_trigger_automation(self):
        """Test that triggerAutomation triggers automation."""
        from flows import integration_functions

        api = integration_functions.hubitatAPI
        api.init({'url': 'http://test.local', 'apiKey': 'key'})

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'success': True})
            mock_fetch.return_value = mock_response

            result = api.triggerAutomation('aut1')

            # Should call with trigger endpoint
            call_args = mock_fetch.call_args[0][0]
            assert 'trigger' in call_args


class TestUniFiAPI:
    """Test suite for UniFi API integration."""

    def test_unifi_api_initialization(self):
        """Test that UniFiAPI initializes correctly."""
        from flows import integration_functions

        config = {
            'url': 'https://unifi.local:8443',
            'username': 'admin',
            'password': 'secret'
        }

        api = integration_functions.unifiAPI
        api.init(config)

        assert api.BASE_URL == config['url']
        assert api.USERNAME == config['username']
        assert api.PASSWORD == config['password']

    def test_unifi_api_default_url(self):
        """Test that UniFiAPI uses default URL when none provided."""
        from flows import integration_functions

        config = {
            'username': 'admin',
            'password': 'secret'
        }

        api = integration_functions.unifiAPI
        api.init(config)

        assert api.BASE_URL == 'https://unifi.local:8443'

    def test_unifi_authenticate(self):
        """Test that authenticate makes login request."""
        from flows import integration_functions

        api = integration_functions.unifiAPI
        api.init({'url': 'https://test.local:8443', 'username': 'admin', 'password': 'pass'})

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'token': 'session-token-123'})
            mock_fetch.return_value = mock_response

            result = api.authenticate()

            # Should call login endpoint
            mock_fetch.assert_called_once()
            call_args = mock_fetch.call_args[0][0]
            assert '/api/login' in call_args

    def test_unifi_get(self):
        """Test that get makes GET request."""
        from flows import integration_functions

        api = integration_functions.unifiAPI
        api.init({'url': 'https://test.local:8443', 'username': 'admin', 'password': 'pass'})
        api.SESSION_TOKEN = 'test-token'

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'data': 'test'})
            mock_fetch.return_value = mock_response

            result = api.get('/rest/smartapi/apis/smart/v2/ubnt/network/clients')

            # Should include session token in headers
            mock_fetch.assert_called()
            call_kwargs = mock_fetch.call_args[1]
            assert 'Authorization' in call_kwargs['headers']
            assert 'Bearer test-token' in call_kwargs['headers']['Authorization']

    def test_unifi_get_clients(self):
        """Test that getClients retrieves WiFi clients."""
        from flows import integration_functions

        api = integration_functions.unifiAPI
        api.init({'url': 'https://test.local:8443', 'username': 'admin', 'password': 'pass'})
        api.SESSION_TOKEN = 'test-token'

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'clients': []})
            mock_fetch.return_value = mock_response

            result = api.getClients()

            # Should call clients endpoint
            call_args = mock_fetch.call_args[0][0]
            assert 'clients' in call_args

    def test_unifi_get_access_points(self):
        """Test that getAccessPoints retrieves AP list."""
        from flows import integration_functions

        api = integration_functions.unifiAPI
        api.init({'url': 'https://test.local:8443', 'username': 'admin', 'password': 'pass'})
        api.SESSION_TOKEN = 'test-token'

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'accessPoints': []})
            mock_fetch.return_value = mock_response

            result = api.getAccessPoints()

            # Should call AP endpoint
            call_args = mock_fetch.call_args[0][0]
            assert 'cap/wlan' in call_args

    def test_unifi_get_network_traffic(self):
        """Test that getNetworkTraffic retrieves traffic stats."""
        from flows import integration_functions

        api = integration_functions.unifiAPI
        api.init({'url': 'https://test.local:8443', 'username': 'admin', 'password': 'pass'})
        api.SESSION_TOKEN = 'test-token'

        with patch('integration_functions.fetch') as mock_fetch:
            mock_response = Mock()
            mock_response.json = Mock(return_value={'traffic': {'up': 1000, 'down': 2000}})
            mock_fetch.return_value = mock_response

            result = api.getNetworkTraffic()

            # Should call traffic endpoint
            call_args = mock_fetch.call_args[0][0]
            assert 'traffic' in call_args


class TestHTTPHelper:
    """Test suite for HTTP helper functions."""

    def test_http_helper_get(self):
        """Test that httpHelper.get makes GET request."""
        from flows import integration_functions

        helper = integration_functions.httpHelper
        helper.request = Mock()

        helper.get('http://test.local', Mock(callback))

        # Should call request with GET
        helper.request.assert_called_once()
        call_args = helper.request.call_args[0][0]
        assert call_args['method'] == 'GET'

    def test_http_helper_post(self):
        """Test that httpHelper.post makes POST request."""
        from flows import integration_functions

        helper = integration_functions.httpHelper
        helper.request = Mock()

        helper.post('http://test.local', {'data': 'test'}, Mock(callback))

        # Should call request with POST
        helper.request.assert_called_once()
        call_args = helper.request.call_args[0][0]
        assert call_args['method'] == 'POST'
        assert 'data' in call_args['body']

    def test_http_helper_put(self):
        """Test that httpHelper.put makes PUT request."""
        from flows import integration_functions

        helper = integration_functions.httpHelper
        helper.request = Mock()

        helper.put('http://test.local', {'data': 'test'}, Mock(callback))

        # Should call request with PUT
        helper.request.assert_called_once()
        call_args = helper.request.call_args[0][0]
        assert call_args['method'] == 'PUT'


class TestUtils:
    """Test suite for utility functions."""

    def test_format_date(self):
        """Test that formatDate converts date to ISO string."""
        from flows import integration_functions

        utils = integration_functions.utils

        result = utils.formatDate('2024-01-15T10:30:00Z')

        assert result == '2024-01-15T10:30:00.000Z'

    def test_format_date_none(self):
        """Test that formatDate handles None input."""
        from flows import integration_functions

        utils = integration_functions.utils

        result = utils.formatDate(None)

        assert result == ''

    def test_parse_json_valid(self):
        """Test that parseJSON correctly parses valid JSON."""
        from flows import integration_functions

        utils = integration_functions.utils

        result = utils.parseJSON('{"key": "value"}')

        assert result == {'key': 'value'}

    def test_parse_json_invalid(self):
        """Test that parseJSON handles invalid JSON gracefully."""
        from flows import integration_functions

        utils = integration_functions.utils

        result = utils.parseJSON('invalid json')

        assert result is None

    def test_validate_config(self):
        """Test that validateConfig checks required fields."""
        from flows import integration_functions

        utils = integration_functions.utils

        # Should pass with all required fields
        config = {'url': 'http://test', 'apiKey': 'key'}
        utils.validateConfig(config, ['url', 'apiKey'])

        # Should raise error with missing field
        with pytest.raises(Exception) as exc_info:
            utils.validateConfig({'url': 'http://test'}, ['url', 'apiKey'])

        assert 'apiKey' in str(exc_info.value)

    def test_debounce(self):
        """Test that debounce limits function calls."""
        from flows import integration_functions

        utils = integration_functions.utils

        calls = []
        debounced_func = utils.debounce(lambda: calls.append(1), 100)

        # Call multiple times in quick succession
        debounced_func()
        debounced_func()
        debounced_func()

        # Rapid calls within the wait window are coalesced into one run
        assert len(calls) == 1

    def test_throttle(self):
        """Test that throttle limits function calls."""
        from flows import integration_functions

        utils = integration_functions.utils

        calls = []

        throttled_func = utils.throttle(lambda: calls.append(1), 100)

        # Call multiple times in quick succession
        throttled_func()
        throttled_func()
        throttled_func()

        # Only the first call within the limit window executes
        assert len(calls) == 1
