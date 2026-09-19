"""
Tests for dashboard-configuration.js
"""
import pytest
import sys
from pathlib import Path

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))


class TestDashboardConfiguration:
    """Test suite for the Smart Home Dashboard configuration flow."""

    def test_dashboard_module_exports_function(self):
        """Test that the module exports a function."""
        from flows import dashboard_configuration
        assert callable(dashboard_configuration)

    def test_dashboard_config_structure(self):
        """Test that dashboard configuration has required structure."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        assert 'name' in dashboard
        assert dashboard['name'] == 'Smart Home Dashboard'
        assert 'version' in dashboard
        assert dashboard['version'] == '1.0.0'
        assert 'tabs' in dashboard
        assert 'layout' in dashboard
        assert dashboard['layout'] == 'landscape'
        assert 'refresh' in dashboard
        assert 'theme' in dashboard

    def test_tab_configuration(self):
        """Test that dashboard has proper tab configuration."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        assert 'dashboard' in dashboard['tabs']
        tab = dashboard['tabs']['dashboard']
        assert tab['name'] == 'Dashboard'
        assert 'views' in tab
        assert 'order' in tab

    def test_views_structure(self):
        """Test that dashboard has all required views."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        expected_views = ['main', 'monitor', 'devices', 'settings']
        for view_name in expected_views:
            assert view_name in dashboard['tabs']['dashboard']['views']

    def test_view_configuration(self):
        """Test that each view has proper configuration."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        for view_name in ['main', 'monitor', 'devices', 'settings']:
            view = dashboard['tabs']['dashboard']['views'][view_name]
            assert 'type' in view
            assert 'name' in view
            assert 'nodes' in view

    def test_home_lab_monitor_node_type(self):
        """Test that home-lab-monitor node type is registered."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)
        assert 'home-lab-monitor' in dashboard

    def test_hubitat_control_node_type(self):
        """Test that hubitat-control node type is registered."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)
        assert 'hubitat-control' in dashboard

    def test_unifi_monitor_node_type(self):
        """Test that unifi-monitor node type is registered."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)
        assert 'unifi-monitor' in dashboard

    def test_kanban_card_node_type(self):
        """Test that kanban-card node type is registered."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)
        assert 'kanban-card' in dashboard

    def test_node_status_configuration(self):
        """Test that home-lab-monitor has status configuration."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        monitor = dashboard['home-lab-monitor']
        assert 'label' in monitor
        assert monitor['label'] == 'Node Status'
        assert 'format' in monitor
        assert monitor['format'] == '%%'
        assert 'min' in monitor
        assert monitor['min'] == 0
        assert 'max' in monitor
        assert monitor['max'] == 100

    def test_hubitat_device_control_config(self):
        """Test that hubitat-control has device control configuration."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        control = dashboard['hubitat-control']
        assert control['label'] == 'Device Control'

    def test_unifi_network_monitor_config(self):
        """Test that unifi-monitor has network monitoring configuration."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        monitor = dashboard['unifi-monitor']
        assert monitor['label'] == 'Network Monitor'

    def test_kanban_task_card_config(self):
        """Test that kanban-card has task card configuration."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        card = dashboard['kanban-card']
        assert card['label'] == 'Task Card'

    def test_hubitat_automation_node_type(self):
        """Test that the automation trigger node type is registered."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)
        assert 'hubitat-automation' in dashboard

    def test_hubitat_automation_config(self):
        """Test that the automation node carries its topics and default action."""
        from flows import dashboard_configuration
        dashboard = dashboard_configuration(None)

        automation = dashboard['hubitat-automation']
        assert automation['label'] == 'Automation Triggers'
        assert automation['listTopic'] == 'hubitat/automations'
        assert automation['resultTopic'] == 'hubitat/automation/result'
        assert automation['action'] == 'runRuleAct'

    def test_automation_topics_match_integration_module(self):
        """The dashboard topics must match the ones the node publishes on."""
        import dashboard_configuration as config_module  # the flows mirror module
        from flows import dashboard_configuration, hubitat_integration

        automation = dashboard_configuration(None)['hubitat-automation']
        assert automation['listTopic'] == hubitat_integration.AUTOMATION_TOPIC
        assert automation['resultTopic'] == hubitat_integration.AUTOMATION_RESULT_TOPIC
        assert automation['action'] == hubitat_integration.DEFAULT_TRIGGER_ACTION
        assert config_module.DEFAULT_TRIGGER_ACTION == hubitat_integration.DEFAULT_TRIGGER_ACTION
