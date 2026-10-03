"""
Guard against invented Proxmox commands in docs and scripts.

History: a session "fixed" deployment docs by replacing `qm` with `ct` in 6 files
(~55 occurrences). `ct` is not a Proxmox command -- it was never real. The result
was docs that told users to run something that does not exist, and the bad rule
propagated into three skills and persistent memory before being caught.

The correct split:
    qm  -> QEMU/KVM virtual machines
    pct -> LXC containers
    (no such command: 'ct'; no such subcommands: 'pct terminal', 'pct delete')
"""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Files scanned: markdown docs and shell scripts (where commands are published).
SCANNED = [
    p for pat in ("*.md", "**/*.md", "*.sh", "**/*.sh")
    for p in ROOT.glob(pat)
    if ".git" not in p.parts and "node_modules" not in p.parts
]

# `ct <verb>` -- 'ct' is not a command at all.
INVENTED_CT = re.compile(
    r"(?:^|[^A-Za-z_/.-])ct\s+"
    r"(?:create|start|stop|set|list|status|enter|exec|terminal|delete|destroy|"
    r"snapshot|rollback|config|clone)\b"
)

# `pct <sub>` where <sub> is not a real pct subcommand.
INVENTED_PCT = re.compile(r"\bpct\s+(?:terminal|delete|ip-config)\b")

# Container operations invoked via the VM tool.
QM_CONTAINER = re.compile(
    r"(?:^|[^A-Za-z_/.-])qm\s+"
    r"(?:create|start|stop|set|list|status|terminal|enter|snapshot|firewall|export)\b"
)


def _scan(pattern):
    hits = []
    for p in SCANNED:
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith(("#!", "# `", "//")):
                continue  # shebangs / doc comments
            if pattern.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()[:100]}")
    return hits


class TestNoInventedProxmoxCommands:
    def test_files_were_found(self):
        assert len(SCANNED) >= 10, "scan found suspiciously few files"

    def test_no_ct_command(self):
        """`ct` is not a Proxmox command. Its presence is always a bug."""
        hits = _scan(INVENTED_CT)
        assert not hits, (
            "'ct <verb>' is not a Proxmox command. Use `pct` for containers and "
            "`qm` for VMs.\n" + "\n".join(hits)
        )

    def test_no_invented_pct_subcommands(self):
        """`pct terminal` / `pct delete` do not exist."""
        hits = _scan(INVENTED_PCT)
        assert not hits, (
            "Not real pct subcommands (use `pct enter`, `pct exec`, `pct destroy`):\n"
            + "\n".join(hits)
        )

    def test_no_container_ops_on_qm(self):
        """Container operations must use pct, not qm."""
        hits = _scan(QM_CONTAINER)
        assert not hits, (
            "`qm` is the QEMU/KVM VM tool; containers use `pct`:\n" + "\n".join(hits)
        )
