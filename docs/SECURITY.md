# Security Posture

> **Status: this document previously described four "implemented" pillars
> (HTTPS, firewall, non-root Node-RED, credential rotation) that were not true of
> the deployed system. It was rewritten on 2026-10-03 to state what was actually
> measured.**
>
> What was measured, against the running container:
>
> | Claim | Reality |
> |-------|---------|
> | HTTPS on port 1881 | **Not listening.** `curl https://sh-dashboard:1881` -> no response; `:1880` serves plain HTTP 200 |
> | Firewall (ufw) | **Not verified** on the container; no rules confirmed applied |
> | Non-root Node-RED | **Not used, deliberately.** Service runs as root, userDir `/root/.node-red` |
> | Credential rotation tooling | `scripts/rotate-credentials.sh` exists and is executable |
>
> The non-root account was the *cause* of the original deployment failure, not a
> hardening win: `User=node-red` with no such account produced `217/USER`, and
> `WorkingDirectory=/home/node-red` pointed at a directory that did not exist.

## Why the previous claims were wrong

`config/settings.js` was cited as configuring `server.ssl.enabled: true` and
`httpStaticHeaders`. Three problems:

1. **It was not JavaScript.** The file held YAML (a leading `#` comment) under a
   `.js` name, so Node-RED could never have loaded it. `node --check` rejected it.
2. **The keys do not exist.** `server` is not a Node-RED settings key (the real
   one is `https`), and `httpStaticHeaders` is not either. There is no
   `ui.theme`/`ui.css`/`ui.tabs`/`ui.order` — the dashboard's only runtime
   setting is `ui.path`.
3. **Nothing reads it at runtime.** Node-RED reads settings only from its
   userDir. The live instance uses `/root/.node-red/settings.js`, which
   `deploy/setup.sh` generates. A repo-path settings file has no effect.

The file is now valid JavaScript containing only documented keys, and is
explicitly a *deploy-time template*, not the live config.

## 1. Transport

Plain HTTP on port 1880. There is no TLS.

If TLS is wanted, the real mechanism is the `https` key in the
**userDir** settings (`/root/.node-red/settings.js`), with real certificate
files:

```js
https: {
    key:  require("fs").readFileSync("/etc/node-red/private.key"),
    cert: require("fs").readFileSync("/etc/node-red/fullchain.pem")
}
```

Then restart the service. Setting any of this in `config/settings.js` will do
nothing. There is no `server:` block to edit.

Exposure: port 1880 is reachable on the LAN and over the tailnet. It is not
exposed to the WAN.

## 2. Firewall

Not applied at the container level as far as this repo can verify. The setup
scripts reference ufw rules for `192.168.1.0/24`, but ufw has not been confirmed
installed or enabled on the running container. Treat LAN restriction as
**unverified**.

## 3. Process user

Node-RED runs as **root**, with:

- userDir and env file: `/root/.node-red/`
- systemd unit: `node-red.service`, with a drop-in at
  `/etc/systemd/system/node-red.service.d/10-fix-runtime.conf` setting
  `User=root`, `Group=root`, `WorkingDirectory=/root/.node-red`,
  `ReadWritePaths=/root/.node-red`, `EnvironmentFile=-/root/.node-red/.env`, and
  `MemoryDenyWriteExecute=false`.

`MemoryDenyWriteExecute=false` is required: disabling W^X kills the V8 JIT and
Node fails immediately with `SIGSYS`. A unit that leaves it `true` cannot run
Node-RED.

Running as root is a deliberate convenience for a single-purpose container
serving a private LAN dashboard. It is not a hardening claim.

## 4. Credentials

- Secrets live in `/root/.node-red/.env` (the unit's `EnvironmentFile`), not in
  the flows. `deploy/.env.example` is the single template.
- `scripts/rotate-credentials.sh` exists for rotation.
- `scripts/verify-security.sh` performs static checks over files. **Its
  non-root/HTTPS assertions check for `User=node-red` and `config/settings.js`
  contents — neither reflects the deployed system, so a passing exit code does
  not mean these properties hold.** Reconcile it before relying on it.

## Practical risk statement

This is a LAN-only dashboard on a private network, served over plain HTTP with
no authentication enabled on the admin/editor endpoints. Anyone who can reach
port 1880 can read and edit the flows and therefore read the credentials the
flows use. If that is not acceptable, the fixes are, in order: enable
`adminAuth` with a real bcrypt hash, then add TLS via the `https` key.
