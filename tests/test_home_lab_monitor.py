"""
Tests for home-lab-monitor.js (Proxmox & Docker monitoring)
"""
import pytest
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call

# Add flows to path
sys.path.insert(0, str(Path(__file__).parent.parent / 'flows'))

import home_lab_monitor


class TestProxmoxMonitor:
    """Test suite for Proxmox monitoring node."""

    def test_proxmox_monitor_initialization(self):
        """Test that ProxmoxMonitor initializes correctly."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, None, mock_red)

        assert monitor.name == "Proxmox Monitor"
        assert monitor.type == "home-lab-monitor"

    def test_proxmox_proxy_initialization(self):
        """Test that ProxmoxMonitor initializes with proxy configuration."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://proxmox.local:8006",
            "user": "admin@pam",
            "password": "secret",
            "verifySSL": False
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)

        assert monitor.url == "http://proxmox.local:8006"
        assert monitor.user == "admin@pam"
        assert monitor.password == "secret"
        assert monitor.verifySSL is False

    def test_proxmox_proxy_default_url(self):
        """Test that ProxmoxMonitor uses default URL when none provided."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "user": "admin@pam",
            "password": "secret"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)

        assert monitor.url == "http://192.168.1.100:8006"

    def test_proxmox_get_system_info(self):
        """Test that getSystemInfo makes correct API call."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock()

        mock_response = Mock()
        mock_response.text = '{"version":"7.1"}'
        monitor.session.request.return_value = mock_response

        result = monitor.getSystemInfo()

        # Should call request with correct endpoint
        monitor.session.request.assert_called()
        call_args = monitor.session.request.call_args[0][0]
        assert '/api2/json/' in call_args
        assert 'system' in call_args

    def test_proxmox_get_nodes(self):
        """Test that getNodes retrieves all nodes."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock()

        mock_response = Mock()
        mock_response.text = '{"data":[{"type":"node","name":"node1"}]}'
        monitor.session.request.return_value = mock_response

        result = monitor.getNodes()

        # Should call request with nodes endpoint
        call_args = monitor.session.request.call_args[0][0]
        assert 'nodes' in call_args

    def test_proxmox_get_cluster_status(self):
        """Test that getClusterStatus retrieves cluster info."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock()

        mock_response = Mock()
        mock_response.text = '{"version":"7.1","datacenter":"dc1"}'
        monitor.session.request.return_value = mock_response

        result = monitor.getClusterStatus()

        # Should call request with cluster endpoint
        call_args = monitor.session.request.call_args[0][0]
        assert 'cluster' in call_args

    def test_proxmox_get_docker_containers(self):
        """Test that getDockerContainers retrieves container list."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock()

        mock_response = Mock()
        mock_response.text = '{"data":[]}'
        monitor.session.request.return_value = mock_response

        result = monitor.getDockerContainers()

        # Should call request with containers endpoint
        call_args = monitor.session.request.call_args[0][0]
        assert 'containers' in call_args

    def test_proxmox_get_cpu_usage(self):
        """Test that getCpuUsage retrieves CPU usage stats."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock()

        mock_response = Mock()
        mock_response.text = '{"load":[[0.5,0.5,0.5]]}'
        monitor.session.request.return_value = mock_response

        result = monitor.getCpuUsage()

        # Should call request with cpu usage endpoint
        call_args = monitor.session.request.call_args[0][0]
        assert 'cpu' in call_args

    def test_proxmox_get_memory_usage(self):
        """Test that getMemoryUsage retrieves memory usage stats."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock()

        mock_response = Mock()
        mock_response.text = '{"total":10000000000,"used":5000000000}'
        monitor.session.request.return_value = mock_response

        result = monitor.getMemoryUsage()

        # Should call request with memory endpoint
        call_args = monitor.session.request.call_args[0][0]
        assert 'memory' in call_args or 'disk' in call_args

    def test_proxmox_handle_error(self):
        """Test that handleError catches exceptions properly."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "url": "http://test.local:8006",
            "user": "admin@pam",
            "password": "pass"
        }

        monitor = home_lab_monitor.ProxmoxMonitor("home-lab-monitor", {}, config, mock_red)
        monitor.session = Mock()
        monitor.session.request = Mock(side_effect=Exception("Connection failed"))

        with pytest.raises(Exception):
            monitor.getSystemInfo()


class TestDockerMonitor:
    """Test suite for Docker monitoring node."""

    def test_docker_monitor_initialization(self):
        """Test that DockerMonitor initializes correctly."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        monitor = home_lab_monitor.DockerMonitor("docker-monitor", {}, None, mock_red)

        assert monitor.name == "Docker Monitor"
        assert monitor.type == "docker-monitor"

    def test_docker_monitor_default_socket(self):
        """Test that DockerMonitor uses default socket path."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {}

        monitor = home_lab_monitor.DockerMonitor("docker-monitor", {}, config, mock_red)

        assert monitor.socket == "/var/run/docker.sock"

    def test_docker_monitor_custom_socket(self):
        """Test that DockerMonitor accepts custom socket path."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {
            "socket": "/custom/docker.sock"
        }

        monitor = home_lab_monitor.DockerMonitor("docker-monitor", {}, config, mock_red)

        assert monitor.socket == "/custom/docker.sock"

    def test_docker_get_containers(self):
        """Test that getContainers retrieves container list."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {}

        monitor = home_lab_monitor.DockerMonitor("docker-monitor", {}, config, mock_red)
        monitor.session = Mock()

        mock_response = Mock()
        mock_response.json = Mock(return_value={
            "Containers": [
                {"Name": "container1", "Status": "running", "Image": "nginx:latest"},
                {"Name": "container2", "Status": "stopped", "Image": "alpine:latest"}
            ]
        })
        monitor.session.request = Mock(return_value=mock_response)

        result = monitor.getContainers()

        # Should return container list
        assert isinstance(result, list)
        assert len(result) == 2

    def test_docker_get_container_stats(self):
        """Test that getContainerStats retrieves container statistics."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {}

        monitor = home_lab_monitor.DockerMonitor("docker-monitor", {}, config, mock_red)
        monitor.session = Mock()

        mock_response = Mock()
        mock_response.json = Mock(return_value={
            "Read": "2024-01-15T10:30:00Z",
            "CPUSec": "1000.5",
            "SystemCpuUsed": "500.2"
        })
        monitor.session.request = Mock(return_value=mock_response)

        result = monitor.getContainerStats("container1")

        # Should return stats object
        assert result is not None

    def test_docker_get_images(self):
        """Test that getImages retrieves image list."""
        mock_red = Mock()
        mock_red.nodes.addType = Mock()

        config = {}

        monitor = home_lab_monitor.DockerMonitor("docker-monitor", {}, config, mock_red)
        monitor.session = Mock()

        mock_response = Mock()
        mock_response.json = Mock(return_value={
            "Images": [
                {"Id": "sha256:abc123", "RepoTags": ["nginx:latest"]},
                {"Id": "sha256:def456", "RepoTags": ["alpine:latest"]}
            ]
        })
        monitor.session.request = Mock(return_value=mock_response)

        result = monitor.getImages()

        # Should return image list
        assert isinstance(result, list)
        assert len(result) == 2
