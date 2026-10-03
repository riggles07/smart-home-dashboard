"""
Guard against env-template drift.

History: the repo carried TWO env templates. A root-level .env.example omitted 7
variables the flows actually read and defined 13 that nothing reads. It drifted
because nothing checked it against the code.

This test derives the authoritative variable list from the flows themselves --
every `env.get('NAME')` in every function node -- and asserts the single template
covers all of them. It cannot drift the way a hand-maintained list does, because
the expectation is generated from the artifact under test.

Card: t_1ed4992c.
"""
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FLOWS = ROOT / "flows" / "all-flows.flow.json"
TEMPLATE = ROOT / "deploy" / ".env.example"

ENV_GET = re.compile(r"env\.get\(\s*['\"]([A-Z][A-Z0-9_]*)['\"]")


def _flow_env_names():
    """Every env var name the deployed flows read, from the real func bodies."""
    nodes = json.loads(FLOWS.read_text())
    names = set()
    for n in nodes:
        if n.get("type") == "function":
            names.update(ENV_GET.findall(n.get("func", "")))
    return names


def _template_names():
    return set(re.findall(r"^\s*([A-Z][A-Z0-9_]*)=", TEMPLATE.read_text(), re.M))


class TestEnvTemplate:
    def test_template_exists(self):
        assert TEMPLATE.exists(), "deploy/.env.example is missing"

    def test_no_second_root_template(self):
        """Exactly one template. Two drifted apart silently before."""
        stray = ROOT / ".env.example"
        assert not stray.exists(), (
            "root .env.example reappeared. Keep a single template at "
            "deploy/.env.example or the two will drift."
        )

    def test_template_covers_every_variable_the_flows_read(self):
        """The template must be a superset of the flow's env reads."""
        needed = _flow_env_names()
        have = _template_names()
        missing = sorted(needed - have)
        assert not missing, (
            f"deploy/.env.example does not document {missing}, which the flows "
            f"read via env.get(). A missing name means a silent failure at "
            f"runtime (the flow's guard fires, or it falls back to a default)."
        )

    def test_flows_actually_read_env(self):
        """Sanity: if this fails, the extractor broke, not the template."""
        assert len(_flow_env_names()) >= 10, (
            "expected the flows to read at least 10 env vars; the extractor "
            "may have stopped matching -- fix the test before trusting it"
        )

    def test_template_does_not_document_unknown_variables(self):
        """Names in the template that NO flow reads are clutter that misleads.

        NODE_RED_* are allowed: they are consumed by settings.js / the service,
        not by flow function nodes.
        """
        allowed_non_flow = {
            "NODE_RED_USER", "NODE_RED_PASS", "NODE_RED_HOST", "NODE_RED_PORT",
            "NODE_RED_SECURE", "NODE_RED_LOG_LEVEL", "NODE_RED_USERDIR",
            "NODE_RED_CREDENTIAL_SECRET", "CONTAINER_ID", "CONTAINER_IP",
            "NODE_RED_KEY_PATH", "NODE_RED_CERT_PATH", "NODERED_USER",
            "NODERED_PASS",
        }
        unknown = sorted(_template_names() - _flow_env_names() - allowed_non_flow)
        assert not unknown, (
            f"deploy/.env.example documents {unknown}, which no flow reads. "
            f"Remove them (or add to allowed_non_flow with a reason)."
        )
