#!/usr/bin/env bash
# Free port 1880 from an orphan Node-RED so the systemd unit can bind it.
#
# The observed failure:
#   systemd starts node-red -> palette loads, settings/flows resolve correctly
#   -> [error] Unable to listen on http://127.0.0.1:1880/  Error: port in use
#   -> Main process exited, code=exited, status=1/FAILURE
#
# Cause: an earlier hand-started Node-RED (not under systemd) is still holding
# 1880. That orphan is also why the running instance reports no HUBITAT_/UNIFI_/
# PROXMOX_ variables -- the process answering the API is the stale one, which was
# started before the env file existed. Killing it and letting systemd's instance
# take the port is what actually applies the EnvironmentFile.
#
# Run as root, ON the Node-RED LXC:   bash takeover-1880.sh
#
# Order matters: stop the unit FIRST (so it does not fight for the port), then
# kill strays, CONFIRM the port is free, then start the unit.
set -uo pipefail

UNIT=node-red
PORT=${NODE_RED_PORT:-1880}
USER_DIR=${NODE_RED_USERDIR:-/root/.node-red}

say() { printf '%s\n' "$*"; }
ok()  { printf '  OK   %s\n' "$*"; }
bad() { printf '  !!   %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { say "must run as root"; exit 1; }

# Is the TCP port BOUND? Not "does it answer HTTP" -- a wedged process can hold
# the port while never replying, and systemd would then fail to bind anyway.
port_bound() {
    (exec 3<>"/dev/tcp/127.0.0.1/$PORT") 2>/dev/null && { exec 3>&- 2>/dev/null || true; return 0; }
    return 1
}
# Does it also SPEAK HTTP? Only used for the final confirmation.
port_http() { curl -s -o /dev/null --max-time 3 "http://localhost:$PORT/settings"; }
list_procs() { pgrep -af 'node-red|red\.js' 2>/dev/null | grep -v "$0" || true; }

say "== 1. who holds :$PORT =="
if port_bound; then
    if port_http; then ok "something is serving HTTP on :$PORT"
    else bad ":$PORT is BOUND but not answering HTTP (wedged listener)"; fi
else
    say "  :$PORT is not bound"
fi
say "  node-red processes:"
list_procs | sed 's/^/    /' || say "    (none)"

say
say "== 2. stop the unit so it stops competing for the port =="
systemctl stop "$UNIT" 2>/dev/null && ok "unit stopped" || say "  (unit was not running)"

say
say "== 3. terminate stray node-red processes =="
strays=$(pgrep -f 'node-red|red\.js' 2>/dev/null | grep -v "^$$\$" || true)
if [ -n "$strays" ]; then
    say "  sending SIGTERM to: $(echo "$strays" | tr '\n' ' ')"
    # shellcheck disable=SC2086
    kill $strays 2>/dev/null || true
    for _ in 1 2 3 4 5; do
        sleep 1
        still=$(pgrep -f 'node-red|red\.js' 2>/dev/null | grep -v "^$$\$" || true)
        [ -z "$still" ] && break
    done
    still=$(pgrep -f 'node-red|red\.js' 2>/dev/null | grep -v "^$$\$" || true)
    if [ -n "$still" ]; then
        say "  still alive, sending SIGKILL to: $(echo "$still" | tr '\n' ' ')"
        # shellcheck disable=SC2086
        kill -9 $still 2>/dev/null || true
        sleep 1
    fi
else
    say "  none"
fi

say
say "== 4. confirm the port is actually free (must be free before starting) =="
free=0
for _ in 1 2 3 4 5; do
    if port_bound; then
        sleep 1
    else
        free=1; break
    fi
done
if [ "$free" = "1" ]; then
    ok ":$PORT is free"
else
    bad ":$PORT is STILL held. Something keeps restarting it. Check:"
    say  "       pgrep -af node-red"
    say  "       grep -rn node-red /etc/rc.local /etc/systemd/system 2>/dev/null"
    exit 1
fi

say
say "== 5. start via systemd =="
systemctl reset-failed "$UNIT" 2>/dev/null || true
systemctl start "$UNIT"
sleep 4

if systemctl is-active --quiet "$UNIT"; then
    ok "$UNIT is active"
else
    bad "$UNIT is not active (state: $(systemctl is-active "$UNIT" 2>/dev/null))"
    say  "     last log lines:"
    journalctl -u "$UNIT" -n 15 --no-pager 2>/dev/null | sed 's/^/       /'
    exit 1
fi

say
say "== 6. is it serving, and with which environment? =="
up=0
for _ in 1 2 3 4 5 6; do
    if port_http; then up=1; break; fi
    sleep 2
done
if [ "$up" = "1" ]; then
    ok ":$PORT responds"
else
    bad ":$PORT does not respond"
fi

pid=$(systemctl show "$UNIT" -p MainPID --value 2>/dev/null || echo "")
say "  unit MainPID: ${pid:-none}"
if [ -n "$pid" ] && [ "$pid" != "0" ] && [ -r "/proc/$pid/environ" ]; then
    n=$(tr '\0' '\n' < "/proc/$pid/environ" | grep -cE '^(HUBITAT|UNIFI|PROXMOX)_' 2>/dev/null || true)
    [ -z "$n" ] && n=0
    if [ "$n" -gt 0 ]; then
        ok "$n flow env var(s) visible to the process:"
        tr '\0' '\n' < "/proc/$pid/environ" | grep -E '^(HUBITAT|UNIFI|PROXMOX)_' \
            | cut -d= -f1 | sort | sed 's/^/       /'
    else
        bad "no HUBITAT_/UNIFI_/PROXMOX_ vars in pid $pid"
        say "     EnvironmentFile=-$USER_DIR/.env did not load. Check the drop-in:"
        say "       systemctl cat $UNIT | grep Environment"
    fi
else
    say "  ?? cannot read /proc/${pid:-?}/environ"
fi

say
say "== 7. flows still present? =="
if [ -f "$USER_DIR/flows.json" ]; then
    nf=$(grep -o '"type"' "$USER_DIR/flows.json" 2>/dev/null | wc -l)
    say "  $USER_DIR/flows.json: $nf node entries"
else
    bad "no flows.json in $USER_DIR"
fi

say
say "Done. From your dev machine:  python3 tools/probe_runtime_env.py http://sh-dashboard:$PORT"
