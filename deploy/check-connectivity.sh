#!/usr/bin/env bash
# Verify the Smart Home Dashboard flow credentials actually reach their services.
#
# Run this INSIDE the Node-RED LXC:
#   bash deploy/check-connectivity.sh
#
# It reads the same env vars the flow function nodes read, so a problem here is
# a problem the flows will hit. Nothing is printed except hostnames and HTTP
# status codes -- no secrets.
set -uo pipefail

echo "Smart Home Dashboard - connectivity check"
echo "date: $(date -Is)"
echo "node-red: $(systemctl is-active node-red 2>/dev/null || echo 'n/a')"

# --- are the env vars even loaded into the service? -------------------------
echo
echo "== service environment =="
if ! systemctl show node-red -p Environment --value 2>/dev/null | grep -q "="; then
    echo "  !! no Environment= lines on node-red.service"
fi
if command -v systemctl >/dev/null && systemctl show node-red -p EnvironmentFiles --value 2>/dev/null | grep -q ".env"; then
    echo "  EnvironmentFile is set"
else
    echo "  !! EnvironmentFile NOT set -- /home/node-red/.env is never read."
    echo "     Add to [Service]:  EnvironmentFile=/home/node-red/.env"
    echo "     then: systemctl daemon-reload && systemctl restart node-red"
fi

# --- Proxmox ----------------------------------------------------------------
echo
echo "== Proxmox =="
if [ -n "${PROXMOX_URL:-}" ]; then
    echo "  PROXMOX_URL=${PROXMOX_URL}"
    host=$(echo "$PROXMOX_URL" | sed -E 's#^[a-z]+://##; s#[:/].*$##')
    getent hosts "$host" >/dev/null 2>&1 && echo "  DNS: $host resolves" || echo "  !! DNS: $host does NOT resolve"
    code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
        -H "Authorization: PVEAPIToken=${PROXMOX_TOKEN:-}" \
        "${PROXMOX_URL}/api2/json/nodes/${PROXMOX_NODE:-pve}/status" 2>/dev/null)
    case "$code" in
        200) echo "  API: 200 OK (authenticated)" ;;
        401|403) echo "  !! API: $code -- token rejected (check PROXMOX_TOKEN)" ;;
        000) echo "  !! API: unreachable" ;;
        *) echo "  ?? API: HTTP $code" ;;
    esac
else
    echo "  - PROXMOX_URL unset (Home Lab tab will show ENOTFOUND)"
fi

# --- Hubitat ----------------------------------------------------------------
echo
echo "== Hubitat =="
if [ -n "${HUBITAT_URL:-}" ]; then
    echo "  HUBITAT_URL=${HUBITAT_URL}"
    host=$(echo "$HUBITAT_URL" | sed -E 's#^[a-z]+://##; s#[:/].*$##')
    getent hosts "$host" >/dev/null 2>&1 && echo "  DNS: $host resolves" || echo "  !! DNS: $host does NOT resolve"
    if [ -n "${HUBITAT_APP_ID:-}" ] && [ -n "${HUBITAT_ACCESS_TOKEN:-}" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
            "${HUBITAT_URL%/}/apps/api/${HUBITAT_APP_ID}/devices?access_token=${HUBITAT_ACCESS_TOKEN}" 2>/dev/null)
        case "$code" in
            200) echo "  Maker API: 200 OK" ;;
            401|403) echo "  !! Maker API: $code -- bad token/app id" ;;
            000) echo "  !! Maker API: unreachable" ;;
            *) echo "  ?? Maker API: HTTP $code" ;;
        esac
        [ -n "${HUBITAT_DEVICE_ID:-}" ] || echo "  !! HUBITAT_DEVICE_ID unset -- Devices tab cannot send commands"
    else
        echo "  - Maker API not configured (HUBITAT_APP_ID / HUBITAT_ACCESS_TOKEN unset)"
    fi
else
    echo "  - HUBITAT_URL unset"
fi

# --- UniFi ------------------------------------------------------------------
echo
echo "== UniFi =="
if [ -n "${UNIFI_URL:-}" ]; then
    echo "  UNIFI_URL=${UNIFI_URL}"
    host=$(echo "$UNIFI_URL" | sed -E 's#^[a-z]+://##; s#[:/].*$##')
    getent hosts "$host" >/dev/null 2>&1 && echo "  DNS: $host resolves" || echo "  !! DNS: $host does NOT resolve"
    if [ -n "${UNIFI_API_KEY:-}" ]; then
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
            -H "X-API-KEY: ${UNIFI_API_KEY}" \
            "${UNIFI_URL%/}/api/s/${UNIFI_SITE:-default}/stat/sta" 2>/dev/null)
        echo "  API key mode: HTTP $code"
    elif [ -n "${UNIFI_USERNAME:-}" ] && [ -n "${UNIFI_PASSWORD:-}" ]; then
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"${UNIFI_USERNAME}\",\"password\":\"${UNIFI_PASSWORD}\"}" \
            "${UNIFI_URL%/}/api/login" 2>/dev/null)
        echo "  Login mode: HTTP $code (200 = credentials accepted)"
    else
        echo "  - no UniFi credentials (set UNIFI_API_KEY or UNIFI_USERNAME/PASSWORD)"
    fi
else
    echo "  - UNIFI_URL unset"
fi

echo
echo "Done. Any '!!' line is a config item to fix in /home/node-red/.env"
