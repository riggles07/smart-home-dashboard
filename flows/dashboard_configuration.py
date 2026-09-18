"""Dashboard configuration mirror -- Smart Home Dashboard UI structure.

Python mirror of ``flows/dashboard-configuration.js``: dashboard
name/version, tab and view layout, and node-type registrations.
"""

DEFAULT_LAYOUT = "landscape"
DEFAULT_REFRESH_MS = 5000
DEFAULT_THEME = "complete"

DASHBOARD_NAME = "Smart Home Dashboard"
DASHBOARD_VERSION = "1.0.0"

#: Node type that renders live Hubitat device state. Kept in sync with the
#: ``hubitat-device-state`` registration in ``flows/dashboard-configuration.js``
#: and the state logic in ``flows/hubitat_integration.py``.
DEVICE_STATE_NODE = "hubitat-device-state"


def dashboard_configuration(RED=None):
    """Return the Smart Home Dashboard configuration.

    Args:
        RED: Optional Node-RED runtime object (unused by the pure-Python
            mirror; kept for signature parity with the JS flow).

    Returns:
        dict: Dashboard configuration including the ``home-lab-monitor``,
        ``hubitat-control``, ``hubitat-device-state``, ``unifi-monitor`` and
        ``kanban-card`` node registrations.
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
                    "devices": {
                        "type": "page",
                        "name": "Devices",
                        # Device tiles are bound to the state node, so a tile
                        # re-renders on every published state snapshot.
                        "nodes": [
                            {
                                "type": DEVICE_STATE_NODE,
                                "group": "Device Status",
                                "width": 6,
                                "order": 1,
                            }
                        ],
                    },
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
        DEVICE_STATE_NODE: {
            "label": "Device Status",
            "tab": "dashboard",
            "view": "devices",
            "group": "Device Status",
            # Tile refresh is the dashboard's own UI refresh; the node's TTL
            # cache means N tiles cost one hub read per TTL window.
            "refresh": DEFAULT_REFRESH_MS,
            "ttl": 5,
            "layout": "grid",
            "attributes": [
                "switch",
                "level",
                "temperature",
                "humidity",
                "battery",
                "motion",
                "contact",
                "lock",
                "hue",
                "saturation",
                "colorTemperature",
            ],
        },
        "unifi-monitor": {"label": "Network Monitor"},
        "kanban-card": {"label": "Task Card"},
    }


def device_state_view(dashboard=None):
    """Return the device-state node registration from a dashboard config.

    The single place that knows the shape of the device-state tile config, so
    the dashboard layer and the tests cannot drift apart.
    """
    config = dashboard if isinstance(dashboard, dict) else dashboard_configuration()
    return dict(config.get(DEVICE_STATE_NODE) or {})


def render_device_status(hubitat_node, force_refresh=False, session=None):
    """Render the Hubitat device state as the dashboard's devices view.

    This is the wiring between the two halves of the feature: it calls the
    ``hubitat-control`` node (``flows/hubitat_integration.py``) for its status
    view and maps it onto the dashboard's device-state node, so device tiles and
    the status indicator reflect live hub values.

    Args:
        hubitat_node: A ``HubitatNode`` (or anything exposing
            ``getStatusView``/``refreshDeviceStates``).
        force_refresh: Bypass the node's TTL cache and read the hub now.
        session: Optional transport override, forwarded to the node.

    Returns:
        dict: ``{"view", "node", "status", "tiles", "ok", "deviceCount",
        "staleCount", "errorCount", "cache", "refreshStrategy"}`` ready for the
        dashboard devices view. When ``hubitat_node`` is unusable the tiles list
        is empty and ``status`` is ``"error"`` -- the dashboard degrades to an
        empty view instead of raising.
    """
    node_config = device_state_view()
    if hubitat_node is None or not hasattr(hubitat_node, "getStatusView"):
        return {
            "view": node_config.get("view", "devices"),
            "node": DEVICE_STATE_NODE,
            "status": "error",
            "ok": False,
            "deviceCount": 0,
            "staleCount": 0,
            "errorCount": 0,
            "tiles": [],
            "cache": {},
            "refreshStrategy": {},
            "error": "no Hubitat node configured for device state",
        }

    view = hubitat_node.getStatusView(force_refresh=force_refresh, session=session)
    if view.get("ok"):
        status = "ok"
    elif view.get("staleCount"):
        status = "degraded"
    else:
        status = "error"
    return {
        "view": node_config.get("view", "devices"),
        "node": DEVICE_STATE_NODE,
        "status": status,
        "ok": view.get("ok", False),
        "deviceCount": view.get("deviceCount", 0),
        "staleCount": view.get("staleCount", 0),
        "errorCount": view.get("errorCount", 0),
        "tiles": view.get("tiles", []),
        "cache": view.get("cache", {}),
        "refreshStrategy": view.get("refreshStrategy", {}),
    }


__all__ = [
    "dashboard_configuration",
    "device_state_view",
    "render_device_status",
    "DEVICE_STATE_NODE",
]
