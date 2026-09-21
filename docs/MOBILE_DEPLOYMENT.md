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

## 1. Start the dashboard on the server

Node-RED must listen on `0.0.0.0` (not `127.0.0.1`) so the tablet can
reach it over the LAN:

```bash
# On the server / LXC container
cd /root/smart-home-dashboard
node-red
# Dashboard: http://<server-ip>:1880
```

Confirm the port is reachable from the device's network:

```bash
# On the server
ss -tlnp | grep 1880
```

## 2. Access from the Galaxy A7 Lite

1. Connect the tablet to the **same Wi-Fi network** as the server.
2. Open **Samsung Internet** or **Chrome**.
3. Navigate to: `http://<server-ip>:1880` — e.g. `http://192.168.1.100:1880`.
   - Use the server's LAN IP. **`localhost` will NOT work** — on the
     tablet, `localhost` refers to the tablet itself, not the server.
4. The responsive theme auto-selects the single-column layout.

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
| "This site can't be reached" | Wrong IP or Node-RED bound to localhost — restart with `node-red -u ~/.node-red` bound to `0.0.0.0`, check `ss -tlnp` |
| Page loads but looks desktop-sized | Theme not applied — confirm `css: "css/dashboard.css"` in the dashboard config and that the file is deployed |
| Controls too small to tap | Verify `--shd-touch-target: 44px` rules in `css/dashboard.css` |
| Slow refresh on Wi-Fi | Move tablet closer to AP; check UniFi controller client stats for the tablet |
| Certificate warnings | If SSL is enabled on port 1881, use `http://…:1880` on the LAN or install the CA cert on the tablet |
| Dashboard stale after rotate | Pull-to-refresh or toggle airplane mode to force a socket reconnect |