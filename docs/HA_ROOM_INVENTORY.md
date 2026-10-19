# Home Assistant room inventory — measured 2026-10-19

HA **2026.10.2**, 456 states, **17 areas**. Read via `/api/template` using Jinja
`areas()` / `area_entities()` — HA exposes no REST endpoint for the area registry,
so a template is the only REST-reachable path (no WebSocket needed).

| Area (id) | Name | Entities | Domains present |
|---|---|---|---|
| `living_room` | Living Room | 4 | light, binary_sensor, camera, event |
| `kitchen` | Kitchen | 20 | binary_sensor, sensor, event, number, switch, camera |
| `bedroom` | Bedroom | 17 | event, switch, light, sensor, binary_sensor, **climate** |
| `exterior` | Exterior | 13 | light, switch, camera, event |
| `virtual` | virtual | 51 | calendar, update, binary_sensor, select, sensor, event, switch, button |
| `basement` | Basement | 39 | sensor, binary_sensor, event, switch, light, camera |
| `outside` | Outside | 13 | event, switch, sensor, binary_sensor, light |
| `media` | Media | 18 | event, switch, light, binary_sensor, remote, select |
| `family_room` | Family Room | 11 | binary_sensor, sensor, switch, light |
| `foyer` | Foyer | 15 | sensor, binary_sensor, switch, light, **climate** |
| `kids_rooms` | Kids Rooms | 4 | sensor, switch |
| `laundry` | Laundry | 39 | sensor, binary_sensor, switch, event, number, select |
| `upstairs_hall` | Upstairs Hall | 2 | sensor, binary_sensor |
| `garage` | Garage | 84 | sensor, binary_sensor, switch, button, select, lock, cover, light, number, update, camera, event |
| `backyard` | Backyard | 0 | — |
| `master_bedroom` | Master Bedroom | 0 | — (but holds a climate entity) |

(one row truncated at the 2.5 kB probe cap — 16 of 17 counted)

## Why this matters for the redesign

**The P5 placeholders are no longer needed.** Earlier today P5 was parked because
HA had zero climate, zero energy and zero weather entities. That is no longer true:

| What P5 needed | What now exists |
|---|---|
| `climate.*` | `climate.master_bedroom_master_bedroom` (cool), `climate.hallway_hallway` (cool) |
| energy `sensor.*` in W/kWh | **22 sensors**, incl. `sensor.basement_sump_pump_power` (W), `sensor.family_room_family_room_left_power` (W), `sensor.washer_energy_today` (Wh), `sensor.refrigerator_energy_*`, `sensor.laundry_dryer_energy_*` |
| `weather.*` | `weather.forecast_home` |

So the thermostat dial, the energy chart and the weather block can be built on
**real data** — the placeholder policy (and its `data-demo` marker) is moot for
all three. P5 should be rewritten against these entity ids rather than placeholders.

Caveats to respect:
- Only **two** climate entities exist, and both report `cool`. A three-state
  heat/cool/auto dial would offer modes the devices do not support — read the
  `hvac_modes` attribute before drawing controls.
- The energy sensors are split between **power (W)** and **cumulative energy
  (Wh/kWh)**. A "Power Consumed" chart wants instantaneous W; the `energy_*`
  sensors are daily/monthly totals. Mixing them on one axis produces a
  meaningless line. Pick one and label the axis.
- `backyard` and `master_bedroom` report 0 area entities while holding devices —
  area assignment is incomplete there, which will show as empty rooms in an
  auto-generated area dashboard.

## Rooms that will look thin in any area-based dashboard

`upstairs_hall` (2), `backyard` (0), `master_bedroom` (0), `kids_rooms` (4),
`living_room` (4). An area dashboard renders one card per area, so these will be
near-empty. Either complete the area assignments in HA first, or accept it.


## Device registry reality (measured via config/device_registry/list)

Devices per area:

```
virtual:26  basement:16  media:15  garage:9  bedroom:8  exterior:8  foyer:8
outside:8  family_room:6  kitchen:4  laundry:4  living_room:3  kids_rooms:2
upstairs_hall:1   (unassigned):47
backyard:0  master_bedroom:0
```

The 47 unassigned devices are **HA's own system devices** -- `Home Assistant Core`,
`Home Assistant Supervisor`, `Home Assistant Host`, `Home Assistant Operating
System`, `Sun` -- plus integration shells like `SHIELD`. They are not home devices
awaiting a room, so "assign the unassigned devices" is not a real task here.

Consequence: an area-based dashboard would render `backyard` and `master_bedroom`
as empty cards. The only ways to fix that are to delete those areas or leave them
for future hardware; there is nothing to move into/out of them.


## Room dashboard created (2026-10-19)

`lovelace/dashboards/create` -> url_path **`by-room`**, title **"By Room"**, storage
mode, shown in the sidebar, `require_admin: false`.

Config saved as a **dashboard strategy**, not hand-written views:

```json
{"strategy": {"type": "areas"}}
```

Read back with `lovelace/config` and confirmed intact (`keys=strategy`,
`type=areas`). This is the built-in auto-generated area dashboard, so it rebuilds
itself from the area registry -- adding a device to a room in HA updates the
dashboard with no edit here.

Two things HA validated the hard way, worth remembering:

- **`url_path` must contain a hyphen.** `rooms` is rejected with
  `invalid_format: Url path needs to contain a hyphen (-)`. `by-room` is accepted.
- The strategy type is genuinely `areas` on HA 2026.10.2 -- verified by readback
  rather than assumed, because a wrong strategy key saves without complaint and
  leaves a blank dashboard.

Verification is programmatic (create + save + readback over the WebSocket). The
rendered dashboard was **not** visually confirmed: viewing it needs an interactive
HA login, which this agent does not have. First thing to eyeball is whether
`backyard` and `master_bedroom` render as empty room cards -- per the registry
measurement they hold nothing, so they will.

No probes were left behind: the live Node-RED deployment is back to the repo's
135 nodes with zero leftovers.
