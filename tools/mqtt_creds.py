"""MQTT login for the wall panel, read from the environment, never from source.

The broker at 100.104.204.118 answers on a Tailscale address and the panel login is a real
credential. It used to be typed into every probe script, which put it in git; these helpers
read MQTT_USER / MQTT_PASS instead -- from the process environment if set, otherwise from
/root/.hermes/.env, which is outside the repo.
"""
from __future__ import annotations

import os
import pathlib

ENV_FILE = pathlib.Path(os.environ.get("HERMES_ENV", "/root/.hermes/.env"))


def _from_env_file(key: str) -> str | None:
    try:
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        return None
    return None


def creds() -> tuple[str, str]:
    """(username, password) for the panel's MQTT login."""
    user = os.environ.get("MQTT_USER") or _from_env_file("MQTT_USER")
    password = os.environ.get("MQTT_PASS") or _from_env_file("MQTT_PASS")
    if not user or not password:
        raise SystemExit("MQTT_USER / MQTT_PASS not set and not found in " + str(ENV_FILE))
    return user, password
