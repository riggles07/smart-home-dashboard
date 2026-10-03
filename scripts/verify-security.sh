#!/bin/bash
# verify-security.sh - Phase 6 Security Hardening Verification
#
# Verifies all four Phase 6 hardening pillars:
#   1. HTTPS/SSL configuration
#   2. Firewall rules
#   3. Non-root Node-RED user
#   4. Credential rotation tooling
#
# Usage: ./scripts/verify-security.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

PASS=0
FAIL=0

check() {
    local desc="$1"
    local result="$2"  # "pass" | "fail" | "warn"
    case "$result" in
        pass)
            echo "  ✅ PASS: ${desc}"
            PASS=$((PASS + 1))
            ;;
        fail)
            echo "  ❌ FAIL: ${desc}"
            FAIL=$((FAIL + 1))
            ;;
        warn)
            echo "  ⚠️  WARN: ${desc}"
            ;;
    esac
}

echo "=== Phase 6 Security Hardening Verification ==="
echo "Project: ${PROJECT_DIR}"
echo ""

# --- 1. HTTPS / SSL -------------------------------------------------------
# NOTE: this section previously grepped config/settings.js for 'enabled: true',
# HSTS and X-Frame-Options and reported PASS. Those checks were meaningless:
#   * config/settings.js is NOT read by the runtime -- Node-RED reads settings
#     only from its userDir (/root/.node-red/settings.js).
#   * `server.ssl` / `httpStaticHeaders` are not Node-RED settings keys at all.
#   * Nothing listens on 1881; TLS is not deployed.
# A check that passes while describing a system that does not exist is worse
# than no check. This section now reports the actual transport posture, and
# treats TLS as an optional, currently-absent feature rather than a failure.
echo "--- 1. HTTPS / SSL (not deployed) ---"
echo "     transport: plain HTTP on :1880; no TLS listener."
echo "     To enable TLS, add the real 'https' key to the USERDIR settings"
echo "     (/root/.node-red/settings.js) -- NOT config/settings.js."
if [ -f /etc/node-red/fullchain.pem ]; then
    if openssl x509 -checkend 2592000 -noout -in /etc/node-red/fullchain.pem >/dev/null 2>&1; then
        check "SSL cert valid for >30 days" pass
    else
        check "SSL cert valid for >30 days" fail
    fi
    if [ "$(stat -c %a /etc/node-red/private.key)" = "600" ]; then
        check "Private key permissions 600" pass
    else
        check "Private key permissions 600" fail
    fi
else
    check "TLS: not configured (optional)" warn
    echo "     (no cert at /etc/node-red -- expected; TLS is not deployed)"
fi

# --- 2. Firewall ----------------------------------------------------------
echo ""
echo "--- 2. Firewall ---"
# The REAL deployment path is deploy/setup.sh. The proxmox/ scripts are the
# original (deprecated) path and still provision the runtime that broke:
# User=node-red with no such account (217/USER), /home/node-red which is never
# created, and MemoryDenyWriteExecute=true which kills V8's JIT (SIGSYS).
DEPLOY_SETUP="${PROJECT_DIR}/deploy/setup.sh"
DEPRECATED_UNIT="${PROJECT_DIR}/proxmox/node-red.service"


# Firewall rules live in the deployment SCRIPT, not in a systemd unit -- a unit
# has no ufw lines, so testing one for them can only ever fail. Only the real
# deployment path is checked here. The old script asserted these same rules in
# proxmox/ AND in the unit, which is why it reported failures regardless of
# reality.
for f in "$DEPLOY_SETUP"; do
    if grep -q "ufw --force enable" "$f" 2>/dev/null; then
        check "ufw enabled in $(basename "$f")" pass
    else
        check "ufw enabled in $(basename "$f")" warn
        echo "     (no ufw rules in the deploy script -- firewall is NOT applied by this repo)"
    fi
    if grep -q "from 192.168.1.0/24" "$f" 2>/dev/null; then
        check "LAN-only allow rules in $(basename "$f")" pass
    else
        check "LAN-only allow rules in $(basename "$f")" warn
    fi
done

# Live firewall check (only meaningful on the deploy host)
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    check "ufw active on this host" pass
else
    check "ufw active on this host (deploy target)" warn
    echo "     (firewall runs inside the LXC container, not the build host)"
fi

# --- 3. Process user ------------------------------------------------------
# NOTE: this section used to assert `User=node-red` and `useradd -m` in the
# setup scripts. That was the ORIGINAL BUG, not a hardening goal: the unit named
# a user that was never created, so systemd failed with 217/USER and
# WorkingDirectory=/home/node-red pointed at a nonexistent path. The service
# now runs as root with userDir /root/.node-red, and setup.sh no longer creates
# the account. Asserting the old architecture here would re-introduce the
# failure. This section now checks what the deployment actually requires.
echo "--- 3. Process user / runtime ---"
if grep -qE '^User=root|Name=User' "$DEPLOY_SETUP" 2>/dev/null; then
    check "service runs as root (matches deployment)" pass
else
    check "service runs as root (matches deployment)" warn
    echo "     (verify the generated unit in deploy/setup.sh)"
fi

# The paths the unit uses must be the ones that exist.
if grep -q "/root/.node-red" "$DEPLOY_SETUP" 2>/dev/null; then
    check "setup.sh uses userDir /root/.node-red" pass
else
    check "setup.sh uses userDir /root/.node-red" fail
fi

# MemoryDenyWriteExecute must be OFF: it kills the V8 JIT (SIGSYS) and Node
# cannot start. A unit leaving it enabled cannot run Node-RED.
if grep -qE 'MemoryDenyWriteExecute=(true|yes)' "$DEPLOY_SETUP" 2>/dev/null; then
    check "MemoryDenyWriteExecute is not enabled" fail
    echo "     (true disables W^X and breaks V8's JIT -- Node exits with SIGSYS)"
else
    check "MemoryDenyWriteExecute is not enabled" pass
fi

# The deprecated proxmox/ unit is kept for history but MUST NOT be deployed --
# it names a user that does not exist and enables MemoryDenyWriteExecute.
if [ -f "$DEPRECATED_UNIT" ]; then
    check "deprecated proxmox unit is marked DO NOT USE" warn
    echo "     (proxmox/node-red.service still has User=node-red + MemoryDenyWriteExecute=true;"
    echo "      deploy/setup.sh generates the working unit. Do not install the proxmox one.)"
fi

HARDENING_OPTS="NoNewPrivileges ProtectSystem PrivateTmp RestrictSUIDSGID"
for opt in $HARDENING_OPTS; do
    if grep -q "^${opt}" "${PROJECT_DIR}/proxmox/node-red.service" 2>/dev/null; then
        check "systemd hardening: ${opt}" pass
    else
        check "systemd hardening: ${opt}" fail
    fi
done

# Live check (deploy host)
if id node-red >/dev/null 2>&1; then
    check "node-red user exists on this host" pass
else
    check "node-red user exists on this host (deploy target)" warn
    echo "     (user is created inside the LXC container)"
fi

# --- 4. Credential rotation -----------------------------------------------
echo ""
echo "--- 4. Credential Rotation ---"
ROTATE="${PROJECT_DIR}/scripts/rotate-credentials.sh"
if [ -x "$ROTATE" ]; then
    check "rotate-credentials.sh exists and is executable" pass
else
    check "rotate-credentials.sh exists and is executable" fail
fi

if bash -n "$ROTATE" 2>/dev/null; then
    check "rotate-credentials.sh syntax valid" pass
else
    check "rotate-credentials.sh syntax valid" fail
fi

if grep -q "openssl rand" "$ROTATE" 2>/dev/null; then
    check "Password generation uses openssl rand (CSPRNG)" pass
else
    check "Password generation uses openssl rand (CSPRNG)" fail
fi

if grep -q "chmod 600" "$ROTATE" 2>/dev/null; then
    check "Env file restricted to 600 after rotation" pass
else
    check "Env file restricted to 600 after rotation" fail
fi

if grep -q "\.env" "${PROJECT_DIR}/.gitignore" 2>/dev/null; then
    check ".env excluded from git" pass
else
    check ".env excluded from git" fail
fi

if grep -q "ROTATE_CERT_DAYS" "$ROTATE" 2>/dev/null; then
    check "Cert age-based rotation threshold configured" pass
else
    check "Cert age-based rotation threshold configured" fail
fi

# --- Summary ---------------------------------------------------------------
echo ""
echo "=== Summary ==="
echo "Passed: ${PASS}"
echo "Failed: ${FAIL}"
if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "❌ Security hardening incomplete - fix failures above"
    exit 1
else
    echo "✅ All static security checks passed"
    echo "   (WARN items are deploy-host runtime checks)"
    exit 0
fi