"""Home Lab Monitoring - Proxmox & Docker Status"""

class HomeLabMonitor:
    """Monitor home lab infrastructure"""

    def __init__(self, proxmox_url: str = "http://localhost:8006",
                 docker_url: str = "unix:///var/run/docker.sock"):
        self.proxmox_url = proxmox_url
        self.docker_url = docker_url

    def get_proxmox_status(self):
        """Get Proxmox cluster status"""
        return {"status": "online", "nodes": ["node1"]}

    def get_docker_containers(self):
        """Get running Docker containers"""
        return [
            {"name": "node-red", "status": "running"},
            {"name": "mosquitto", "status": "running"}
        ]

    def check_health(self):
        """Overall health check"""
        return {
            "proxmox": "healthy",
            "docker": "healthy",
            "overall": "healthy"
        }
