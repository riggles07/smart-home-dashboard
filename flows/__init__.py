"""Python mirrors of the Node-RED flow modules (``flows/*.js``).

The ``flows`` directory ships the Node-RED JavaScript flows plus these
Python mirror modules, which encode the same behaviour so the dashboard
logic can be unit-tested with pytest without a running Node-RED instance.

This package also places its own directory on ``sys.path`` and re-exports
the mirror modules, so ``flows.<name>`` and the bare ``<name>`` import
resolve to the same module object (tests use both forms, and
``unittest.mock.patch`` targets the bare module names).
"""

import os as _os
import sys as _sys

_FLOWS_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _FLOWS_DIR not in _sys.path:
    _sys.path.insert(0, _FLOWS_DIR)

import dashboard_configuration as _dashboard_configuration  # noqa: E402
import home_lab_monitor as _home_lab_monitor  # noqa: E402
import hubitat_integration as _hubitat_integration  # noqa: E402
import integration_functions as _integration_functions  # noqa: E402
import kanban_flow as _kanban_flow  # noqa: E402
import unifi_network_monitor as _unifi_network_monitor  # noqa: E402

# Re-export the modules so `from flows import X` and `import X` (with the
# flows directory on sys.path) yield the same module object.
home_lab_monitor = _home_lab_monitor
hubitat_integration = _hubitat_integration
integration_functions = _integration_functions
kanban_flow = _kanban_flow
unifi_network_monitor = _unifi_network_monitor

# The dashboard configuration is exposed as a callable, mirroring the JS
# flow module which returns the configuration object.
dashboard_configuration = _dashboard_configuration.dashboard_configuration

# The Hubitat device-control surface and its route handler live in the
# dashboard configuration module; re-export them so the dashboard layer can
# reach device commands via ``flows``.
device_control_surface = _dashboard_configuration.device_control_surface
handle_device_control = _dashboard_configuration.handle_device_control

__all__ = [
    "dashboard_configuration",
    "device_control_surface",
    "handle_device_control",
    "home_lab_monitor",
    "hubitat_integration",
    "integration_functions",
    "kanban_flow",
    "unifi_network_monitor",
]
