#!/usr/bin/env bash
# Repair a broken /root/.node-red/settings.js with a known-good one.
#
# Context: the previous settings.js.example in this repo invented keys that are
# not part of Node-RED's schema (flowFiles, plugins, server, ui.theme, ui.tabs,
# ui.order, functionRepo, projectsDir, httpStaticHeaders). A file built from it
# fails to parse. This script replaces it with a minimal, verified settings file.
#
# What it preserves:
#   - your flowFile location, so the dashboard does NOT come up empty
#     (this is the dangerous one: Node-RED's default is flows_<hostname>.json,
#      so silently dropping flowFile can make existing flows disappear)
#
# What it does NOT preserve:
#   - adminAuth and https blocks (both are commented out in the replacement).
#     Evidence from the live instance shows adminAuth is not currently active
#     (the admin API answers without credentials), so this is not a downgrade.
#     The script prints a reminder if it sees those keys in the old file.
#
# Run as root, ON the Node-RED LXC:   bash repair-settings.sh

set -uo pipefail

SETTINGS=${SETTINGS:-/root/.node-red/settings.js}
DIR=$(dirname "$SETTINGS")
USER_DIR=${NODE_RED_USERDIR:-$DIR}

[ "$(id -u)" -eq 0 ] || { echo "must run as root"; exit 1; }
[ -f "$SETTINGS" ] || { echo "no settings.js at $SETTINGS"; exit 1; }

echo "== what is here now =="
echo "  settings: $SETTINGS ($(wc -l < "$SETTINGS") lines)"

echo
echo "== flowFile detection (must be preserved) =="
# Match an uncommented  flowFile: "..."  or  flowFile: '...'
FLOW_FILE=$(grep -E '^[[:space:]]*flowFile[[:space:]]*:' "$SETTINGS" 2>/dev/null \
    | head -1 \
    | sed -E 's/.*flowFile[[:space:]]*:[[:space:]]*//; s/[,;].*$//; s/^["'\'']//; s/["'\'']$//' \
    | tr -d '[:space:]')
if [ -n "$FLOW_FILE" ]; then
    echo "  found flowFile: $FLOW_FILE"
else
    echo "  no flowFile key in the current file"
fi

# What flow files actually exist?
echo "  flow files on disk:"
ls -1 "$DIR"/*.json 2>/dev/null | sed 's|.*/|    |' || echo "    (none)"

# Decide the value to write. Preference: the existing flowFile; else flows.json
# if it is present; else omit the key entirely and let Node-RED use its default.
WRITE_FLOWFILE=""
if [ -n "$FLOW_FILE" ] && [ -f "$DIR/$FLOW_FILE" ]; then
    WRITE_FLOWFILE="$FLOW_FILE"
    echo "  -> will preserve flowFile: $WRITE_FLOWFILE (file exists)"
elif [ -f "$DIR/flows.json" ]; then
    WRITE_FLOWFILE="flows.json"
    echo "  -> will use flowFile: flows.json (found on disk)"
else
    echo "  -> will OMIT flowFile (let Node-RED use its default flows_<hostname>.json)"
fi

echo
echo "== backing up =="
STAMP=$(date +%Y%m%d-%H%M%S)
cp -a "$SETTINGS" "$SETTINGS.broken-$STAMP"
echo "  saved: $SETTINGS.broken-$STAMP"

# Warn if we are about to drop something they had configured.
if grep -qE '^[[:space:]]*adminAuth[[:space:]]*:' "$SETTINGS" 2>/dev/null; then
    echo "  NOTE: old file had an adminAuth block -- it is NOT carried over."
    echo "        Re-add it with: node-red admin hash-pw   (then paste the hash)"
fi
if grep -qE '^[[:space:]]*https[[:space:]]*:' "$SETTINGS" 2>/dev/null; then
    echo "  NOTE: old file had an https block -- it is NOT carried over."
fi

echo
echo "== writing known-good settings.js =="
if [ -n "$WRITE_FLOWFILE" ]; then
    FLOWFILE_LINE="    flowFile: \"$WRITE_FLOWFILE\","
else
    FLOWFILE_LINE="    // flowFile omitted -- Node-RED uses its default flows_<hostname>.json"
fi

cat > "$SETTINGS" <<EOF
/**
 * Node-RED settings -- Smart Home Dashboard
 *
 * Only keys from Node-RED's documented settings schema are used here:
 *   https://nodered.org/docs/user-guide/runtime/configuration
 *
 * Do NOT add keys outside that schema. The following are NOT Node-RED settings
 * and will break this file or be silently ignored:
 *   flowFiles  plugins  server  functionRepo  projectsDir  httpStaticHeaders
 *   ui.theme   ui.css   ui.tabs   ui.order
 * There is exactly ONE flow-file option: flowFile. The dashboard's only runtime
 * setting is  ui: { path: "..." }  -- theme/tabs/css are editor-side.
 *
 * Always validate before restarting:
 *   node --check "\$SETTINGS"
 */

module.exports = {
    // Directory holding user data (flows, credentials, library).
    userDir: process.env.NODE_RED_USERDIR || "$USER_DIR",

    // Flow file, relative to userDir.
$FLOWFILE_LINE

    // Indent the flow file so diffs are readable.
    flowFilePretty: true,

    // Editor/API port.
    uiPort: process.env.NODE_RED_PORT || 1880,

    // Encrypts the credentials file. Changing it invalidates stored credentials.
    // Not used by this project (the flows read secrets from the environment).
    credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET || "shd-local-secret",

    // Dashboard: 'path' is the ONLY runtime dashboard setting. Default: "ui".
    ui: { path: "ui" },

    logging: {
        console: { level: process.env.NODE_RED_LOG_LEVEL || "info" }
    }

    // adminAuth: { ... }   -- enable with a real hash: node-red admin hash-pw
    // https:    { ... }   -- enable with real cert/key paths
};
EOF
echo "  written: $SETTINGS ($(wc -l < "$SETTINGS") lines)"

echo
echo "== validating (Node-RED will do exactly this) =="
if node --check "$SETTINGS" >/dev/null 2>&1; then
    echo "  OK   parses"
else
    echo "  !!   still broken:"
    node --check "$SETTINGS" 2>&1 | head -8 | sed 's/^/       /'
    exit 2
fi
if node -e "require('$SETTINGS')" >/dev/null 2>&1; then
    echo "  OK   loads"
    node -e "
      const s=require('$SETTINGS');
      console.log('       flowFile:', s.flowFile || '(default)');
      console.log('       userDir :', s.userDir);
      console.log('       ui      :', JSON.stringify(s.ui));
    "
else
    echo "  !!   throws on load:"
    node -e "require('$SETTINGS')" 2>&1 | head -8 | sed 's/^/       /'
    exit 2
fi

echo
echo "Done. Next:  bash fix-node-red-service.sh"
echo "  (that script fixes User=node-red not existing, which causes status=217/USER)"
