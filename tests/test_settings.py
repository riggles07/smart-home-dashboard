"""
Tests for config/settings.js -- the Node-RED settings for this project.

HISTORY / WHY THIS FILE WAS REWRITTEN
-------------------------------------
The previous version had 33 tests that grepped config/settings.js for string
literals, including keys that are NOT part of Node-RED's settings schema:
`plugins`, `flowFiles`, `server.ssl`, `httpStaticHeaders`, and the dashboard's
`ui.theme` / `ui.css` / `ui.tabs` / `ui.order`.

That combination was self-consistent but wrong in two independent ways, and it
broke CI on every push:

  1. The file under test was YAML (starting with a '#' comment) saved as .js, so
     Node-RED could never have loaded it. `node --check` rejected it.
  2. Two tests asserted the fabricated plugin list. When the repo's plugin names
     (node-red-node-hubitat / -unifi) diverged from the real npm packages
     (node-red-contrib-hubitat / -unifi), the suite failed -- and CI went red on
     every push, hiding real regressions.

The rule these tests now enforce: settings.js must be VALID JAVASCRIPT and must
contain ONLY keys Node-RED actually documents. A grep-based test cannot detect a
fabricated key, because the test itself encodes which keys are expected.
"""
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "config" / "settings.js"

# Keys that are NOT Node-RED settings. Their presence means someone copied an
# invented configuration; each one either breaks the file or is silently ignored.
# See https://nodered.org/docs/user-guide/runtime/configuration
FABRICATED = [
    "plugins:",
    "flowFiles",
    "functionRepo",
    "projectsDir",
    "httpStaticHeaders",
    "server:",
    "ui.theme",
    "ui.tabs",
    "ui.order",
]


def _node_available():
    try:
        subprocess.run(["node", "--version"], capture_output=True, timeout=10)
        return True
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


needs_node = pytest.mark.skipif(
    not _node_available(), reason="node not installed on this runner"
)


class TestSettingsFile:
    def test_settings_file_exists(self):
        assert SETTINGS.exists(), "config/settings.js is missing"

    def test_is_javascript_not_yaml(self):
        """A .js file must not carry a YAML header -- it would never load."""
        first = SETTINGS.read_text().splitlines()[0].strip()
        assert not first.startswith("#"), (
            f"config/settings.js starts with a YAML comment ({first!r}). "
            "Node-RED cannot load this: it must be JavaScript."
        )

    @needs_node
    def test_passes_node_syntax_check(self):
        """The real gate: the file must parse as JavaScript.

        This is what CI should rely on rather than substring greps -- it catches
        malformed keys, unbalanced braces and YAML-in-a-.js-file.
        """
        r = subprocess.run(["node", "--check", str(SETTINGS)],
                           capture_output=True, text=True)
        assert r.returncode == 0, f"node --check failed:\n{r.stderr}"

    @needs_node
    def test_module_loads_and_exports_object(self):
        r = subprocess.run(
            ["node", "-e",
             f"const s=require({json.dumps(str(SETTINGS))});"
             "if (typeof s !== 'object' || s === null) process.exit(3);"
             "console.log('OK')"],
            capture_output=True, text=True)
        assert r.returncode == 0, f"module did not load:\n{r.stderr}"


class TestNoFabricatedKeys:
    """Fail if a key that is not part of Node-RED's schema is present."""

    @pytest.mark.parametrize("needle", FABRICATED)
    def test_fabricated_key_absent(self, needle):
        content = SETTINGS.read_text()
        # Ignore matches inside comments -- the file documents these by name.
        code = "\n".join(
            line for line in content.splitlines()
            if not line.strip().startswith(("//", "*", "/*"))
        )
        assert needle not in code, (
            f"{needle!r} is not a Node-RED setting and must not appear in "
            "config/settings.js"
        )


class TestRealKeys:
    """Assert the keys that ARE real, at their documented names."""

    @needs_node
    def test_flow_file_singular(self):
        """`flowFile` (one file), never `flowFiles`."""
        r = subprocess.run(
            ["node", "-e",
             f"const s=require({json.dumps(str(SETTINGS))});"
             "console.log(typeof s.flowFile, s.flowFiles)"] + [] ,
            capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout.startswith("string"), "flowFile should be set"
        assert r.stdout.strip().endswith("undefined"), "flowFiles must not exist"

    @needs_node
    def test_ui_path_is_the_only_dashboard_setting(self):
        """The dashboard runtime setting is `ui.path`; anything else is editor-side."""
        r = subprocess.run(
            ["node", "-e",
             f"const s=require({json.dumps(str(SETTINGS))});"
             "console.log(JSON.stringify(Object.keys(s.ui||{})))"],
            capture_output=True, text=True)
        assert r.returncode == 0
        keys = json.loads(r.stdout)
        assert keys == ["path"], f"ui must only contain 'path', found {keys}"

    @needs_node
    def test_ui_port_is_numeric(self):
        r = subprocess.run(
            ["node", "-e",
             f"const s=require({json.dumps(str(SETTINGS))});"
             "console.log(typeof s.uiPort)"],
            capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout.strip() == "number", "uiPort must be a number"

    @needs_node
    def test_userdir_points_at_the_service_userdir(self):
        """Must match the systemd unit's userDir, or config silently does nothing."""
        r = subprocess.run(
            ["node", "-e",
             f"const s=require({json.dumps(str(SETTINGS))});"
             "console.log(s.userDir)"],
            capture_output=True, text=True)
        assert r.returncode == 0
        assert r.stdout.strip() == "/root/.node-red"
