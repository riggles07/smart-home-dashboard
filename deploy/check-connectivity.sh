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

# Load the env file into this shell's environment. Without this, every ${VAR}
# below reads the invoking shell (which has none of them) and reports a false
# "unset" for a perfectly configured host.
#
# Candidate locations, most-specific first: the unit's userDir home (what
# systemd would use) then $HOME (what a hand-started process would use).
env_file=""
for cand in "${NODE_RED_ENV_FILE:-}" /home/node-red/.env /root/.node-red/.env "$HOME/.node-red/.env"; do
    [ -n "$cand" ] && [ -f "$cand" ] && { env_file="$cand"; break; }
done
if [ -n "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file" 2>/dev/null \
        && echo "loaded env: $env_file" \
        || echo "  ?? could not load $env_file -- check quoting/spaces in values"
    set +a
else
    echo "note: no env file found in /home/node-red/.env, /root/.node-red/.env or \$HOME/.node-red/.env"
    echo "      (set NODE_RED_ENV_FILE to point elsewhere)"
fi

# --- are the env vars even loaded into the flows? ---------------------------
echo
echo "== service environment =="
# The probe must test the environment the FLOWS run in, not this shell -- a
# plain ${VAR} here would always look unset and report a false failure.
#
# Preference order for the source of truth:
#   1. the running Node-RED process  (/proc/<pid>/environ)
#   2. the env file itself           (parsed, so the file's own contents are still
#      meaningful when we cannot inspect the live process)
env_vars=""
env_src=""
# 1. Prefer the environment of the actual Node-RED process. That is the only
#    thing that proves the flows can see the values.
svc_pid=$(systemctl show node-red -p MainPID --value 2>/dev/null || echo "")
if [ -z "$svc_pid" ] || [ "$svc_pid" = "0" ]; then
    svc_pid=$(pgrep -f 'node-red' 2>/dev/null | head -1 || echo "")
fi
if [ -n "$svc_pid" ] && [ -r "/proc/$svc_pid/environ" ]; then
    proc_vars=$(tr '\0' '\n' < "/proc/$svc_pid/environ" 2>/dev/null)
    if echo "$proc_vars" | grep -qE '^(HUBITAT|UNIFI|PROXMOX)_'; then
        env_vars="$proc_vars"
        env_src="running process (pid $svc_pid) -- these ARE visible to the flows"
    fi
fi

# 2. Fall back to the env file we already resolved above (same list, so the two
#    sections can never disagree about which file is in use).
if [ -z "$env_vars" ] && [ -n "$env_file" ] && [ -f "$env_file" ]; then
    env_vars=$(grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "$env_file" 2>/dev/null)
    env_src="env file $env_file (NOT confirmed in the running process)"
fi

if [ -n "$env_vars" ]; then
    echo "  source: $env_src"
    matched=$(echo "$env_vars" | grep -E '^(HUBITAT|UNIFI|PROXMOX)_' || true)
    if [ -n "$matched" ]; then
        # Show that values are set, never the values themselves.
        echo "$matched" | sed -E 's/=(.*)$/=<set>/' | sed 's/^/    /'
    else
        echo "  !! no HUBITAT_/UNIFI_/PROXMOX_ variables found in this source."
        echo "     The flows will fall back to *.local defaults and ENOTFOUND."
    fi
    if [ -n "$env_file" ] && [ -z "$(echo "$env_vars" | grep -c '^')" ]; then :; fi
else
    echo "  ?? no env source found (no readable process, no env file)."
fi
echo "  NOTE: values defined in a file are only used by the running Node-RED if"
echo "        the process that started it had them -- see 'running' below."

# What is actually running Node-RED, and is the env file wired to it?
if command -v systemctl >/dev/null 2>&1; then
    printf '  unit: node-red is %s\n' "$(systemctl is-active node-red 2>/dev/null || echo unknown)"
    if systemctl cat node-red >/dev/null 2>&1; then
        systemctl cat node-red 2>/dev/null | grep -q "^EnvironmentFile=" \
            && echo "  unit: EnvironmentFile= present" \
            || echo "  unit: no EnvironmentFile= directive"
    else
        echo "  unit: no node-red.service in this container -- systemd is not managing it"
    fi
fi
# How is it actually running? An LXC often runs Node-RED by hand or under its
# own init, in which case the systemd unit (and any EnvironmentFile= on it) is
# irrelevant -- the process env is whatever its launcher had.
if command -v pgrep >/dev/null 2>&1; then
    rpid=$(pgrep -f 'node-red' 2>/dev/null | head -1 || echo "")
    if [ -n "$rpid" ]; then
        echo "  running: pid $rpid"
        if [ "$rpid" = "1" ]; then
            echo "    !! pid 1 is the container's init -- Node-RED is PID 1 (started as the"
            echo "       container command, not via systemd). Its env comes from the"
            echo "       container/process launcher, so an EnvironmentFile= drop-in has no"
            echo "       effect. Either put the variables in the container config, or start"
            echo "       it via a wrapper that sources the env file."
        fi
        if [ -r "/proc/$rpid/environ" ]; then
            if tr '\0' '\n' < "/proc/$rpid/environ" | grep -qE '^(HUBITAT|UNIFI|PROXMOX)_'; then
                echo "    flow vars ARE in pid $rpid's environment"
            else
                echo "    !! flow vars are NOT in pid $rpid's environment -- the running"
                echo "       Node-RED cannot see them (this is what makes the flows fall"
                echo "       back to *.local and ENOTFOUND)"
            fi
        fi
    fi
fi

# --- Proxmox ----------------------------------------------------------------
echo
echo "== Proxmox =="
if [ -n "${PROXMOX_URL:-}" ]; then
    echo "  PROXMOX_URL=${PROXMOX_URL}"
    check_dns "$(host_of "$PROXMOX_URL")"
    # Proxmox API tokens must be  <user>@<realm>!<tokenname>=<secret>.
    # The common mistakes are using the login realm form (root@pam) with no
    # !tokenname, or omitting the secret. Validate the SHAPE only, never print it.
    if [ -n "${PROXMOX_TOKEN:-}" ]; then
        if printf '%s' "$PROXMOX_TOKEN" | grep -qE '^[^@!]+@[^!=]+![^=]+=.+$'; then
            echo "  token format: OK (<user>@<realm>!<name>=<secret>)"
        else
            echo "  !! token format looks wrong. Expected <user>@<realm>!<name>=<secret>"
            echo "     e.g. root@pam!dashboard=xxxxxxxx-xxxx-xxxx"
            echo "     A bare 'root@pam' or a missing '!name=' will always give HTTP 401."
        fi
    fi
    code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
        -H "Authorization: PVEAPIToken=${PROXMOX_TOKEN:-}" \
        "${PROXMOX_URL}/api2/json/nodes/${PROXMOX_NODE:-pve}/status" 2>/dev/null)
    case "$code" in
        200) echo "  API: 200 OK (authenticated + authorised)" ;;
        401) echo "  !! API: 401 -- token rejected. Check the FORMAT:"
             echo "     <user>@<realm>!<tokenname>=<secret>   (a bare 'root@pam' always 401s)" ;;
        403) echo "  !! API: 403 -- token AUTHENTICATED but lacks permission (Sys.Audit)."
             echo "     Grant it: Datacenter -> Permissions -> Add -> API Token Permission"
             echo "       Path: /   Role: PVEAuditor   (select the token, not the user)"
             echo "     Note: if the token has 'Privilege Separation' enabled (the"
             echo "     default), it inherits NOTHING from its user -- the permission"
             echo "     must be granted to the TOKEN itself." ;;
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
        # Mirror the flow's own login-URL logic exactly, or this check tests a
        # different endpoint than the flow uses and misleads either way:
        #   UNIFI_LOGIN_URL if set -> else /api/auth/login at the console root
        #   for a /proxy/network base (UniFi OS) -> else <UNIFI_URL>/api/login
        if [ -n "${UNIFI_LOGIN_URL:-}" ]; then
            login_url="$UNIFI_LOGIN_URL"
        else
            console_root=$(root_of "$UNIFI_URL")
            case "$UNIFI_URL" in
                */proxy/network*) login_url="${console_root}/api/auth/login" ;;
                *) login_url="${UNIFI_URL%/}/api/login" ;;
            esac
        fi
        echo "  login URL: ${login_url}  (matches the flow's derivation)"
        code=$(curl -sk -o /dev/null -w "%{http_code}" --max-time 8 \
            -H "Content-Type: application/json" \
            -d "{\"username\":\"${UNIFI_USERNAME}\",\"password\":\"${UNIFI_PASSWORD}\"}" \
            "$login_url" 2>/dev/null)
        case "$code" in
            200) echo "  login: 200 OK (credentials accepted)" ;;
            400) echo "  !! login: 400 -- endpoint reached but request rejected." ;;
            401) echo "  !! login: 401 -- credentials rejected" ;;
            404) echo "  !! login: 404 -- wrong login path for this controller type" ;;
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
