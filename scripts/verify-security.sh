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
echo "--- 1. HTTPS / SSL ---"
SETTINGS="${PROJECT_DIR}/config/settings.js"
if grep -q "enabled: true" "$SETTINGS" 2>/dev/null; then
    check "SSL enabled in settings.js" pass
else
    check "SSL enabled in settings.js" fail
fi

if grep -q "/etc/node-red/fullchain.pem" "$SETTINGS" 2>/dev/null; then
    check "SSL cert path points to /etc/node-red" pass
else
    check "SSL cert path points to /etc/node-red" fail
fi

if grep -q "Strict-Transport-Security" "$SETTINGS" 2>/dev/null; then
    check "HSTS security header configured" pass
else
    check "HSTS security header configured" fail
fi

if grep -q "X-Frame-Options" "$SETTINGS" 2>/dev/null; then
    check "X-Frame-Options header configured" pass
else
    check "X-Frame-Options header configured" fail
fi

# Live cert check (if present on this host)
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
    check "SSL cert present at /etc/node-red (deploy target)" warn
    echo "     (cert is generated on the deploy host by setup-smarthome.sh)"
fi

# --- 2. Firewall ----------------------------------------------------------
echo ""
echo "--- 2. Firewall ---"
SETUP_SH="${PROJECT_DIR}/proxmox/setup-smarthome.sh"
POST_INSTALL="${PROJECT_DIR}/proxmox/post-install.sh"

for f in "$SETUP_SH" "$POST_INSTALL"; do
    if grep -q "ufw --force enable" "$f" 2>/dev/null; then
        check "ufw enabled in $(basename "$f")" pass
    else
        check "ufw enabled in $(basename "$f")" fail
    fi
    if grep -q "from 192.168.1.0/24" "$f" 2>/dev/null; then
        check "LAN-only allow rules in $(basename "$f")" pass
    else
        check "LAN-only allow rules in $(basename "$f")" fail
    fi
    if grep -q "allow 1881/tcp" "$f" 2>/dev/null; then
        check "HTTPS port 1881 allowed in $(basename "$f")" pass
    else
        check "HTTPS port 1881 allowed in $(basename "$f")" fail
    fi
done

# Live firewall check (only meaningful on the deploy host)
if command -v ufw >/dev/null && ufw status 2>/dev/null | grep -q "Status: active"; then
    check "ufw active on this host" pass
else
    check "ufw active on this host (deploy target)" warn
    echo "     (firewall runs inside the LXC container, not the build host)"
fi

# --- 3. Non-root Node-RED -------------------------------------------------
echo ""
echo "--- 3. Non-root Node-RED ---"
for f in "$SETUP_SH" "$POST_INSTALL" "${PROJECT_DIR}/proxmox/node-red.service"; do
    if grep -q "User=node-red" "$f" 2>/dev/null; then
        check "User=node-red in $(basename "$f")" pass
    else
        check "User=node-red in $(basename "$f")" fail
    fi
done

if grep -q "useradd -m" "$SETUP_SH" 2>/dev/null; then
    check "node-red user creation in setup script" pass
else
    check "node-red user creation in setup script" fail
fi

if grep -q "useradd -m" "$POST_INSTALL" 2>/dev/null; then
    check "node-red user creation in post-install" pass
else
    check "node-red user creation in post-install" fail
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