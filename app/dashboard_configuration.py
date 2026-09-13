"""Dashboard Configuration Module - Node-RED Dashboard Setup"""
DASHBOARD_CONFIG = {
    "id": "dashboard-configuration",
    "name": "Smart Home Dashboard",
    "version": "1.0.0",
    "flows": {
        "dashboard": {
            "title": "Smart Home Dashboard",
            "layout": "default",
            "widgets": ["proxmox-status", "docker-status", "hubitat-devices", "unifi-network", "kanban-board"]
        }
    }
}

def init_dashboard():
    """Initialize the Node-RED dashboard"""
    return {"status": "initialized", "config": DASHBOARD_CONFIG}

def get_dashboard_state():
    """Get current dashboard state"""
    return DASHBOARD_CONFIG.copy()

def validate_dashboard_config(config):
    """Validate dashboard configuration"""
    required = ["id", "name", "flows"]
    return all(k in config for k in required)
