#!/bin/bash
# rotate-credentials.sh - Credential Rotation for Smart Home Dashboard
#
# Rotates:
#   1. Node-RED admin password (bcrypt-hashed into settings)
#   2. SSL certificate (if older than ROTATE_CERT_DAYS or --cert flag)
#   3. API tokens in .env (placeholders - requires manual re-entry of
#      Hubitat/UniFi credentials from their admin consoles)
#
# Usage:
#   ./rotate-credentials.sh              # rotate passwords + refresh .env tokens
#   ./rotate-credentials.sh --cert       # also regenerate self-signed SSL cert
#   ./rotate-credentials.sh --dry-run    # show what would happen, no changes
#
# Exit codes:
#   0 success, 1 missing dependency, 2 backup failure

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ENV_FILE:-${SCRIPT_DIR}/../.env}"
BACKUP_DIR="${SCRIPT_DIR}/../backups"
ROTATE_CERT_DAYS="${ROTATE_CERT_DAYS:-30}"

DRY_RUN=false
ROTATE_CERT=false
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --cert)    ROTATE_CERT=true ;;
    esac
done

log()     { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"; }
success() { log "SUCCESS: $1"; }
warn()    { log "WARN: $1"; }
error()   { log "ERROR: $1"; exit 1; }

# --- 1. Node-RED admin password rotation -------------------------------
rotate_node_red_password() {
    log "Rotating Node-RED admin password..."

    # Generate a random 24-char password
    NEW_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
    [ -n "$NEW_PASS" ] || error "Password generation failed"

    if command -v node >/dev/null; then
        # bcrypt hash via Node (matches Node-RED adminAuth format)
        HASH="$(node -e "
            const crypto = require('crypto');
            const bcrypt = require('bcryptjs');
            console.log(bcrypt.hashSync(process.argv[1], 10));
        " "$NEW_PASS" 2>/dev/null)" || HASH=""
        if [ -z "$HASH" ]; then
            warn "bcryptjs unavailable - storing plaintext in .env (change manually!)"
            HASH_VALUE="$NEW_PASS"
        else
            HASH_VALUE="$HASH"
        fi
    else
        warn "Node.js not found - storing plaintext in .env (change manually!)"
        HASH_VALUE="$NEW_PASS"
    fi

    if [ "$DRY_RUN" = true ]; then
        log "[dry-run] Would update NODE_RED_PASS in ${ENV_FILE}"
        return
    fi

    # Backup .env before modification
    if [ -f "$ENV_FILE" ]; then
        mkdir -p "$BACKUP_DIR"
        cp "$ENV_FILE" "${ENV_FILE}.backup.$(date +%Y%m%d_%H%M%S)" \
            || error "Failed to backup ${ENV_FILE}"
    fi

    # Update .env
    if [ -f "$ENV_FILE" ] && grep -q "^NODE_RED_PASS=" "$ENV_FILE"; then
        sed -i "s|^NODE_RED_PASS=.*|NODE_RED_PASS=${HASH_VALUE}|" "$ENV_FILE"
    else
        echo "NODE_RED_PASS=${HASH_VALUE}" >> "$ENV_FILE"
    fi
    chmod 600 "$ENV_FILE"

    success "Node-RED admin password rotated (stored in ${ENV_FILE})"
    log "New plaintext password (shown once, save it now): ${NEW_PASS}"
}

# --- 2. SSL certificate rotation ---------------------------------------
rotate_ssl_cert() {
    log "Rotating SSL certificate..."

    local cert_path="/etc/node-red/fullchain.pem"
    local key_path="/etc/node-red/private.key"
    local need_rotate=true

    # Check cert age if it exists
    if [ -f "$cert_path" ] && command -v openssl >/dev/null; then
        END_DATE="$(openssl x509 -enddate -noout -in "$cert_path" 2>/dev/null | cut -d= -f2 || true)"
        if [ -n "$END_DATE" ]; then
            END_EPOCH="$(date -d "$END_DATE" +%s 2>/dev/null || echo 0)"
            NOW_EPOCH="$(date +%s)"
            AGE_DAYS=$(( (END_EPOCH - NOW_EPOCH) / 86400 ))
            if [ "$AGE_DAYS" -gt "$ROTATE_CERT_DAYS" ]; then
                log "Cert valid for ${AGE_DAYS} more days (> ${ROTATE_CERT_DAYS}) - no rotation needed"
                need_rotate=false
            fi
        fi
    fi

    if [ "$need_rotate" = false ] && [ "$ROTATE_CERT" = false ]; then
        return
    fi

    if [ "$DRY_RUN" = true ]; then
        log "[dry-run] Would regenerate self-signed cert at ${cert_path}"
        return
    fi

    if [ "$(id -u)" -ne 0 ]; then
        warn "Not root - cannot write /etc/node-red. Run with sudo for cert rotation."
        return
    fi

    mkdir -p /etc/node-red
    # Backup old cert
    if [ -f "$cert_path" ]; then
        mkdir -p "$BACKUP_DIR"
        cp "$cert_path" "${BACKUP_DIR}/fullchain.pem.$(date +%Y%m%d_%H%M%S).bak" || true
        cp "$key_path" "${BACKUP_DIR}/private.key.$(date +%Y%m%d_%H%M%S).bak" || true
    fi

    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
        -keyout "$key_path" \
        -out "$cert_path" \
        -subj "/CN=smarthome-dashboard" \
        || error "SSL certificate generation failed"

    chmod 600 "$key_path"
    chmod 644 "$cert_path"

    success "SSL certificate rotated (${cert_path})"
}

# --- 3. Environment token placeholders ----------------------------------
rotate_env_tokens() {
    log "Rotating .env API token placeholders..."

    if [ ! -f "$ENV_FILE" ]; then
        warn "${ENV_FILE} not found - skipping token rotation"
        return
    fi

    if [ "$DRY_RUN" = true ]; then
        log "[dry-run] Would flag HUBITAT_API_KEY / UNIFI credentials for manual rotation"
        return
    fi

    # These require re-issuing tokens in Hubitat/UniFi admin consoles.
    # We replace values with rotation markers so stale creds never linger.
    # (No spaces in values so the file remains safe to `source`.)
    sed -i \
        -e "s|^HUBITAT_API_KEY=.*|HUBITAT_API_KEY=ROTATED_$(date +%Y%m%d)_REISSUE_IN_HUBITAT_MAKER_API|" \
        -e "s|^HUBITAT_ACCESS_TOKEN=.*|HUBITAT_ACCESS_TOKEN=ROTATED_$(date +%Y%m%d)_REISSUE_IN_HUBITAT_MAKER_API|" \
        -e "s|^UNIFI_PASSWORD=.*|UNIFI_PASSWORD=ROTATED_$(date +%Y%m%d)_RESET_IN_UNIFI_CONTROLLER|" \
        "$ENV_FILE"
    chmod 600 "$ENV_FILE"

    success ".env token placeholders rotated - re-enter fresh credentials"
    warn "Hubitat Maker API token and UniFi password MUST be re-issued from their admin consoles"
}

# --- Main ---------------------------------------------------------------
main() {
    log "=== Credential Rotation - Smart Home Dashboard ==="

    command -v openssl >/dev/null \
        || error "openssl required but not found"

    rotate_node_red_password
    rotate_ssl_cert
    rotate_env_tokens

    log ""
    log "=== Rotation Summary ==="
    log "Node-RED password: rotated"
    log "SSL certificate: $([ "$ROTATE_CERT" = true ] && echo 'forced rotation' || echo "rotated if older than ${ROTATE_CERT_DAYS} days")"
    log "API tokens: flagged for manual re-issue (Hubitat/UniFi consoles)"
    log ""
    log "Post-rotation steps:"
    log "  1. Update Hubitat Maker API access token in Hubitat admin"
    log "  2. Reset UniFi controller password and update .env"
    log "  3. Restart Node-RED: systemctl restart node-red"
    log "  4. Verify HTTPS access: https://<host>:1881"

    success "Credential rotation complete"
}

main "$@"