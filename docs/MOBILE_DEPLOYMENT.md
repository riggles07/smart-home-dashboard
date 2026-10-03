# Galaxy A7 Lite Deployment Guide

Phase 5: mobile-responsive UI deployment on the **Samsung Galaxy A7 Lite (SM-T220)**.

Target device profile:

| Property | Value |
|----------|-------|
| Model | Samsung Galaxy Tab A7 Lite 8.7" (SM-T220) |
| Viewport (portrait) | 800 × 1280 CSS px |
| Viewport (landscape) | 1280 × 800 CSS px |
| Device pixel ratio | 2x |
| Browser | Samsung Internet / Chrome (Android) |

The theme (`css/dashboard.css`) re-flows the dashboard into a single
column at ≤1024px, with density tuning at 900px (A7 Lite portrait),
600px (phones / split-screen) and 380px (small phones).

---

## 1. The dashboard is a systemd service (do not run `node-red` by hand)

On this deployment Node-RED is managed by systemd, running **as root** with
userDir `/root/.node-red`:

```bash
systemctl status node-red
systemctl restart node-red        # after editing /root/.node-red/.env
```

Do **not** start it manually with `node-red` / `node-red -u ~/.node-red`. A
hand-started process binds `:1880` and then the service cannot — the unit
crash-loops with `Error: port in use` while the stray answers. (Recovering from
that is `deploy/takeover-1880.sh`.) It also runs without the `.env`, so every
flow fails with `ENOTFOUND` defaults.

Confirm it is listening on all interfaces and reachable off-box:

```bash
ss -tlnp | grep 1880              # expect 0.0.0.0:1880 or *:1880, NOT 127.0.0.1
```

## 2. Access from the Galaxy A7 Lite

1. Put the tablet on the **same network path** as the server — same Wi-Fi
   (LAN) or the same tailnet (Tailscale).
2. Open **Samsung Internet** or **Chrome**.
3. Navigate to `http://<server-ip>:1880/ui/`
   - This deployment is reached over **Tailscale**: `http://100.76.56.35:1880/ui/`
   - The short name `sh-dashboard` only resolves where MagicDNS is active
     (it resolves via the search domain `tail5a1c91.ts.net`). **If the short
     name fails but the IP works, use the IP** — that is a DNS/MagicDNS issue
     on the client, not a dashboard problem.
   - **`localhost` will NOT work** — on the tablet that means the tablet itself.
4. Confirm you get the dark theme (see §3). If the page is light-grey, the
   theme did not load.

## 3. Install as a home-screen app (recommended)

For a kiosk-like experience:

**Samsung Internet:** Menu (☰) → **Add page to** → **Home screen**.

**Chrome:** Menu (⋮) → **Add to Home screen** → **Install**.

The shortcut launches the dashboard full-screen without browser chrome.

## 4. Keep the screen awake (kiosk mode)

If the tablet is wall-mounted:

- **Settings → Advanced features → Auto screen off / Screen timeout** → 30 minutes or use a "Stay Awake" app while charging.
- Enable **Settings → Display → Keep screen on while viewing** (Smart Stay) if available.

## 5. Verify responsiveness on the device

Run through this checklist on the A7 Lite:

- [ ] **Portrait (800px):** cards stack in one column; no horizontal scroll.
- [ ] **Landscape (1280px):** rows render side-by-side.
- [ ] **Touch targets:** switch/slider/button controls are ≥44px and tap accurately.
- [ ] **Tables:** device and client lists fit the screen; text wraps, no clipping.
- [ ] **Rotation:** rotating the device does not zoom the layout or lose position.
- [ ] **Auto-refresh:** status indicators pulse; data updates every 5s.

Automated theme checks (on the server):

```bash
python3 -m pytest tests/test_mobile_ui.py -v
```

## 6. Troubleshooting

| Symptom | Fix |
|---------|-----|
| "This site can't be reached" | Wrong IP, or the tablet is not on the tailnet. Verify the service: `systemctl status node-red`, then `ss -tlnp \| grep 1880` (must not be `127.0.0.1`). See §1 — do not hand-start `node-red`. |
| `sh-dashboard` won't resolve but the IP works | MagicDNS is not active on the client. Use the IP, or enable MagicDNS / `tailscale up --accept-dns=true` on the tablet. |
| Page loads but looks light-grey / desktop-sized | The theme did not load. **`settings.js` cannot apply a CSS file** — the legacy dashboard has no `css:` setting (only `ui.path`, `ui.middleware`, `ui.ioMiddleware`, `ui.readOnly`, `ui.defaultGroup`). The theme is injected by the **`Mobile theme` `ui_template`** node (`tools/gen_flows.py`), which inlines `css/dashboard.css` into a `<style>` block and re-asserts `body.nr-dashboard-theme` so it beats the dashboard's own `#eee` rule. Verify: open devtools and check `getComputedStyle(document.body).backgroundColor` is `rgb(26, 26, 46)`. |
| Controls too small to tap | The theme sets `--shd-touch-target: 44px`. Note the tab drawer entries and the toolbar hamburger are Angular Material elements (`md-list-item`, `button.md-icon-button`), **not** `.ui_tab .tab-link` — confirm the override in `THEME_OVERRIDE` is present, since those selectors must match the rendered DOM (verified 48px / 44px). |
| Slow refresh on Wi-Fi | Move tablet closer to AP; check UniFi controller client stats for the tablet |
| Certificate warnings | If SSL is enabled on port 1881, use `http://…:1880` on the LAN or install the CA cert on the tablet |
| Dashboard stale after rotate | Pull-to-refresh or toggle airplane mode to force a socket reconnect |