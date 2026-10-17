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

    def test_no_inline_comments_after_values(self):
        """An inline '#' is NOT stripped by systemd's EnvironmentFile parser.

        The value runs to end-of-line, so `HA_URL=http://x  # note` sets HA_URL
        to "http://x  # note". Most other readers (bash `source`, dotenv
        libraries, docker --env-file) DO strip it, so the mistake passes every
        local check and only breaks inside the running service.

        Measured 2026-10-17 on a real deployment:
            HA_URL        len=81 'http://homeassistant.tail5a1c91.ts.net     # port 80, ...'
            HA_ENTITY_ID  len=74 'light.kitchen                         # whichever ...'
        The Home Assistant WebSocket client then threw
            Invalid URL: ws://homeassistant.tail5a1c91.ts.net  # port 80.../api/websocket

        Quoted values are allowed to contain '#'; put comments on their own line.
        """
        bad = []
        for i, line in enumerate(TEMPLATE.read_text().splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, _, value = s.partition("=")
            if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", key.strip()):
                continue
            if "#" in value and not value.strip().startswith(('"', "'")):
                bad.append((i, s))
        assert not bad, (
            f"deploy/.env.example has an inline '#' after a value at {bad}. "
            "systemd's EnvironmentFile does NOT strip it -- the comment becomes "
            "part of the value. Put the comment on its own line."
        )


def test_no_redaction_placeholders_in_commands():
    """A redaction placeholder inside a runnable command gets PASTED literally.

    Measured 2026-10-17: a doc shipped `curl -i -H "Authorization: Bearer ***"`.
    It was copied verbatim, HA replied `401 Unauthorized` (body: the plain text
    "401: Unauthorized"), and the failure surfaced as a confusing
    `JSONDecodeError: Extra data: line 1 column 4 (char 3)` instead of anything
    mentioning auth. Use a shell variable (`$HA_TOKEN`) so the line is safe to
    paste -- the reader's own env supplies the secret.
    """
    banned = ("Bearer ***", "[REDACTED]", "Bearer <token>", "Bearer XXX")
    hits = []
    # Exclude THIS file. It has to name the banned strings in order to define
    # and explain them, and a hygiene check that matches its own source is
    # guaranteed to fail -- the same self-referential trap as a residue check
    # that flags the very script doing the checking.
    self_path = Path(__file__).resolve()
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        # Skip kanban worker worktrees. They are nested INSIDE the repo at
        # .worktrees/<card>/, so rglob walks them -- and each one is a full
        # checkout containing a COPY of this very file, plus the docs it scans.
        # Without this the guard trips on its own duplicates and fails in the MAIN
        # tree while passing inside a worktree (where nothing is nested beneath it).
        # That asymmetry is what blocked a verified commit from being pushed on
        # 2026-10-17: the gate passed in the worktree, then failed on main.
        # .worktrees/ is gitignored, but this guard walks the filesystem, not git.
        if ".worktrees" in path.parts:
            continue
        if path.resolve() == self_path:
            continue
        if path.suffix not in (".md", ".sh", ".js", ".py", ".example", ".json"):
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        if path.suffix == ".md":
            # Only fenced code blocks are pasteable. Prose may legitimately
            # DISCUSS the placeholder by name (this doc does), and flagging that
            # would make the guard unusable.
            scoped, in_fence = [], False
            for i, line in enumerate(text.splitlines(), 1):
                if line.lstrip().startswith("```"):
                    in_fence = not in_fence
                    continue
                if in_fence:
                    scoped.append((i, line))
        else:
            scoped = list(enumerate(text.splitlines(), 1))
        for i, line in scoped:
            for b in banned:
                if b in line:
                    hits.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()[:90]}")
    assert not hits, (
        "Redaction placeholder in a runnable command -- it will be pasted "
        f"literally. Use $VAR instead: {hits}"
    )
