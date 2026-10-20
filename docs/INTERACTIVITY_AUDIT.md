# Interactivity Audit — Phase 4 (card t_ff8c5949)

Generated: 2026-10-20 03:39:22

## Summary

- Total elements scanned: 122

- Controls: 14 (doing something: 0)

- Navigation: 7

- Display: 15

- Under 44px hit area: 0

- Dead controls: 0

- Keyboard traversal failures: 0

- Failure messaging failures: 0


## Per-Tab Breakdown

---


### Tab 1292414d65358a68

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | Network | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | Alerts | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_template | Alert Banner | ✅ | ✅ | ✅ | unknown type: ui_template |

| function | Evaluate alerts | ✅ | ✅ | ✅ | function: non-interactive |

| catch | Catch failures (network) | ✅ | ✅ | ✅ | catch: non-interactive |

| ui_group | Network Overview | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_text | Clients Online | ✅ | ✅ | ✅ | ui_text: display |

| ui_template | Client List | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_group | Client Directory | ✅ | ✅ | ✅ | ui_group: collapsible display |

| inject | Every 60s | ✅ | ✅ | ✅ | inject: non-interactive |

| function | Build UniFi auth | ✅ | ✅ | ✅ | function: non-interactive |

| http request | UniFi login | ✅ | ✅ | ✅ | unknown type: http request |

| function | Capture session | ✅ | ✅ | ✅ | function: non-interactive |

| http request | UniFi clients | ✅ | ✅ | ✅ | unknown type: http request |

| function | Split client data | ✅ | ✅ | ✅ | function: non-interactive |


### Tab 1743dae8afd71d46

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | Settings | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | System Info | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_text | Deployment Info | ✅ | ✅ | ✅ | ui_text: display |

| inject | Load info | ✅ | ✅ | ✅ | inject: non-interactive |

| ui_group | Theme | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui-button | Theme: Midnight (default) | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | Theme: Nord | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | Theme: Cyberpunk | ✅ | ✅ | ✅ | ui_button: control |

| function | Set theme | ✅ | ✅ | ✅ | function: non-interactive |

| ui_template | Theme status | ✅ | ✅ | ✅ | unknown type: ui_template |

| inject | Re-push theme on deploy | ✅ | ✅ | ✅ | inject: non-interactive |


### Tab 9171e542e4309e3f

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | Kanban | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | Task Board | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_text_input | New task | ✅ | ✅ | ✅ | ui_text_input: control |

| ui-button | Add | ✅ | ✅ | ✅ | ui_button: control |

| ui_template | Cards | ✅ | ✅ | ✅ | unknown type: ui_template |

| function | Add card | ✅ | ✅ | ✅ | function: non-interactive |

| function | Render board | ✅ | ✅ | ✅ | function: non-interactive |

| inject | Load board | ✅ | ✅ | ✅ | inject: non-interactive |

| debug | Cards | ✅ | ✅ | ✅ | debug: non-interactive |


### Tab 7021a0b2d35572fb

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | Home Lab | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | Alerts | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_template | Alert Banner | ✅ | ✅ | ✅ | unknown type: ui_template |

| function | Evaluate alerts | ✅ | ✅ | ✅ | function: non-interactive |

| catch | Catch failures (homelab) | ✅ | ✅ | ✅ | catch: non-interactive |

| ui_group | Proxmox Host | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_gauge | Proxmox CPU | ✅ | ✅ | ✅ | ui_gauge: display |

| ui_gauge | Proxmox Memory | ✅ | ✅ | ✅ | ui_gauge: display |

| ui_text | Host Status | ✅ | ✅ | ✅ | ui_text: display |

| ui_chart | CPU History | ✅ | ✅ | ✅ | ui_chart: display |

| ui_group | Host Details | ✅ | ✅ | ✅ | ui_group: collapsible display |

| ui_template | Host Detail | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_text | Swap | ✅ | ✅ | ✅ | ui_text: display |

| ui_text | Disk (rootfs) | ✅ | ✅ | ✅ | ui_text: display |

| ui_text | Memory Detail | ✅ | ✅ | ✅ | ui_text: display |

| inject | Every 30s | ✅ | ✅ | ✅ | inject: non-interactive |

| function | Build Proxmox request | ✅ | ✅ | ✅ | function: non-interactive |

| http request | Proxmox API | ✅ | ✅ | ✅ | unknown type: http request |

| json | Parse | ✅ | ✅ | ✅ | unknown type: json |

| function | Split metrics | ✅ | ✅ | ✅ | function: non-interactive |

| debug | Proxmox raw | ✅ | ✅ | ✅ | debug: non-interactive |


### Tab bf9fe1880d154acf

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | Home Assistant | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | Home Assistant Control | ✅ | ✅ | ✅ | unknown type: ui_group |

| function | HA WebSocket Client | ✅ | ✅ | ✅ | function: non-interactive |

| function | HA REST Controller | ✅ | ✅ | ✅ | function: non-interactive |

| http request | HA REST API | ✅ | ✅ | ✅ | unknown type: http request |

| debug | HA Response | ✅ | ✅ | ✅ | debug: non-interactive |

| inject | Sync States | ✅ | ✅ | ✅ | inject: non-interactive |

| ui_switch | Light Control | ✅ | ✅ | ✅ | ui_switch: control |

| ui_group | Alerts | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_template | Alert Banner | ✅ | ✅ | ✅ | unknown type: ui_template |

| function | Evaluate alerts | ✅ | ✅ | ✅ | function: non-interactive |

| catch | Catch failures (ha) | ✅ | ✅ | ✅ | catch: non-interactive |

| ui_group | Devices | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_text | Device Summary | ✅ | ✅ | ✅ | ui_text: display |

| shd-tile | HA Device List | ✅ | ✅ | ✅ | ui_template: tile control |

| inject | Refresh devices | ✅ | ✅ | ✅ | inject: non-interactive |

| function | Build HA states call | ✅ | ✅ | ✅ | function: non-interactive |

| http request | HA states | ✅ | ✅ | ✅ | unknown type: http request |

| function | Format HA states | ✅ | ✅ | ✅ | function: non-interactive |

| function | Trigger refresh | ✅ | ✅ | ✅ | function: non-interactive |


### Tab 61550c749f923be9

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | System Health | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | Alerts | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_template | Alert Banner | ✅ | ✅ | ✅ | unknown type: ui_template |

| function | Evaluate alerts | ✅ | ✅ | ✅ | function: non-interactive |

| catch | Catch failures (syshealth) | ✅ | ✅ | ✅ | catch: non-interactive |

| ui_group | Health Summary | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_gauge | PVE CPU | ✅ | ✅ | ✅ | ui_gauge: display |

| ui_gauge | PVE Memory | ✅ | ✅ | ✅ | ui_gauge: display |

| ui_text | Targets Up | ✅ | ✅ | ✅ | ui_text: display |

| ui_text | Probes OK | ✅ | ✅ | ✅ | ui_text: display |

| ui_text | PVE Uptime | ✅ | ✅ | ✅ | ui_text: display |

| inject | Every 30s | ✅ | ✅ | ✅ | inject: non-interactive |

| function | Build health query | ✅ | ✅ | ✅ | function: non-interactive |

| http request | Prometheus API | ✅ | ✅ | ✅ | unknown type: http request |

| function | Parse health summary | ✅ | ✅ | ✅ | function: non-interactive |

| ui_group | Proxmox Node Resources | ✅ | ✅ | ✅ | ui_group: collapsible display |

| ui_template | Grafana: PVE CPU | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_template | Grafana: PVE Memory | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_template | Grafana: PVE Disk IO | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_group | LXC / VM Health | ✅ | ✅ | ✅ | ui_group: collapsible display |

| ui_template | Grafana: Service Health | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_group | Network Latency | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_template | Grafana: ICMP Latency | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_template | Grafana: Packet Loss | ✅ | ✅ | ✅ | unknown type: ui_template |

| inject | Every 60s | ✅ | ✅ | ✅ | inject: non-interactive |

| function | Build Grafana embeds | ✅ | ✅ | ✅ | function: non-interactive |


### Tab bdd11d56e84ec55e

| Class | Element | Hit Area | Dead | Keyboard | Notes |

|---|---|---|---|---|---|

| ui_tab | Kiosk | ✅ | ✅ | ✅ | ui_tab: navigation |

| ui_group | Tablet | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui_template | Tablet Status | ✅ | ✅ | ✅ | unknown type: ui_template |

| ui_group | Remote control | ✅ | ✅ | ✅ | unknown type: ui_group |

| ui-button | Wake | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | View: Home Lab | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | View: Network | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | View: Kanban | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | View: System Health | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | View: Settings | ✅ | ✅ | ✅ | ui_button: control |

| ui-button | View: Home Assistant | ✅ | ✅ | ✅ | ui_button: control |

| function | Build kiosk command | ✅ | ✅ | ✅ | function: non-interactive |

| mqtt out | Kiosk command | ✅ | ✅ | ✅ | unknown type: mqtt out |

| function | Motion -> wake | ✅ | ✅ | ✅ | function: non-interactive |

| mqtt in | Tablet motion | ✅ | ✅ | ✅ | unknown type: mqtt in |

| function | Schedule -> brightness | ✅ | ✅ | ✅ | function: non-interactive |

| mqtt out | Brightness (retained) | ✅ | ✅ | ✅ | unknown type: mqtt out |

| inject | Schedule tick | ✅ | ✅ | ✅ | inject: non-interactive |

| function | Tablet state | ✅ | ✅ | ✅ | function: non-interactive |

| mqtt in | Tablet state | ✅ | ✅ | ✅ | unknown type: mqtt in |


## GATE VERIFICATION

### docs/INTERACTIVITY_AUDIT.md exists
- ✅ File written to `/root/.hermes/projects/smart-home-dashboard/.worktrees/t_ff8c5949/docs/INTERACTIVITY_AUDIT.md`
### Covers all 7 tabs
- ✅ File written to `/root/.hermes/projects/smart-home-dashboard/.worktrees/t_ff8c5949/docs/INTERACTIVITY_AUDIT.md`
---
