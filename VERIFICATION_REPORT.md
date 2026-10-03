# Smart Home Dashboard - Verification Report

> **Corrected 2026-10-03.** The previous version of this file claimed "10/10
> requirements implemented (100%)" and stated that HTTPS, firewall, non-root
> Node-RED and `adminAuth` were all "✅ Done (Phase 6)". None of that was true of
> the deployed system. They were read from config files and setup scripts rather
> than from the running host — and the config file they were read from
> (`config/settings.js`) is not even read by Node-RED. Every claim below was
> re-checked against the live container.

## Test Run Summary

| Metric | Result |
|--------|--------|
| Test Command | `python -m pytest` (also via `.github/workflows/ci.yml` on every push) |
| Tests Executed | 221 |
| Pass/Fail | **221 passed, 0 failed** (2026-10-03) |
| CI | Green (sha `cb351bf`, all 9 steps) — pytest + flow structure + settings syntax + theme wiring |
| Coverage | N/A — no coverage tooling configured |

The count moved from 232 to 221 because 33 grep-based tests in
`tests/test_settings.py` were replaced by 17 behavioural ones (they asserted
keys that are not Node-RED settings and had been failing in CI). New coverage
was added in their place: theme wiring, env-template drift, flow structure.

### What the previous claim got wrong

| Previous claim | Measured reality |
|----------------|------------------|
| HTTPS on 1881 | **Nothing listens on 1881.** `:1880` serves plain HTTP 200 |
| Firewall (ufw) | **Not verified** on the container |
| Non-root `node-red` user | **Not used.** Service runs as root, userDir `/root/.node-red`. The non-root account was the *cause* of the deployment failure (`217/USER`) |
| `adminAuth` enabled | **Not enabled** |
| `config/settings.js` as "Node-RED configuration" | It was YAML under a `.js` name (unloadable) and is not read at runtime. Now valid JS, but still only a deploy-time template |

The lesson: a static check over files can pass while describing an architecture
the system does not have. `scripts/verify-security.sh` had exactly this flaw and
has been corrected.

---

## Documentation Review

### ✅ Present (and correct as of this revision)
- **README.md** — overview, install, config, troubleshooting; security section rewritten to actual posture
- **PROJECT_SUMMARY.md** — phase status corrected (security items marked not-done)
- **docs/SECURITY.md** — rewritten: states no TLS, firewall unverified, root process
- **deploy/README.md** — real deployment path; firewall step marked optional/unverified
- **deploy/.env.example** — single env template, checked against the flows by `tests/test_env_template.py`
- **config/settings.js** — valid JavaScript, documented keys only
- **tests/** — 221 tests, plus flow-structure and theme-wiring guards
- **CI** — `ci.yml` enforces all of the above on every push

### ⚠️ Missing
- **CHANGELOG.md** — none
- **Integration tests** — no live-API tests in the suite (`tools/verify_live_data.py`
  exists as a manual probe, not a CI test)
- **`adminAuth`** — the editor/admin API is open to anyone who can reach :1880

---

## Requirement Coverage Matrix

| Requirement | Status | Evidence |
|-------------|--------|----------|
| Node-RED Dashboard UI | ✅ Working | 5 tabs served live at `http://sh-dashboard:1880/ui/`; 51 nodes deployed |
| Hubitat Integration | ✅ Working | Devices tab live; Maker API HTTP 200 (20588 B) |
| UniFi Network Monitoring | ✅ Working | Network tab renders **63 clients** (hostname/IP/MAC) |
| Home Lab Monitor (Proxmox) | ✅ Working | CPU/memory gauges render live (HTTP 200, 1636 B) |
| Kanban Board | ✅ Working | Typed a task, pressed Add, row rendered (verified in-browser) |
| Mobile Responsive Design | ✅ Working | Dark theme applied; verified in-browser (bg `rgb(26,26,46)`, 44px targets) |
| Settings / Deployment Info tab | ✅ Working | Renders (was blank: one-shot inject + wrong `props` schema) |
| **HTTPS / TLS** | ❌ **Not implemented** | No listener on 1881 |
| **Firewall (ufw)** | ⚠️ **Unverified** | Rules referenced in scripts; not confirmed applied |
| **Non-root Node-RED** | ❌ **Not used (deliberate)** | Runs as root so it works; non-root was the failure mode |
| **adminAuth** | ❌ **Not enabled** | Editor/Admin API unauthenticated on :1880 |
| Credential rotation tooling | ✅ Exists | `scripts/rotate-credentials.sh` (executable, syntax-checked) |

**Coverage: 7/8 functional requirements working. Security items are partial —
see the ❌/⚠️ rows above.**

---

## Open Issues / Recommendations

### Critical
- [ ] **Enable `adminAuth`** — anyone reaching :1880 can edit flows and read the
      credentials they use. Generate a real hash: `node-red admin hash-pw`.
- [ ] **Integration tests** — `tools/verify_live_data.py` is manual; wire a
      network-free variant into CI if useful

### Medium
- [ ] **TLS** — optional; the real key is `https` in `/root/.node-red/settings.js`
- [ ] **Firewall** — decide whether to apply ufw on the container, or delete the
      claim from the scripts
- [ ] **CHANGELOG.md**
- [x] **CI tests** — done: rewritten to run pytest + 3 static gates; green
- [x] **`.env` exclusion** — done

### Low
- [ ] **Deprecated `proxmox/` path** — marked DO-NOT-USE; could be deleted outright
- [ ] **`deploy/setup.sh`** — verify it provisions a working runtime on a fresh
      container (partially verified this session)

---

## Conclusion

The dashboard is **functionally complete and deployed**: 5 tabs, live data from
Proxmox, Hubitat and UniFi, a working mobile theme, and a green CI pipeline that
enforces flow structure, settings validity and theme wiring.

It is **not security-hardened**. It serves plain HTTP, with no authentication,
on a private LAN, and the process runs as root. That is an acceptable posture for
a single-purpose LAN dashboard behind a trusted network — but it should be stated
plainly rather than described as "production-ready security configuration".

Verify the static checks with `./scripts/verify-security.sh`. Note that the
script inspects files, not the running host, so treat its exit code as necessary
but not sufficient.
