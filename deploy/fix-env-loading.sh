#!/usr/bin/env bash
# Make node-red.service actually load /home/node-red/.env.
#
# Symptom this fixes:
#   systemctl show node-red -p Environment --value | tr ' ' '\n' | grep -E 'HUBITAT|UNIFI'
#   -> (no output)
# i.e. the vars are silently absent, so flow function nodes fall back to their
# hardcoded defaults (proxmox.local / hubitat.local / unifi.local) and every
# request fails with ENOTFOUND no matter what is in .env.
#
# Run as root, ON the Node-RED LXC:   sudo bash deploy/fix-env-loading.sh
#
# Idempotent: safe to re-run. Uses a systemd drop-in rather than editing the
# unit file, so a later `setup.sh` regeneration won't clobber it.
set -euo pipefail

ENV_FILE=/home/node-red/.env
DROPIN_DIR=/etc/systemd/system/node-red.service.d
DROPIN=${DROPIN_DIR}/10-env-file.conf
UNIT=node-red

if [ "$(id -u)" -ne 0 ]; then
    echo "must run as root (try: sudo bash $0)" >&2
    exit 1
fi

echo "== 1. does the unit reference the env file today? =="
if systemctl cat "$UNIT" 2>/dev/null | grep -q "^EnvironmentFile="; then
    echo "   EnvironmentFile= already present:"
    systemctl cat "$UNIT" | grep "^EnvironmentFile="
else
    echo "   no EnvironmentFile= -- installing a drop-in"
fi

echo
echo "== 2. checking $ENV_FILE =="
if [ ! -f "$ENV_FILE" ]; then
    echo "   !! $ENV_FILE does not exist. Create it first (see deploy/.env.example)." >&2
    exit 1
fi
# A missing file makes systemd refuse to start the unit; a CRLF or a value with
# unquoted spaces silently mangles the environment.
if grep -q $'\r' "$ENV_FILE"; then
    echo "   !! $ENV_FILE contains CRLF line endings -- strip them:"
    echo "      sed -i 's/\r$//' $ENV_FILE"
fi
if grep -nE '^[A-Za-z_][A-Za-z0-9_]*=[^"'"'"']*[[:space:]]+[^"'"'"'#]' "$ENV_FILE" >/dev/null 2>&1; then
    echo "   !! unquoted value containing spaces in $ENV_FILE (systemd splits on"
    echo "      whitespace; quote the whole value)"
fi
echo "   variables defined:"
grep -oE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=' "$ENV_FILE" \
    | tr -d ' =' | sort | sed 's/^/     /'

echo
echo "== 3. installing drop-in $DROPIN =="
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN" <<'EOF'
# Added by deploy/fix-env-loading.sh -- loads flow credentials/endpoints for
# the Home Lab, Devices and Network tabs. systemd does not expand variables in
# this file and a missing file makes the unit fail to start.
[Service]
EnvironmentFile=/home/node-red/.env
EOF
echo "   written:"
sed 's/^/     /' "$DROPIN"

echo
echo "== 4. reloading + restarting =="
systemctl daemon-reload
systemctl restart "$UNIT"
sleep 2
systemctl is-active --quiet "$UNIT" \
    && echo "   $UNIT is active" \
    || { echo "   !! $UNIT failed to start -- check: journalctl -u $UNIT -n 30" >&2; exit 1; }

echo
echo "== 5. verifying against the RUNNING process =="
# /proc/<pid>/environ is ground truth. `systemctl show -p Environment` is not
# always populated for values sourced from EnvironmentFile, so never conclude
# success or failure from it alone.
pid=$(systemctl show "$UNIT" -p MainPID --value)
echo "   MainPID: ${pid:-none}"
if [ -n "${pid:-}" ] && [ "$pid" != "0" ] && [ -r "/proc/$pid/environ" ]; then
    if tr '\0' '\n' < "/proc/$pid/environ" | grep -qE '^(HUBITAT|UNIFI|PROXMOX)_'; then
        echo "   OK - flow env vars are in the process environment:"
        tr '\0' '\n' < "/proc/$pid/environ" \
            | grep -E '^(HUBITAT|UNIFI|PROXMOX)_' \
            | sed -E 's/=(.*)$/=<set>/' | sed 's/^/     /'
    else
        echo "   !! no HUBITAT_/UNIFI_/PROXMOX_ vars in /proc/$pid/environ" >&2
        echo "      The drop-in is installed but the file's contents are not" >&2
        echo "      reaching the process -- check the file and journalctl." >&2
        exit 1
    fi
else
    echo "   !! cannot read /proc/$pid/environ (need root, or pid is unknown)" >&2
    exit 1
fi

echo
echo "Done. Now run:  bash deploy/check-connectivity.sh"
