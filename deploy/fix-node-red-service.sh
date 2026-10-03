#!/usr/bin/env bash
# Diagnose and fix node-red.service failing to start.
#
# Written for the observed failure:
#   node-red.service: Failed to determine user credentials: No such process
#   node-red.service: Failed at step USER spawning /usr/bin/node-red
#   Main process exited, code=exited, status=217/USER
#
# status=217/USER means systemd could not resolve the unit's User= account:
# that user does not exist on this container. systemd fails BEFORE running
# Node-RED, so settings.js/env/flows are not even reached.
#
# Run as root, ON the Node-RED LXC:   bash fix-node-red-service.sh
#
# Idempotent. Applies the minimal fix for whatever it actually finds, validating
# settings.js first so the service does not immediately re-enter the crash loop.
set -uo pipefail

UNIT=node-red
USER_DIR=${NODE_RED_USERDIR:-/root/.node-red}
ENV_FILE=${NODE_RED_ENV_FILE:-$USER_DIR/.env}
DROPIN_DIR=/etc/systemd/system/node-red.service.d
DROPIN=$DROPIN_DIR/10-fix-runtime.conf

say()  { printf '%s\n' "$*"; }
ok()   { printf '  OK   %s\n' "$*"; }
bad()  { printf '  !!   %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { say "must run as root"; exit 1; }

say "== 1. does the unit exist? =="
if ! systemctl cat "$UNIT" >/dev/null 2>&1; then
    bad "no $UNIT unit in this container"
    say "     If Node-RED runs as the container command instead, a unit is not the fix."
    exit 1
fi
ok "unit found"

say
say "== 2. which user does it ask for? =="
unit_user=$(systemctl cat "$UNIT" 2>/dev/null | sed -n 's/^[[:space:]]*User=//p' | tail -1)
unit_group=$(systemctl cat "$UNIT" 2>/dev/null | sed -n 's/^[[:space:]]*Group=//p' | tail -1)
unit_wd=$(systemctl cat "$UNIT" 2>/dev/null | sed -n 's/^[[:space:]]*WorkingDirectory=//p' | tail -1)
say "  User=            ${unit_user:-<unset, means root>}"
say "  Group=           ${unit_group:-<unset>}"
say "  WorkingDirectory=${unit_wd:-<unset>}"

USER_MISSING=0
if [ -n "$unit_user" ] && ! id "$unit_user" >/dev/null 2>&1; then
    bad "user '$unit_user' does NOT exist on this container  <-- status=217/USER"
    USER_MISSING=1
else
    ok "user resolves${unit_user:+ ($unit_user)}"
fi

say
say "== 3. recent failure from the journal =="
journalctl -u "$UNIT" -n 12 --no-pager 2>/dev/null | sed 's/^/  /' || say "  (no journal access)"

say
say "== 4. where is the data actually? =="
say "  userDir (assumed): $USER_DIR"
[ -d "$USER_DIR" ] && ok "exists" || bad "missing"
[ -f "$ENV_FILE" ] && ok "env file: $ENV_FILE" || bad "no env file at $ENV_FILE"
if [ -f "$USER_DIR/.env" ]; then
    n=$(grep -cE '^(HUBITAT|UNIFI|PROXMOX)_' "$USER_DIR/.env" 2>/dev/null || echo 0)
    say "  flow env vars defined in file: $n"
fi

say
say "== 5. validate settings.js BEFORE restarting =="
# A bad settings.js re-enters the crash loop, so refuse to proceed until it loads.
SETTINGS=$USER_DIR/settings.js
SETTINGS_OK=1
if [ -f "$SETTINGS" ]; then
    if node --check "$SETTINGS" >/dev/null 2>&1; then
        ok "settings.js parses"
    else
        bad "settings.js has a SYNTAX ERROR -- fix this first:"
        node --check "$SETTINGS" 2>&1 | sed 's/^/       /'
        SETTINGS_OK=0
    fi
    if node -e "require('$SETTINGS')" >/dev/null 2>&1; then
        ok "settings.js loads"
    else
        bad "settings.js throws when loaded:"
        node -e "require('$SETTINGS')" 2>&1 | head -6 | sed 's/^/       /'
        SETTINGS_OK=0
    fi
else
    bad "no settings.js at $SETTINGS (Node-RED will use defaults)"
fi

if [ "$SETTINGS_OK" -eq 0 ]; then
    say
    say "Fix settings.js, then re-run this script."
    exit 2
fi

say
say "== 6. decide the fix =="
FIX_GROUP=root
if [ "$USER_MISSING" -eq 1 ]; then
    say "  User='$unit_user' does not exist; running the service as root instead."
    say "  Rationale: the data lives in $USER_DIR (root-owned, mode 600 .env),"
    say "  so a non-root user could neither read the env file nor write the flows."
    FIX_USER=root
else
    say "  User='$unit_user' resolves; keeping it."
    FIX_USER=$unit_user
fi
# Group= is resolved by systemd independently of User=; a dangling Group=
# fails with 217/GROUP even when User= is fine. Validate it too.
if [ -n "$unit_group" ] && ! getent group "$unit_group" >/dev/null 2>&1; then
    say "  Group='$unit_group' does not exist either -- pinning Group=root."
    FIX_GROUP=root
elif [ -n "$unit_group" ]; then
    FIX_GROUP=$unit_group
fi
say "  -> will run as User=$FIX_USER Group=$FIX_GROUP"

say
say "== 7. install drop-in $DROPIN =="
mkdir -p "$DROPIN_DIR"
cat > "$DROPIN" <<EOF
# Written by fix-node-red-service.sh.
#
# Causes addressed:
#  - status=217/USER: User=/Group= named an account that does not exist.
#    BOTH must be fixed -- systemd resolves Group= too, so setting only User=
#    still fails (217/GROUP).
#  - WorkingDirectory=/home/node-red did not exist; the data lives in
#    $USER_DIR.
#  - ProtectSystem=strict makes / read-only outside ReadWritePaths, so the data
#    dir must be listed or Node-RED cannot write flows/credentials.
#  - MemoryDenyWriteExecute=true breaks V8's JIT. Node.js needs writable AND
#    executable pages; with this on, node-red aborts or runs crippled.
#  - EnvironmentFile loads the flow credentials/endpoints for the tabs. The
#    leading '-' keeps a missing file from being fatal.
[Service]
User=$FIX_USER
Group=$FIX_GROUP
WorkingDirectory=$USER_DIR
ReadWritePaths=
ReadWritePaths=$USER_DIR
MemoryDenyWriteExecute=false
EnvironmentFile=-$ENV_FILE
EOF
sed 's/^/  /' "$DROPIN"

say
say "== 8. reload, clear the crash loop, start =="
systemctl daemon-reload
systemctl reset-failed "$UNIT" 2>/dev/null || true
systemctl restart "$UNIT" 2>/dev/null || true
sleep 3

if systemctl is-active --quiet "$UNIT"; then
    ok "$UNIT is active"
else
    bad "$UNIT is still not active (state: $(systemctl is-active "$UNIT" 2>/dev/null))"
    say  "     last log lines:"
    journalctl -u "$UNIT" -n 15 --no-pager 2>/dev/null | sed 's/^/       /'
    exit 1
fi

say
say "== 9. is it serving, and can it see the flow vars? =="
if curl -s -o /dev/null --max-time 6 http://localhost:1880/settings; then
    ok ":1880 responds"
else
    bad ":1880 does not respond yet (give it a few seconds)"
fi

pid=$(systemctl show "$UNIT" -p MainPID --value 2>/dev/null || echo "")
if [ -n "$pid" ] && [ "$pid" != "0" ] && [ -r "/proc/$pid/environ" ]; then
    if tr '\0' '\n' < "/proc/$pid/environ" | grep -qE '^(HUBITAT|UNIFI|PROXMOX)_'; then
        ok "flow env vars ARE visible to the process:"
        tr '\0' '\n' < "/proc/$pid/environ" | grep -E '^(HUBITAT|UNIFI|PROXMOX)_' \
            | cut -d= -f1 | sort | sed 's/^/       /'
    else
        bad "no HUBITAT_/UNIFI_/PROXMOX_ vars in pid $pid"
        say "     Check that $ENV_FILE exists and is listed in $DROPIN"
    fi
else
    say "  ?? cannot read /proc/${pid:-?}/environ"
fi

say
say "Done. For a full per-service probe:  bash check-connectivity.sh"
