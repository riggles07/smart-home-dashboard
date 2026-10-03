#!/bin/sh
# Hardened Node-RED launcher: loads /root/.node-red/.env and starts Node-RED.
#
# Use this as the container's start command (or run it to bring Node-RED up).
#
# Why not `set -a; . .env`?  Dot-sourcing the env file is what takes the whole
# service down: a single unmatched quote, a stray backtick, or a CRLF line makes
# a non-interactive shell ABORT while sourcing, so `exec node-red` is never
# reached and the container exits. This script instead PARSES the file line by
# line and exports each pair explicitly, so no malformed line can prevent
# Node-RED from starting. Bad lines are logged and skipped.

ENV_FILE="${NODE_RED_ENV_FILE:-/root/.node-red/.env}"
USER_DIR="${NODE_RED_USERDIR:-/root/.node-red}"
LOG="${NODE_RED_START_LOG:-$USER_DIR/start.log}"

log() { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG" 2>/dev/null; }

mkdir -p "$USER_DIR" 2>/dev/null

{
    echo "=== $(date -Is) launching node-red ==="
    echo "env file : $ENV_FILE"
    echo "user dir : $USER_DIR"
} >> "$LOG" 2>/dev/null

# --- load environment, tolerating every malformed line --------------------
loaded=0
skipped=0
if [ -f "$ENV_FILE" ]; then
    while IFS= read -r line || [ -n "$line" ]; do
        # strip CR (Windows line endings)
        line=$(printf '%s' "$line" | tr -d '\r')
        # skip blanks and comments
        case "$line" in ''|'#'*) continue ;; esac
        # tolerate an `export ` prefix, which shell users expect to work
        case "$line" in 'export '*) line=${line#export } ;; esac
        # trim surrounding whitespace
        line=$(printf '%s' "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')
        # must look like NAME=...
        key=${line%%=*}
        val=${line#*=}
        # a line with no '=' at all is not a pair
        case "$line" in *=*) : ;; *) skipped=$((skipped+1)); log "skip line without '='"; continue ;; esac
        # reject keys that are not valid identifiers
        case "$key" in
            *[!A-Za-z0-9_]*|'') skipped=$((skipped+1)); log "skip malformed key"; continue ;;
        esac
        # strip one layer of matching quotes
        case "$val" in
            \"*\") val=$(printf '%s' "$val" | sed 's/^"//; s/"$//') ;;
            \'*\') val=$(printf '%s' "$val" | sed "s/^'//; s/'\$//") ;;
        esac
        export "$key=$val"
        loaded=$((loaded+1))
    done < "$ENV_FILE"
    log "env: $loaded variable(s) loaded, $skipped line(s) skipped"
else
    log "WARN: $ENV_FILE not found -- starting without it"
fi

# --- resolve the node-red binary -------------------------------------------
NODE_RED_BIN=$(command -v node-red 2>/dev/null || true)
if [ -z "$NODE_RED_BIN" ]; then
    for c in /usr/bin/node-red /usr/local/bin/node-red /usr/lib/node_modules/node-red/red.js; do
        [ -x "$c" ] && { NODE_RED_BIN="$c"; break; }
    done
fi

if [ -z "$NODE_RED_BIN" ]; then
    log "FATAL: node-red executable not found (looked at PATH, /usr/bin, /usr/local/bin)"
    echo "node-red not found; see $LOG" >&2
    exit 127
fi
log "binary: $NODE_RED_BIN"

# --- report what the flows will see (names only, never values) ------------
visible=$(env | grep -cE '^(HUBITAT|UNIFI|PROXMOX)_' 2>/dev/null || true)
[ -z "$visible" ] && visible=0
log "flow env vars visible: $visible"
log "  $(env | grep -E '^(HUBITAT|UNIFI|PROXMOX)_' | cut -d= -f1 | sort | tr '\n' ' ')"

exec "$NODE_RED_BIN" --userDir "$USER_DIR"
