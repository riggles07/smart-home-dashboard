# Security Hardening (Phase 6)

This document covers the four security-hardening pillars implemented for the
Smart Home Dashboard: HTTPS, firewall, non-root Node-RED, and credential rotation.

## 1. HTTPS / TLS

- **Config**: `config/settings.js` — `server.ssl.enabled: true`, listening on port **1881**
- **Certificate**: self-signed RSA-2048, generated at `/etc/node-red/fullchain.pem`
  (key at `/etc/node-red/private.key`, mode 600)
- **Generation**: `proxmox/setup-smarthome.sh` creates the cert during deployment;
  `scripts/rotate-credentials.sh --cert` regenerates it on demand
- **Security headers** (in `config/settings.js` under `httpStaticHeaders`):
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HSTS)
  - `X-Frame-Options: DENY` (clickjacking protection)
  - `X-Content-Type-Options: nosniff` (MIME sniffing protection)
  - `X-XSS-Protection: 1; mode=block`
  - `Content-Security-Policy` (limits script/style/img/font sources)

> Self-signed certs trigger browser warnings. For a trusted cert, place a
> Let's Encrypt-issued `fullchain.pem`/`private.key` at the same paths.

## 2. Firewall

- **Tool**: ufw (default-deny incoming)
- **Rules** (applied by `proxmox/setup-smarthome.sh` and `proxmox/post-install.sh`):
  ```
  ufw allow from 192.168.1.0/24 to any port 1880  # HTTP  - LAN only
  ufw allow from 192.168.1.0/24 to any port 1881  # HTTPS - LAN only
  ufw --force enable
  ```
- Ports 1880/1881 are only reachable from the local LAN subnet — no WAN exposure.
- Proxmox-level: LXC containers are created with `firewall=1` on the veth
  interface (`proxmox/setup-lxc.sh`), enabling PVE firewall inspection.

## 3. Non-Root Node-RED

- **User**: `node-red` (created by `setup-smarthome.sh` / `post-install.sh` with
  `useradd -m`, home `/home/node-red`, `~/.node-red` mode 700)
- **systemd unit** (`proxmox/node-red.service` and the embedded copy in the
  setup scripts) runs as `User=node-red` with sandboxing:
  - `NoNewPrivileges=true` — no setuid/escalation
  - `ProtectSystem=strict` — read-only filesystem except `ReadWritePaths=/home/node-red`
  - `PrivateTmp=yes`, `PrivateDevices=yes`
  - `ProtectKernelTunables/Modules`, `ProtectControlGroups=yes`
  - `RestrictSUIDSGID`, `RestrictNamespaces`, `LockPersonality`, `MemoryDenyWriteExecute`

## 4. Credential Rotation

Run `./scripts/rotate-credentials.sh` to rotate:

| Credential | Mechanism |
|------------|-----------|
| Node-RED admin password | New 24-char random password (`openssl rand`); bcrypt-hashed when Node.js/bcryptjs available |
| SSL certificate | Regenerated if older than `ROTATE_CERT_DAYS` (default 30) or with `--cert` |
| Hubitat API key / Maker API token | Replaced with `ROTATED_YYYYMMDD_...` markers; re-issue in Hubitat admin |
| UniFi password | Marker replacement; reset in UniFi controller |

- `.env` is backed up before every rotation (`backups/`)
- `.env` permissions reset to 600 after each rotation
- `--dry-run` mode shows planned changes without touching anything
- **Schedule**: run monthly (e.g. via cron: `0 3 1 * * /path/to/rotate-credentials.sh --cert`)

## Verification

```bash
./scripts/verify-security.sh
```

Checks all four pillars across config files, setup scripts, the systemd unit,
and the rotation tooling — 27 static checks (plus deploy-host runtime WARNs).
Exit code 0 = all pass.

## Deployment Checklist

1. Run `proxmox/setup-smarthome.sh` inside the LXC container (creates user,
   service, firewall, cert)
2. Run `./scripts/rotate-credentials.sh` to replace the default `admin/admin` login
3. Re-issue Hubitat Maker API token and UniFi password; update `.env`
4. Restart: `systemctl restart node-red`
5. Verify: `./scripts/verify-security.sh` and browse `https://<container-ip>:1881`