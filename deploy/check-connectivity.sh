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

# Resolve a host to an IP, but skip DNS for literals -- getent hosts fails on a
# bare IP under some nsswitch configurations, which would be a false alarm.
check_dns() {
    local h="$1"
    if [[ "$h" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || [[ "$h" == *:* ]]; then
        echo "  DNS: $h is an IP literal (no lookup needed)"
        return 0
    fi
    if getent hosts "$h" >/dev/null 2>&1; then
        echo "  DNS: $h resolves"
    else
        echo "  !! DNS: $h does NOT resolve (add it to DNS or use an IP)"
    fi
}

# Strip scheme and any path/port suffix -> bare host
host_of() { echo "$1" | sed -E 's#^[a-z]+://##; s#[/:].*$##'; }
# scheme://authority (drops any path prefix) -> for probing the console root
root_of() { echo "$1" | sed -E 's#^([a-z]+://[^/]+).*$#\1#'; }

# --- are the env vars even loaded into the service? -------------------------
echo
echo "== service environment =="
# /proc/<pid>/environ is the only ground truth: `systemctl show -p Environment`
# is NOT reliably populated for values that came from EnvironmentFile, so it can
# report "empty" on a perfectly working setup (and vice versa).
svc_pid=$(systemctl show node-red -p MainPID --value 2>/dev/null || echo "")
if [ -n "$svc_pid" ] && [ "$svc_pid" != "0" ] && [ -r "/proc/$svc_pid/environ" ]; then
    if tr '\0' '\n' < "/proc/$svc_pid/environ" | grep -qE '^(HUBITAT|UNIFI|PROXMOX)_'; then
        echo "  env vars ARE loaded into node-red (pid $svc_pid):"
        tr '\0' '\n' < "/proc/$svc_pid/environ" \
            | grep -E '^(HUBITAT|UNIFI|PROXMOX)_' \
            | sed -E 's/=(.*)$/=<set>/' | sed 's/^/    /'
    else
        echo "  !! env vars NOT in the running process (pid $svc_pid)."
        echo "     No EnvironmentFile= is being read. Fix with:"
        echo "       sudo bash deploy/fix-env-loading.sh"
    fi
else
    echo "  ?? cannot read /proc/$svc_pid/environ (not root, or service down)"
fi
if command -v systemctl >/dev/null 2>&1; then
    systemctl cat node-red 2>/dev/null | grep -q "^EnvironmentFile=" \
        && echo "  unit: EnvironmentFile= present" \
        || echo "  unit: no EnvironmentFile= directive"
fi

# --- Proxmox ----------------------------------------------------------------
echo
echo "== Proxmox =="
if [ -n "${PROXMOX_URL:-}" ]; then
    echo "  PROXMOX_URL=${PROXMOX_URL}"
    check_dns "$(host_of "$PROXMOX_URL")"
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
    check_dns "$(host_of "$HUBITAT_URL")"
    if [ -n "${HUBITAT_APP_ID:-}" ] && [ -n "${HUBITAT_ACCESS_TOKEN:-}" ]; then
        code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
            "${HUBITAT_URL%/}/apps/api/${HUBITAT_APP_ID}/devices?access_token=${HUBITAT_ACCESS_TOKEN}" 2>/dev/null)
        case "$code" in
            200) echo "  Maker API: 200 OK" ;;
            401|403) echo "  !! Maker API: $code -- bad token/app id" ;;
            000) echo "  !! Maker API: unreachable" ;;
            *) echo "  ?? Maker API: HTTP $code" ;;
        esac
        if [ -n "${HUBITAT_DEVICE_ID:-}" ]; then
            dcode=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
                "${HUBITAT_URL%/}/apps/api/${HUBITAT_APP_ID}/devices/${HUBITAT_DEVICE_ID}?access_token=${HUBITAT_ACCESS_TOKEN}" 2>/dev/null)
            case "$dcode" in
                200) echo "  device ${HUBITAT_DEVICE_ID}: 200 OK (exists in this Maker API app)" ;;
                404) echo "  !! device ${HUBITAT_DEVICE_ID}: 404 -- not exposed by app ${HUBITAT_APP_ID}" ;;
                *) echo "  ?? device ${HUBITAT_DEVICE_ID}: HTTP $dcode" ;;
            esac
        else
            echo "  !! HUBITAT_DEVICE_ID unset -- Devices tab cannot send commands"
        fi
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
    check_dns "$(host_of "$UNIFI_URL")"

    # Detect controller type from the CONSOLE ROOT, not UNIFI_URL -- UNIFI_URL
    # may already carry the /proxy/network prefix, which has no title.
    root=$(root_of "$UNIFI_URL")
    title=$(curl -sk --max-time 6 "${root}/" 2>/dev/null | grep -oiE "<title>[^<]*</title>" | head -1)
    case "$title" in
        *"UniFi OS"*)
            echo "  controller: UniFi OS (console root: ${root})"
            case "$UNIFI_URL" in
                */proxy/network*) echo "  prefix: /proxy/network present -- correct for UniFi OS" ;;
                *) echo "  !! prefix: UNIFI_URL lacks /proxy/network. UniFi OS serves the" \
                          "Network app there; set UNIFI_URL=${root}/proxy/network" ;;
            esac
            ;;
        "") echo "  controller: $root returned no title (self-hosted controller?)" ;;
        *) echo "  controller title at ${root}: ${title}" ;;
    esac

    # Show which prefix actually answers. A 401 means the path reached the auth
    # gate (path likely valid); 404 means wrong prefix. NOTE: UniFi OS returns
    # 401 for EVERY /api/* path, including bogus ones, so a 401 does not by
    # itself prove the path is right -- only a 404 proves it is wrong.
    for prefix in "" "/proxy/network"; do
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 6 \
            "${UNIFI_URL%/}${prefix}/api/s/${UNIFI_SITE:-default}/stat/sta" 2>/dev/null)
        case "$code" in
            200) echo "  ${prefix}/api/s/... -> 200 OK (this prefix works)" ;;
            401) echo "  ${prefix}/api/s/... -> 401 (auth gate; prefix plausible)" ;;
            404) echo "  ${prefix}/api/s/... -> 404 (wrong prefix -- UNIFI_URL needs ${prefix#/})" ;;
            000) echo "  ${prefix}/api/s/... -> unreachable" ;;
            *) echo "  ${prefix}/api/s/... -> HTTP $code" ;;
        esac
    done

    if [ -n "${UNIFI_API_KEY:-}" ]; then
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
            -H "X-API-KEY: ${UNIFI_API_KEY}" \
            "${UNIFI_URL%/}/api/s/${UNIFI_SITE:-default}/stat/sta" 2>/dev/null)
        case "$code" in
            200) echo "  API key: 200 OK (authenticated)" ;;
            401|403) echo "  !! API key: $code -- key rejected" ;;
            *) echo "  ?? API key: HTTP $code" ;;
        esac
    elif [ -n "${UNIFI_USERNAME:-}" ] && [ -n "${UNIFI_PASSWORD:-}" ]; then
        login_url="${UNIFI_LOGIN_URL:-${UNIFI_URL%/}/api/login}"
        echo "  login URL: ${login_url}"
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"${UNIFI_USERNAME}\",\"password\":\"${UNIFI_PASSWORD}\"}" \
            "$login_url" 2>/dev/null)
        case "$code" in
            200) echo "  login: 200 OK (credentials accepted)" ;;
            400) echo "  !! login: 400 -- endpoint exists but request rejected. UniFi OS uses" \
                      "/api/auth/login; set UNIFI_LOGIN_URL to that path." ;;
            401) echo "  !! login: 401 -- credentials rejected" ;;
            000) echo "  !! login: unreachable" ;;
            *) echo "  ?? login: HTTP $code" ;;
        esac
    else
        echo "  - no UniFi credentials (set UNIFI_API_KEY or UNIFI_USERNAME/PASSWORD)"
    fi
else
    echo "  - UNIFI_URL unset"
fi

echo
echo "Done. Any '!!' line is a config item to fix in /home/node-red/.env"
