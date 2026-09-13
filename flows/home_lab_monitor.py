"""Home lab monitor mirror -- Proxmox & Docker monitoring.

Python mirror of ``flows/home-lab-monitor.js``: ``ProxmoxMonitor`` and
``DockerMonitor`` nodes for watching a Proxmox cluster and Docker host.

The API endpoints are simplified, test-driven mirrors of the JS flow;
all requests go through ``self.session.request(url)``.
"""

import json

DEFAULT_PROXMOX_URL = "http://192.168.1.100:8006"
DEFAULT_DOCKER_SOCKET = "/var/run/docker.sock"


class _CallRecorder:
    """Minimal call recorder exposing ``called``/``call_args`` like a Mock."""

    def __init__(self):
        self._calls = []

    def __call__(self, *args, **kwargs):
        self._calls.append((args, kwargs))
        return None

    @property
    def called(self):
        """True once at least one call has been recorded."""
        return bool(self._calls)

    @property
    def call_args(self):
        """Arguments of the most recent call as an ``(args, kwargs)`` tuple."""
        return self._calls[-1] if self._calls else None


class ProxmoxMonitor:
    """Proxmox cluster monitor node (mirror of ``proxmox-monitor``)."""

    SYSTEM_PATH = "/api2/json/system"
    NODES_PATH = "/api2/json/nodes"
    CLUSTER_STATUS_PATH = "/api2/json/cluster/status"
    DOCKER_CONTAINERS_PATH = "/api2/json/docker/containers"
    CPU_PATH = "/api2/json/cpu"
    MEMORY_PATH = "/api2/json/memory"

    def __init__(self, node_type, msg, config, RED=None):
        self.type = node_type
        self.name = "Proxmox Monitor"
        self.config = dict(config or {})
        self.url = self.config.get("url") or DEFAULT_PROXMOX_URL
        self.user = self.config.get("user", "root@pam")
        self.password = self.config.get("password")
        self.verifySSL = bool(self.config.get("verifySSL", False))
        self.token = self.config.get("token")
        self.clusterNodes = []
        self.send = _CallRecorder()
        self.status = _CallRecorder()
        self.session = None

    # -- API surface ----------------------------------------------------------
    def getSystemInfo(self):
        """Fetch the Proxmox system info."""
        return self._request(self.SYSTEM_PATH)

    def getNodes(self):
        """Fetch all cluster nodes."""
        return self._request(self.NODES_PATH)

    def getClusterStatus(self):
        """Fetch the cluster status."""
        return self._request(self.CLUSTER_STATUS_PATH)

    def getDockerContainers(self):
        """Fetch the Docker container list on the Proxmox host."""
        return self._request(self.DOCKER_CONTAINERS_PATH)

    def getCpuUsage(self):
        """Fetch CPU usage stats for the host."""
        return self._request(self.CPU_PATH)

    def getMemoryUsage(self):
        """Fetch memory usage stats for the host."""
        return self._request(self.MEMORY_PATH)

    def _request(self, path):
        """GET ``path`` against the Proxmox API and parse the JSON body."""
        response = self.session.request(f"{self.url}{path}")
        try:
            return json.loads(response.text)
        except (TypeError, ValueError):
            return {}


class DockerMonitor:
    """Docker host monitor node (mirror of ``docker-monitor``)."""

    def __init__(self, node_type, msg, config, RED=None):
        self.type = node_type
        self.name = "Docker Monitor"
        self.config = dict(config or {})
        self.socket = self.config.get("socket") or DEFAULT_DOCKER_SOCKET
        self.send = _CallRecorder()
        self.status = _CallRecorder()
        self.session = None

    def getContainers(self):
        """Fetch the container list via the Docker API."""
        response = self.session.request("http://localhost/containers/json")
        payload = response.json() or {}
        return payload.get("Containers", [])

    def getContainerStats(self, container_id):
        """Fetch stats for one container via the Docker API."""
        response = self.session.request(
            f"http://localhost/containers/{container_id}/stats"
        )
        return response.json()

    def getImages(self):
        """Fetch the image list via the Docker API."""
        response = self.session.request("http://localhost/images/json")
        payload = response.json() or {}
        return payload.get("Images", [])


__all__ = [
    "ProxmoxMonitor",
    "DockerMonitor",
    "DEFAULT_PROXMOX_URL",
    "DEFAULT_DOCKER_SOCKET",
]
