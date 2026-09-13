"""
Tests for config/settings.js (Node-RED configuration)
"""
import pytest
import sys
import json
from pathlib import Path
import re


class TestSettingsConfiguration:
    """Test suite for Node-RED settings configuration."""

    def test_settings_file_exists(self):
        """Test that settings.js file exists."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        assert settings_path.exists(), f"Settings file not found at {settings_path}"

    def test_settings_has_node_red_config(self):
        """Test that settings has node-red configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'node_red:' in content

    def test_settings_has_port_configuration(self):
        """Test that settings has port configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'port:' in content
        assert '1880' in content

    def test_settings_has_admin_user(self):
        """Test that settings has admin user configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'admin:' in content
        assert 'user:' in content
        assert 'password:' in content

    def test_settings_has_http_admin_root(self):
        """Test that settings has httpAdminRoot configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpAdminRoot:' in content
        assert 'node-red' in content

    def test_settings_has_ui_theme(self):
        """Test that settings has UI theme configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'ui:' in content
        assert 'theme:' in content
        assert 'complete' in content

    def test_settings_has_tabs_configuration(self):
        """Test that settings has tabs configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'tabs:' in content
        assert 'file: flows/dashboard-configuration.js' in content

    def test_settings_has_dashboard_tab(self):
        """Test that settings has Dashboard tab configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert '- Dashboard' in content

    def test_settings_has_order_configuration(self):
        """Test that settings has tab order configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'order:' in content

    def test_settings_has_http_node_enabled(self):
        """Test that settings has httpNode enabled."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpNode: true' in content

    def test_settings_has_http_node_admin_auth(self):
        """Test that settings has httpNodeAdminAuth configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpNodeAdminAuth:' in content

    def test_settings_has_http_node_cors(self):
        """Test that settings has httpNodeCors configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpNodeCors:' in content
        assert 'origin: "*"' in content

    def test_settings_has_http_static_auth_disabled(self):
        """Test that settings has httpStaticAuth disabled."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpStaticAuth: false' in content

    def test_settings_has_logging_configuration(self):
        """Test that settings has logging configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'logging:' in content
        assert 'console:' in content
        assert 'file:' in content

    def test_settings_has_console_logging(self):
        """Test that settings has console logging configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'console:' in content
        assert 'level: info' in content

    def test_settings_has_file_logging(self):
        """Test that settings has file logging configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'file:' in content
        assert 'level: info' in content
        assert 'maxFiles:' in content
        assert 'maxSize:' in content

    def test_settings_has_plugins_configuration(self):
        """Test that settings has plugins configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'plugins:' in content

    def test_settings_has_dashboard_plugin(self):
        """Test that settings has dashboard plugin configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert '- dashboard' in content

    def test_settings_has_hubitat_plugin(self):
        """Test that settings has hubitat plugin configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert '- node-red-node-hubitat' in content

    def test_settings_has_unifi_plugin(self):
        """Test that settings has unifi plugin configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert '- node-red-node-unifi' in content

    def test_settings_has_kanban_plugin(self):
        """Test that settings has kanban plugin configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert '- node-red-contrib-kanbanflow' in content

    def test_settings_has_ssl_configuration(self):
        """Test that settings has SSL configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'ssl:' in content
        assert 'enabled: false' in content

    def test_settings_has_ssl_cert_path(self):
        """Test that settings has SSL cert path."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'cert:' in content
        assert 'ssl/certs/node-red.crt' in content

    def test_settings_has_ssl_key_path(self):
        """Test that settings has SSL key path."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'key:' in content
        assert 'ssl/private/node-red.key' in content

    def test_settings_has_static_file_path(self):
        """Test that settings has static file path configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpStatic:' in content
        assert '/usr/share/node-red' in content

    def test_settings_has_static_cdn(self):
        """Test that settings has static CDN configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpStaticCdn:' in content
        assert 'unpkg.com' in content

    def test_settings_has_static_legacy(self):
        """Test that settings has static legacy CDN configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpStaticLegacy:' in content

    def test_settings_has_static_auth_user(self):
        """Test that settings has static auth user configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpStaticAuthUser:' in content

    def test_settings_has_static_auth_pass(self):
        """Test that settings has static auth password configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'httpStaticAuthPass:' in content

    def test_settings_has_xheaders_configuration(self):
        """Test that settings has xheaders configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'xheaders: false' in content

    def test_settings_has_xforwarded_configuration(self):
        """Test that settings has xforwarded configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'xforwarded: false' in content

    def test_settings_has_server_configuration(self):
        """Test that settings has server configuration."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'server:' in content

    def test_settings_has_http_node_cors_credentials(self):
        """Test that settings has httpNodeCors credentials configured."""
        settings_path = Path(__file__).parent.parent / 'config' / 'settings.js'
        content = settings_path.read_text()

        assert 'credentials: false' in content
