#!/usr/bin/env bash
# Create kanban cards recording the configuration/variable changes made while
# bringing the Smart Home Dashboard Node-RED instance back up.
#
# Safe by construction:
#   - every card is created with --triage (inert while kanban.auto_decompose=false)
#   - --idempotency-key makes re-runs return the existing card instead of duplicating
#   - --board master is explicit so a board switch elsewhere cannot retarget this
#
# Run from anywhere:  bash scripts/create_config_drift_cards.sh
#
# NOTE: this CLI's `kanban create` has no --board flag; cards land on the
# CURRENT board. The script verifies the current board before writing anything.
set -uo pipefail

TENANT=smart-home-dashboard
BY=parent-session
DIR=$(mktemp -d)

# Refuse to write to the wrong board.
current=$(hermes kanban boards list 2>/dev/null | sed -n 's/^Current board: *//p')
if [ "$current" != "master" ]; then
    echo "refusing: current board is '${current:-unknown}', expected 'master'." >&2
    echo "switch with: hermes kanban boards switch master" >&2
    exit 1
fi

mk() { # mk <slug> <title>  ; body on stdin
    local slug="$1"; shift
    local title="$1"; shift
    cat > "$DIR/$slug.body"
    local id
    id=$(hermes kanban create "$title" \
        --body "$(cat "$DIR/$slug.body")" \
        --tenant "$TENANT" \
        --triage \
        --idempotency-key "$slug" \
        --created-by "$BY" \
        --json 2>/dev/null | python3 -c "import sys,json;print(json.load(sys.stdin).get('id','?'))" 2>/dev/null)
    printf '  %-40s %s\n' "$slug" "${id:-FAILED}"
}

echo "creating cards (current board: $current, tenant: $TENANT)"

mk "shd-setup-sh-runtime-drift" "Fix deploy/setup.sh: it provisions the exact runtime that broke (User=node-red, MemoryDenyWriteExecute)" <<'BODY'
The container on sh-dashboard had to be repaired by hand because deploy/setup.sh
provisions a runtime that cannot start. A fresh deploy reproduces the same
failures.

Evidence (deploy/setup.sh):
  :99    useradd -m -s /bin/bash node-red
  :126   User=node-red
  :127   Group=node-red
  :128   WorkingDirectory=/home/node-red
  :154   MemoryDenyWriteExecute=true

Observed consequences on sh-dashboard (journalctl -u node-red):
  node-red.service: Failed to determine user credentials: No such process
  node-red.service: Failed at step USER spawning /usr/bin/node-red
  Main process exited, code=exited, status=217/USER     (restart counter 73)

And after the user fault was fixed, the service still died until
MemoryDenyWriteExecute was disabled, because the V8 JIT needs an mprotect
RW->RX transition which W^X blocks (SIGSYS).

Actual working runtime (verified live):
  User=root  Group=root  WorkingDirectory=/root/.node-red
  ReadWritePaths=/root/.node-red   MemoryDenyWriteExecute=false
  EnvironmentFile=-/root/.node-red/.env

Required change: align deploy/setup.sh with the runtime that actually works.
Either (a) drop the node-red account entirely and run as root with userDir
/root/.node-red, or (b) keep a dedicated user AND create /home/node-red AND make
the mode-600 .env readable by it, AND relax ProtectSystem/ReadWritePaths so it
can write flows. (a) matches how this container is built; the data under /root is
root-owned.

Acceptance: deploy/setup.sh produces a unit that starts first time, and the
generated unit contains no User= naming a non-existent account and no
MemoryDenyWriteExecute=true. Cite the line numbers changed.

Repo: /root/.hermes/projects/smart-home-dashboard
BODY

mk "shd-root-env-example-wrong-names" "Fix root .env.example: wrong variable names; it disagrees with the flows" <<'BODY'
There are two env templates and the root one names variables nothing reads.

Evidence:
  /root/.hermes/projects/smart-home-dashboard/.env.example contains
    PROXMOX_HOST=proxmox.local
    PROXMOX_PORT=8006
    PROXMOX_USER=root@pam
    PROXMOX_PASS=your_password
    UNIFI_HOST=unifi.local
    UNIFI_PORT=8443
  i.e. PROXMOX_HOST/PROXMOX_PASS (2 occurrences) and UNIFI_HOST/UNIFI_PORT.

The flows read exactly these 14 names (extracted from the func bodies of
flows/all-flows.flow.json):
  HUBITAT_ACCESS_TOKEN HUBITAT_API_KEY HUBITAT_APP_ID HUBITAT_DEVICE_ID
  HUBITAT_URL PROXMOX_NODE PROXMOX_TOKEN PROXMOX_URL UNIFI_API_KEY
  UNIFI_LOGIN_URL UNIFI_PASSWORD UNIFI_SITE UNIFI_URL UNIFI_USERNAME

So PROXMOX_HOST, PROXMOX_PORT, PROXMOX_USER, PROXMOX_PASS, UNIFI_HOST and
UNIFI_PORT are read by nothing, and the root template omits PROXMOX_URL,
PROXMOX_TOKEN, HUBITAT_APP_ID, HUBITAT_DEVICE_ID, UNIFI_URL and UNIFI_API_KEY.

Required change: make the root .env.example a superset that contains every one of
the 14 names above, or delete it and keep a single template. deploy/.env.example
already contains all 14 -- use it as the source of truth.

Acceptance: for each of the 14 names, grep the root template and show it present;
show the removed names are gone. Note in the file which of the 14 are optional
(PROXMOX_NODE, UNIFI_SITE, UNIFI_LOGIN_URL) and which are alternatives
(HUBITAT_ACCESS_TOKEN vs HUBITAT_API_KEY; UNIFI_API_KEY vs UNIFI_USERNAME+UNIFI_PASSWORD).

Repo: /root/.hermes/projects/smart-home-dashboard
BODY

mk "shd-docs-stale-paths-users-keys" "Sweep docs for stale /home/node-red paths, User=node-red, and fabricated settings keys" <<'BODY'
Docs and scripts still describe a runtime and a settings schema that never worked.

Evidence (grep, excluding node_modules):
  /home/node-red referenced in 13 files, including
    docs/SECURITY.md, flows/README.md, deploy/.env.example, deploy/setup.sh,
    deploy/README.md, proxmox/setup-node-red.sh, proxmox/post-install.sh,
    proxmox/README.md, proxmox/README-LXC-CONTAINER.md, proxmox/setup-smarthome.sh
  User=node-red / useradd node-red referenced in 10 files, including
    scripts/verify-security.sh, docs/SECURITY.md, proxmox/post-install.sh
  MemoryDenyWriteExecute=true referenced in
    docs/SECURITY.md, deploy/setup.sh, proxmox/post-install.sh,
    proxmox/setup-smarthome.sh
  docs/SECURITY.md:13 cites "config/settings.js under httpStaticHeaders" --
    httpStaticHeaders is NOT a Node-RED setting and has no effect.
  docs/SECURITY.md also claims Node-RED runs as a non-root 'node-red' user,
    which is not true of the working instance.

Ground truth to document instead:
  userDir is /root/.node-red and the service runs as root (the data and the
  mode-600 .env are root-owned).
  MemoryDenyWriteExecute must be false for Node-RED (V8 JIT).
  Node-RED settings keys are limited to the documented schema. These do NOT
  exist and must not appear in docs or examples: flowFiles, plugins, server,
  functionRepo, projectsDir, httpStaticHeaders, ui.theme, ui.css, ui.tabs,
  ui.order. There is exactly ONE flow-file key: flowFile. The dashboard runtime
  setting is only  ui: { path: "..." }  -- theme/tabs/css are editor-side.
  Reference: https://nodered.org/docs/user-guide/runtime/configuration

Acceptance: no file under the repo references /home/node-red, User=node-red, or
MemoryDenyWriteExecute=true as an instruction; no doc presents a fabricated key as
real. Quote the grep before/after counts.

Repo: /root/.hermes/projects/smart-home-dashboard
BODY

mk "shd-project-docs-actual-state" "Update PROJECT_SUMMARY.md and deploy/README.md to the deployed reality" <<'BODY'
Project docs describe phases and a file layout, not the running system.

Verified current state on sh-dashboard (measured, not assumed):
  48 nodes across 5 tabs: Home Lab, Devices, Network, Kanban, Settings
  flowFile  : /root/.node-red/flows.json
  userDir   : /root/.node-red
  editor    : http://sh-dashboard:1880 (HTTP)
  dashboard : /ui  (legacy node-red-dashboard 3.6.6)
  Dashboard 2.0 (@flowfuse/node-red-dashboard) is ALSO installed but the flows do
  not use it -- worth stating so nobody mixes the two type families
  Node-RED v5.0.7 on Node.js v24.21.0

Live service verification (tools/verify_live_data.py, run against the host):
  Hubitat   HTTP 200, 20588 bytes   -> LIVE
  UniFi     HTTP 200, ~150000 bytes -> LIVE (via UNIFI_API_KEY)
  Proxmox   HTTP 403  Permission check failed (/nodes/pve, Sys.Audit)

Required change: update PROJECT_SUMMARY.md and deploy/README.md to state the above,
and document the five faults that had to be cleared to get here, because the
existing docs imply a deploy that already worked:
  1. settings.js contained keys outside Node-RED's schema -> SyntaxError on load
  2. unit User=node-red / Group=node-red -> the account does not exist (217/USER)
  3. MemoryDenyWriteExecute=true -> V8 JIT blocked (SIGSYS)
  4. an orphan Node-RED held port 1880, so the systemd instance could not bind
     and the process answering the API was the stale one with no env
  5. the .env never reached the runtime ("EnvironmentFile" was absent)

Also list the verification tools and what each proves:
  tools/gen_flows.py            regenerate flows (deterministic ids, palette-checked)
  tools/validate_flows.py       structure/wire integrity -- run before deploy
  tools/test_flow_functions.js  runs the func bodies from the deployed JSON
  tools/probe_runtime_env.py    proves which env vars the running runtime can see
  tools/verify_live_data.py     proves each tab returns live data
  deploy/check-connectivity.sh  host-local probes incl. Proxmox token shape

Acceptance: a reader who has never seen this repo can, from the docs alone, state
the userDir, the flowFile, the env var contract, and the three commands to verify a
deployment.

Repo: /root/.hermes/projects/smart-home-dashboard
BODY

mk "shd-ci-gate-flow-validation" "CI runs only pytest; add flow validation and function-node tests" <<'BODY'
The CI workflow does not exercise any of the flow tooling, so the failure mode we
spent this session on would pass CI.

Evidence (.github/workflows/ci.yml):
  :20  run: python -m pip install --upgrade pip pytest
  :23  run: python -m pytest -v
  Neither tools/validate_flows.py nor tools/test_flow_functions.js is invoked.

Consequence: a malformed flow JSON (dangling wire, orphaned tab/group reference,
empty function body) or a broken function node ships green.

Required change: add steps that run
  python3 tools/validate_flows.py flows/all-flows.flow.json
  node tools/test_flow_functions.js
against the committed flows. Both are pure-static (no host, no network) so they are
CI-safe. test_flow_functions.js reads func bodies out of flows/all-flows.flow.json,
so it tests the committed artifact rather than a copy.

Optional hardening: assert that tools/gen_flows.py regenerates flows
byte-identically (guards against someone hand-editing the JSON and the generator
drifting apart).

Acceptance: a deliberately broken flow (e.g. delete a wire target) fails CI, and
a clean tree passes. Paste both outcomes.

Repo: /root/.hermes/projects/smart-home-dashboard
BODY

mk "shd-credential-permission-docs" "Document credential + permission requirements (Proxmox token shape, Sys.Audit, UniFi API key)" <<'BODY'
Getting live data required specific credential shapes and a permission grant that
nothing in the repo currently documents. Record them so the next person does not
repeat this session.

Evidence, from probing the live host:
  Proxmox, wrong token format -> HTTP 401 (token rejected)
  Proxmox, correct format but no rights -> HTTP 403 with body
    {"data":null,"message":"Permission check failed (/nodes/pve, Sys.Audit)"}
  UniFi, legacy username/password against a UniFi OS console -> HTTP 401
  UniFi, API key (X-API-KEY) -> HTTP 200, ~150000 bytes of client data
  Hubitat Maker API -> HTTP 200, 20588 bytes of device data

Required change: add a credentials section to deploy/README.md and deploy/.env.example
that states all of the following.

Proxmox:
  - Token format is exactly <user>@<realm>!<tokenname>=<secret>, from
    Datacenter -> Permissions -> API Tokens -> Add. The secret is shown once.
    A bare 'root@pam' or a missing '!name=' always yields 401.
  - The token needs Sys.Audit on the node. Grant it to the TOKEN, not just the user:
    Datacenter -> Permissions -> Add -> API Token Permission, Path /,
    Role PVEAuditor. Privilege Separation defaults ON, so a token inherits nothing
    from its user -- this is the usual cause of a correct token still 403-ing.
  - 401 vs 403 are different faults: 401 = bad token, 403 = missing permission.
    The dashboard's token currently has the format right and lacks Sys.Audit.

UniFi:
  - UNIFI_URL must include the API prefix: UniFi OS consoles (UDM/Cloud Gateway)
    serve the Network app under /proxy/network (e.g.
    https://192.168.1.1/proxy/network); a self-hosted controller uses the root path.
    A UniFi OS console answers <title>UniFi OS</title> at the host root.
  - Prefer UNIFI_API_KEY (Network 8+: Settings -> Control Plane -> Integrations).
    Local username/password via /api/auth/login is often rejected on UniFi OS.
  - UNIFI_LOGIN_URL is optional and auto-derived from the /proxy/network prefix.

Hubitat:
  - HUBITAT_ACCESS_TOKEN may be supplied as HUBITAT_API_KEY; the flow falls back.
  - HUBITAT_DEVICE_ID is required for the Devices tab's controls.

Also note the diagnostic trap: a UniFi OS console returns 401 for EVERY /api/*
path including bogus ones, so only a 404 disproves a URL prefix.

Acceptance: each statement above appears in the repo, and deploy/check-connectivity.sh
still validates the Proxmox token SHAPE without printing the value.

Repo: /root/.hermes/projects/smart-home-dashboard
BODY

echo "done"
