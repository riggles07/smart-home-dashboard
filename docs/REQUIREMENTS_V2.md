# Smart Home Dashboard - Requirements Update (2026-10-08)

## 1. Home Assistant Migration
**Goal:** Replace Hubitat as the primary smart home orchestrator with Home Assistant (HA).

### Functional Requirements
- **Entity Migration:** Map existing Hubitat device controls (Lights, Switches, Sensors) to HA entities.
- **API Integration:** Implement the Home Assistant WebSocket API or REST API within Node-RED.
- **State Synchronization:** Real-time bidirectional state updates between HA and the Node-RED dashboard.
- **Command Execution:** Ability to trigger HA services (e.g., `light.turn_on`, `switch.toggle`) directly from the UI.
- **Auth Management:** Secure handling of HA Long-Lived Access Tokens (LLAT) via `.env`.

### Technical Constraints
- **Protocol:** Prefer WebSocket for real-time status; REST for one-off commands.
- **Backend:** Integration is implemented in the **generated** flows —
  `tools/gen_flows.py` emits the Home Assistant tab into
  `flows/99-other.flow.json` (and `all-flows.flow.json`). `flows/home-assistant-integration.js`
  and its `.py` mirror are custom **node-type definitions** retained as
  reference implementations, not flows; editing them does not change the
  dashboard.
- **Deployment:** Ensure HA connectivity from the `sh-dashboard` LXC
  (LAN: `192.168.4.100`, tailnet `100.76.56.35`). Note HA is reached over the
  tailnet on **port 80**, not 8123 — see `docs/HOME_ASSISTANT_INTEGRATION.md`.

---

## 4. Implementation status (recorded 2026-10-16)

Requirements above are the original statement of intent; this records what
actually shipped, so the two are not confused.

| § | Requirement | Status |
|---|-------------|--------|
| 1 | Home Assistant migration | **Additive, not a replacement.** HA ships as tab 7 with WebSocket state sync + REST control. The Hubitat Devices tab is still present and still speaks Maker API — Hubitat has not been retired. |
| 1 | HA auth via LLAT in `.env` | Done — `HA_TOKEN`, presence-checked by `tools/nodered_env_probe3.py` |
| 1 | Command execution from the UI | Done — the switch maps to `light.turn_on` / `light.turn_off` for `HA_ENTITY_ID` |
| 2 | Grafana embeds | Done — six `d-solo` iframes + a native Prometheus summary query on the System Health tab |
| 2 | LXC/VM health, latency, packet loss | Done via Grafana panels; the Blackbox exporter supplies latency/loss |
| 3 | CSS-variable theming in `css/dashboard.css` | Done — `--shd-*` custom properties, guarded by `tests/test_colour_guard.py` and `tests/test_theme_wiring.py` |
| 3 | 44px touch targets | Done — asserted by `tests/test_mobile_ui.py` |
| 3 | Dynamic backgrounds / multiple palettes | **Not delivered.** One dark theme; no time-of-day or weather-driven backgrounds. |
| 3 | Animations / haptic-style feedback | **Not delivered.** |

---

## 2. Grafana Home Lab Integration
**Goal:** Enhance the Home Lab monitor by embedding high-fidelity Grafana panels into the Node-RED dashboard.

### Functional Requirements
- **Embedded Panels:** Integrate specific Grafana panels (via iframes or API) for:
    - Proxmox Node Resource usage (CPU/RAM/IO).
    - LXC/VM health and uptime.
    - Network latency and packet loss (from Prometheus Blackbox).
- **Unified View:** Create a "System Health" tab in the Node-RED dashboard that acts as a portal to Grafana.
- **Dynamic Filtering:** (Optional) Pass variables from Node-RED to Grafana dashboards to filter by node or container.

### Technical Constraints
- **CORS/Security:** Configure Grafana `allow_embedding = true` in `grafana.ini`.
- **Auth:** Use Grafana anonymous access for specific dashboards (read-only) or API keys for secure embeds.
- **Performance:** Optimize panel load times to prevent UI lag on the Galaxy A7 Lite.

---

## 3. Advanced UI/UX Design (Theming & Readability)
**Goal:** Transform the dashboard from a functional tool into a high-end, themable interface with a focus on clarity and aesthetic appeal.

### Functional Requirements
- **Theming System:**
    - **Dynamic Backgrounds:** Support for changing backgrounds based on time of day, weather, or system state (e.g., subtle gradients, blurred imagery, or dark/light mode transitions).
    - **Customizable Palettes:** Implement CSS variable-based themes (e.g., "Cyberpunk", "Minimalist", "Nord") that can be switched via a dashboard setting.
- **Readability & Clarity:**
    - **Visual Hierarchy:** Use distinct typography and spacing to separate critical alerts from general status.
    - **High Contrast:** Ensure all text meets WCAG accessibility standards against dynamic backgrounds.
    - **Reduced Clutter:** Implement "progressive disclosure" — show essential status at a glance, with detailed controls available via a tap.
- **Workflow Optimization:**
    - **Intentional Navigation:** Redesign the tab/menu structure to follow a logical user flow (e.g., Home → Security → Network → System Health).
    - **Interactive Feedback:** Add subtle animations or haptic-style visual cues when a command is successfully sent to HA.

### Technical Constraints
- **Performance:** Background effects (blur/gradients) must not impact the frame rate on the Galaxy A7 Lite (SM-T220).
- **Implementation:** Styles must be consolidated in `css/dashboard.css` using CSS Custom Properties (`--var`) for easy theme swapping.
- **Responsive Design:** All new UI elements must adhere to the 44px touch-target standard.
