"""Dashboard configuration mirror -- Smart Home Dashboard UI structure.

Python mirror of ``flows/dashboard-configuration.js``: dashboard
name/version, tab and view layout, and node-type registrations.

The ``hubitat-control`` registration also carries the *device control surface*
-- the widgets the Devices view renders and the handler that turns a widget
action into a Hubitat Maker API command --
:func:`device_control_surface` / :func:`handle_device_control`.
"""

DEFAULT_LAYOUT = "landscape"
DEFAULT_REFRESH_MS = 5000
DEFAULT_THEME = "complete"

DASHBOARD_NAME = "Smart Home Dashboard"
DASHBOARD_VERSION = "1.0.0"

#: UI group per device capability -- which control a widget renders.
CAPABILITY_WIDGET_TYPE = {
    "switch": "ui_switch",
    "dimmer": "ui_slider",
    "color-bulb": "ui_colour_picker",
    "common": "ui_button",
}


def _control_widgets():
    """Build the device-control widget descriptors for the Devices view.

    One entry per supported Maker API command, grouped by device capability, so
    the dashboard knows which widget to render and which command name to send.
    """
    from hubitat_integration import HubitatNode

    widgets = []
    for command, spec in sorted(HubitatNode.supportedCommands().items()):
        widgets.append(
            {
                "command": command,
                "capability": spec["capability"],
                "widget": CAPABILITY_WIDGET_TYPE.get(spec["capability"], "ui_button"),
                "args": list(spec["args"]),
                "required": list(spec["required"]),
                "description": spec["description"],
            }
        )
    return widgets


def device_control_surface():
    """Return the dashboard's device-control surface definition.

    This is what the ``hubitat-control`` node publishes to the Devices view:
    the topic the UI publishes control actions on, the topic results come back
    on, and the widget list derived from the supported Maker API commands.
    """
    return {
        "label": "Device Control",
        "type": "hubitat-control",
        "input_topic": "hubitat/device/+/control",
        "output_topic": "hubitat/device/+/command",
        "widgets": _control_widgets(),
    }


def handle_device_control(node, msg):
    """Route handler: map a dashboard control action onto a Hubitat command.

    Args:
        node: A ``HubitatNode`` (or anything exposing ``controlDevice``).
        msg: The Node-RED style message carrying the UI action, e.g.
            ``{"payload": {"deviceId": "101", "command": "setLevel", "value": 50}}``.

    Returns:
        dict: JSON-safe result for the dashboard, from
        :meth:`HubitatNode.controlDevice`.
    """
    result = node.controlDevice(msg)
    return result.to_dict() if hasattr(result, "to_dict") else result


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
        "hubitat-control": device_control_surface(),
        "unifi-monitor": {"label": "Network Monitor"},
        "kanban-card": {"label": "Task Card"},
    }


__all__ = [
    "dashboard_configuration",
    "device_control_surface",
    "handle_device_control",
]
