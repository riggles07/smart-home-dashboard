"""Dashboard configuration mirror -- Smart Home Dashboard UI structure.

Python mirror of ``flows/dashboard-configuration.js``: dashboard
name/version, tab and view layout, and node-type registrations.
"""

DEFAULT_LAYOUT = "landscape"
DEFAULT_REFRESH_MS = 5000
DEFAULT_THEME = "complete"

DASHBOARD_NAME = "Smart Home Dashboard"
DASHBOARD_VERSION = "1.0.0"


def dashboard_configuration(RED=None):
    """Return the Smart Home Dashboard configuration.

    Args:
        RED: Optional Node-RED runtime object (unused by the pure-Python
            mirror; kept for signature parity with the JS flow).

    Returns:
        dict: Dashboard configuration including the ``home-lab-monitor``,
        ``hubitat-control``, ``unifi-monitor`` and ``kanban-card`` node
        registrations.
    """
    return {
        "name": DASHBOARD_NAME,
        "version": DASHBOARD_VERSION,
        "tabs": {
            "dashboard": {
                "name": "Dashboard",
                "order": 1,
                "views": {
                    "main": {"type": "page", "name": "Main View", "nodes": []},
                    "monitor": {"type": "page", "name": "Monitor View", "nodes": []},
                    "devices": {"type": "page", "name": "Devices", "nodes": []},
                    "settings": {"type": "page", "name": "Settings", "nodes": []},
                },
            }
        },
        "layout": DEFAULT_LAYOUT,
        "refresh": DEFAULT_REFRESH_MS,
        "theme": DEFAULT_THEME,
        "home-lab-monitor": {
            "label": "Node Status",
            "format": "%%",
            "min": 0,
            "max": 100,
        },
        "hubitat-control": {"label": "Device Control"},
        "unifi-monitor": {"label": "Network Monitor"},
        "kanban-card": {"label": "Task Card"},
    }


__all__ = ["dashboard_configuration"]
