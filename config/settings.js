/**
 * Node-RED settings -- Smart Home Dashboard
 *
 * This file MUST be valid JavaScript. It previously held YAML (starting with a
 * '#' comment) under a .js name, so it could never be loaded by Node-RED at all.
 *
 * Scope note: this file documents the intended runtime configuration for a
 * deploy. The RUNNING instance on sh-dashboard reads its settings from the
 * service's userDir (/root/.node-red/settings.js) -- Node-RED only ever reads
 * settings from its userDir, never from a repo path. `deploy/setup.sh`
 * generates that file.
 *
 * ONLY keys documented at
 *   https://nodered.org/docs/user-guide/runtime/configuration
 * appear below. Do not add others. These are NOT Node-RED settings and will
 * either break the file or be silently ignored:
 *   plugins          (plugins are npm packages -- `npm install`, not config.
 *                     `externalModules` only enables installing from the editor)
 *   flowFiles        (there is exactly ONE flow file option: `flowFile`)
 *   server           (the real keys are `https` / `httpServerOptions`)
 *   httpStaticHeaders (real key is `httpStatic`, plus `httpServerOptions`)
 *   ui.theme  ui.css  ui.tabs  ui.order
 *                    (the dashboard's ONLY runtime setting is `ui.path`;
 *                     theme/tabs/layout/css live in the editor UI)
 *   functionRepo  projectsDir
 *
 * Verify before any restart:
 *   node --check config/settings.js
 *   node -e "require('./config/settings.js'); console.log('loads OK')"
 */

module.exports = {
    // ---------------------------------------------------------------------
    // Runtime
    // ---------------------------------------------------------------------

    // Directory holding user data (flows, credentials, library).
    // Default for root is already /root/.node-red.
    userDir: process.env.NODE_RED_USERDIR || "/root/.node-red",

    // The file (relative to userDir, or absolute) holding the flows.
    flowFile: "flows.json",
    flowFilePretty: true,

    // Editor/API port.
    uiPort: process.env.NODE_RED_PORT || 1880,

    // Secret used to encrypt the credentials file. Must stay stable: if it
    // changes, previously stored credentials become unreadable.
    credentialSecret: process.env.NODE_RED_CREDENTIAL_SECRET || "shd-local-secret",

    // ---------------------------------------------------------------------
    // HTTP endpoints
    // ---------------------------------------------------------------------
    // Admin root and the static-file mount. The admin root defaults to "/";
    // mounting it under a sub-path is a real, supported option.
    httpAdminRoot: "/",
    httpStatic: "/usr/share/node-red",

    // ---------------------------------------------------------------------
    // Dashboard (node-red-dashboard)
    // ---------------------------------------------------------------------
    // `path` is the ONLY dashboard runtime setting. Default is "ui".
    ui: { path: "ui" },

    // ---------------------------------------------------------------------
    // Logging
    // ---------------------------------------------------------------------
    logging: {
        console: { level: process.env.NODE_RED_LOG_LEVEL || "info" },
        file: {
            level: "info",
            // NOTE: the real logging.file keys are `level`, `metrics`, `audit`
            // and `handler`. `maxFiles`/`maxSize` are NOT Node-RED settings --
            // rotation is configured on the `handler` instead.
            handler: undefined
        }
    },

    // ---------------------------------------------------------------------
    // External modules -- allows installing nodes from the editor.
    // This is the real key; `plugins:` is not one.
    // ---------------------------------------------------------------------
    externalModules: {
        autoInstall: false
    },

    // ---------------------------------------------------------------------
    // Admin authentication. Disabled to match the current deployment.
    // To enable, generate a real bcrypt hash first:
    //   node-red admin hash-pw
    // Never hand-write a placeholder hash -- an invalid hash breaks login.
    // ---------------------------------------------------------------------
    // adminAuth: {
    //     type: "credentials",
    //     users: [{
    //         username: process.env.NODE_RED_USER || "admin",
    //         password: "$2b$08$REPLACE_WITH_OUTPUT_OF_node-red_admin_hash-pw",
    //         permissions: "*"
    //     }]
    // },

    // ---------------------------------------------------------------------
    // HTTPS. Disabled -- the live instance serves plain HTTP on uiPort.
    // The real key is `https`; `server: { ssl: ... }` is not a Node-RED
    // setting. To enable, uncomment with real certificate files.
    // ---------------------------------------------------------------------
    // https: {
    //     key:  require("fs").readFileSync("/etc/node-red/private.key"),
    //     cert: require("fs").readFileSync("/etc/node-red/fullchain.pem")
    // },
};
