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
- **Backend:** Integration must reside in `flows/home-assistant-integration.js` (replacing `hubitat-integration.js`).
- **Deployment:** Ensure HA connectivity from the `sh-dashboard` LXC (LAN: 192.168.4.178).

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
