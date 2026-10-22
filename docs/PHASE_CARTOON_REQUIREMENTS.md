# Phase 7 — Cartoon Floorplan Dashboard: Requirements

**Status:** DRAFT for user decisions · **Written** 2026-10-22
**Supersedes for the plan view:** `/floor-plan` ha-floorplan implementation
**Handoff target:** coder subagent / kanban worker. Every requirement below is
written so it can be turned into a test without asking a follow-up question.

---

## 0. One-paragraph summary

Replace the current photo-textured, top-down `ha-floorplan` view with a
**cartoon-style cutaway illustration of the main floor** that is genuinely
interactive: rooms and fixtures are drawn, lights visibly glow, motion pulses,
doors swing, and tapping a room opens a sheet of that room's real devices. It runs
as a **single self-contained Lovelace card** (no build step) in the existing HA
dashboard, on the existing tablet kiosk, reusing the measured room geometry, the
existing SVG render pipeline, the existing WS config writer, and the existing test
suite. Nothing new is installed on the host.

---

## 1. Why a redesign — measured problems with the current plan

| # | Problem | Evidence (today's live state) |
|---|---|---|
| 1 | A bound room's control silently does nothing | `floorplan.yaml` binds `switch.laundry_laundry_relay`, which **404s**. The live entity is `switch.double_relay` ("Laundry relay"). Reported by the user as "doesn't allow light control". |
| 2 | Temperature labels never populate | The rules call `floorplan.text_set`, a **frontend-registered** service. `GET /api/services` shows zero `floorplan.*` services, and the four `<text id="temp_*">` elements still render their literal placeholder. |
| 3 | No validation gate caught either | Nothing in the 533-test suite asserts that a bound entity **exists in HA**. Config writes can be "successful" against a dead entity id. |
| 4 | Visual language is photographic, not illustrated | Seven `rooms_small/*.jpg` textures at 42 % tint over flat fills. Reads as a stylised map, not a "cartoon house". |
| 5 | No affordance for "what can I touch" | Unbound rooms (kitchen, dining, bathroom) are distinguished only by a dashed stroke. |
| 6 | No per-fixture control | Rooms are single tap targets; a room with 4 lights (kitchen) or 7 (foyer) can only toggle one entity. |

---

## 2. What already exists (reuse inventory — all verified 2026-10-22)

### 2.1 Hardware (unchanged, no new spend)

| Item | Spec | Role |
|---|---|---|
| Samsung Galaxy Tab A7 Lite (SM-T220) | 8.7", **800 × 1280** portrait | Primary kiosk. All performance budgets are set against this. |
| HAOS host | HA **2026.10.2**, **587 states**, 17 areas | State source + dashboard host |
| Mosquitto | `100.104.204.118:1883` | Kiosk control (wake/screen), unchanged |
| Node-RED | existing flows | Keeps Home Lab / Network / Kanban tabs; **not** used for the new plan |

### 2.2 Software to reuse as-is

| Asset | Path | Reuse |
|---|---|---|
| Measured room geometry | `floorplan/geometry.py` | Room polygons in cm-space, rectilinear, neighbours share walls. Becomes the extrusion source. |
| SVG render pipeline | `floorplan/render_floorplan.py` | Pattern for "generate asset → upload → cache-bust". Extend, don't fork. |
| WS config writer | `floorplan/repoint_dashboard.py` | Already writes `image.location` + bumps `?v=N` and reads back. Extend to write the new card config. |
| Photo downscaler | `floorplan/downscale_rooms.py` | Reused only if D7 keeps photos. |
| Test suite | `tests/` (533 passing) | Extended, never bypassed. `test_floorplan_assets.py` is the model. |
| HA access | `/root/.hermes/.env` → `HA_URL`, `HA_TOKEN` | REST + WS both proven |
| Theme/palette tokens | repo `css/`, `js/themes.js` | Contrast suite must keep passing |
| Nav + tabs | existing Lovelace views | `/floor-plan` slot is replaced in place |

### 2.3 Live room → entity inventory (measured via `area_entities()`)

This is the data contract's raw material. Counts are real, not estimated.

**study** (HA area `family_room`)

| Kind | Entity | Current |
|---|---|---|
| light (primary) | `light.family_room_family_room` | off |
| switch | `switch.family_room_right`, `switch.family_room_family_room_left` | off, off |
| media | `media_player.family_room_tv` | off |
| motion | `binary_sensor.family_room_family_room_motion_motion` | off |
| temp | `sensor.family_room_family_room_motion_temperature` | 67.46 °F |

**corridor** (HA area `foyer`) — the dense room, 7 lights

| Kind | Entity | Current |
|---|---|---|
| lights | `light.foyer_candelabra_1..3`, `light.foyer_d1..d4` | all off |
| climate | `climate.hallway_hallway` | heat_cool |
| temp / humidity | `sensor.hallway_hallway_temperature` / `_humidity` | 68.92 / 52 |
| motion | `binary_sensor.hallway_motion_motion` | off |
| alarm zones | `zone_1` Front Door, `zone_6` Living Room Motion | off |
| **NEVER BIND** | `switch.siren`, `switch.siren_alarm` | off — a tap would sound the siren |

**living_room** · `light.living_room_ceiling` · `media_player.living_room_speaker`

**kitchen** — 4 controllable, 3 of them lights

| Kind | Entity | Current |
|---|---|---|
| lights | `light.z_wave_plus_s2_dimmer_light_switch` (Kitchen Lights), `light.kitchen_kitchen_table`, `light.dimmer` (Island) | off |
| switch | `switch.on_off_switch` (Cabinet) | off |
| media | `media_player.kitchen_display` | off |
| sensors | `sensor.kitchen_motion_temperature` 64.84, `_illuminance` 0, motion, `binary_sensor.refrigerator_door` | — |

**laundry** — appliances + one relay

| Kind | Entity | Current |
|---|---|---|
| relay | `switch.double_relay` ("Laundry relay"), `switch.double_relay_2` | off |
| appliance power | `switch.washer_power`, `switch.laundry_dryer_power` | off |
| status | `sensor.washer_current_status` `power_off`, `sensor.laundry_dryer_current_status` `power_off` | — |
| door | `binary_sensor.laundry_door_contact` / `_presence` / `_water` | off / **on** / off |
| energy | `sensor.washer_energy_this_month` 256, `sensor.laundry_dryer_energy_this_month` 30915 | — |

**dining_room**, **bathroom** — **zero** entities in HA. They can be drawn but have
nothing to control.

**House-level**

| Kind | Entity | Note |
|---|---|---|
| weather | `weather.forecast_home` (`clear-night`) | now exists — header block is buildable |
| climate | `climate.hallway_hallway` (heat_cool), `climate.master_bedroom_master_bedroom` | 2 only, both heat_cool |
| **alarm** | **no `alarm_control_panel.*` exists** | Only Alarm Panel Pro zones + siren switches. A "mode" must be a helper we create (see D6). |
| unconfigured zones | `zone_7..zone_12` read **on** | These are unused loops. Never render them as faults. |

---

## 3. Goals / non-goals

**Goals**

- G1 The plan reads instantly as an illustrated house, not a map with photos.
- G2 Every drawn thing that looks interactive **is** interactive, and every
  interactive thing writes to HA within 2 s.
- G3 One glance answers: which rooms are lit, where is motion, is a door open,
  what is the alarm state, what is each room's temperature.
- G4 Works on the 800 × 1280 kiosk with no scrolling for the plan itself.
- G5 Iterable: the user reviews rendered screenshots each phase and steers.

**Non-goals (this phase)**

- N1 Cameras / video feeds (deferred: camera entities exist but bandwidth and
  privacy on a kiosk are a separate decision).
- N2 Basement, garage, upstairs floors (data exists; art does not — see D8).
- N3 Replacing the Node-RED tabs (Home Lab, Network, Kanban, System Health).
- N4 Any new host software, container, or build toolchain.
- N5 3D/WebGL. 2.5D SVG only.

---

## 4. Decision register — user input required

Each decision states the options, my recommendation, and what changes downstream.
**Defaults are pre-selected; replying "defaults" authorises all of them.**

### D1 — View style
| Opt | Description | Consequence |
|---|---|---|
| **1a (default)** | **Isometric cutaway**, 2:1 projection, front/south walls omitted so you look into every room | Most "cartoon house" feel. Hit areas are parallelograms in projected space; furniture must be placed per room. |
| 1b | **Top-down cartoon** — same plan orientation as today, thick outlines, flat fills, furniture glyphs | Cheapest, geometry and hit-testing unchanged, reads as a game minimap not a house. |
| 1c | Both, with a toggle | ~1.6× art cost, best of both. |

### D2 — Art source
| Opt | Description | Consequence |
|---|---|---|
| **2a (default)** | **Procedural from `geometry.py` + hand-placed cartoon props.** Walls extruded from the measured polygons; furniture/doors/fixtures as small hand-authored SVG groups | Deterministic, testable, resolution-independent, animatable, and the room outlines are guaranteed correct because they come from measured cm coordinates. |
| 2b | AI-generated illustration + hand-traced hotspot polygons | Fastest "wow", but fixed raster resolution, perspective will not match measured geometry, glow masking is manual, and regenerating art loses hand-tuned hit areas. |
| 2c | Fully hand-drawn SVG in an editor | Highest craft ceiling; slowest; hit areas drift from `geometry.py`. |

### D3 — Renderer
| Opt | Description | Consequence |
|---|---|---|
| **3a (default)** | **Custom LitElement Lovelace card**, one `.js` file, no build step, inline SVG | Full control: per-fixture state, glow, sheets, keyboard. Direct `hass.states` access, so no reliance on frontend-registered services (the `text_set` failure above). ~600–900 lines of JS to own and test. |
| 3b | Keep `ha-floorplan`, restyle the SVG, use `class_set` rules | Least new code, but cannot do per-fixture sheets, and text/state binding is exactly what is broken today. |
| 3c | Node-RED `ui_template` hosting the SVG | Reuses Node-RED deploys, but duplicates the HA state path and drags the plan away from Lovelace. |

### D4 — Room interaction model
| Opt | Description |
|---|---|
| **4a (default)** | Tap a **fixture** (lamp, TV, relay) toggles that entity. Tap a **room floor** opens a bottom sheet (portrait) / right panel (landscape) listing every device in that room with name, state, and toggle. Long-press a room toggles **all lights** in it. |
| 4b | Room tap toggles the room's primary light; fixtures not individually tappable. Simplest, loses per-fixture control. |
| 4c | Always-visible device chips floating in each room. Fastest single tap, clutters the art on a 800 px screen. |

### D5 — Palette
| Opt | Description |
|---|---|
| **5a (default)** | **Cartoon daylight** palette (warm floors, pastel room tints, navy outlines) with an automatic **night variant** after sunset (cooler fills, warm lamp pools). Both from CSS custom properties on the same SVG, so one art asset serves both. |
| 5b | Daylight only — simplest, glares at night on a bedroom-adjacent kiosk. |
| 5c | Dark-only — consistent with the other dashboard tabs, weakest "cartoon" read. |

### D6 — Alarm mode
There is **no `alarm_control_panel`**. Options:
| Opt | Description |
|---|---|
| **6a (default)** | Create an HA **`input_select.house_mode`** helper (`Home` / `Away` / `Night` / `Vacation`). The header chip sets it; the card also shows a live zone summary (Front Door, Kitchen Door, Living Room Motion, Garage ×2) with the unconfigured `zone_7..12` excluded. Modes become usable as automation conditions later. |
| 6b | Zone summary only — display-only, no mode concept. Zero new HA objects, no mode to arm automations against. |
| 6c | Wire a real alarm panel integration first, then build the widget. Blocks the phase. |

### D7 — Keep the room photos?
| Opt | Description |
|---|---|
| **7a (default)** | **Drop them.** Cartoon art replaces photography. `rooms_small/*.jpg` stay in the repo, unreferenced, so nothing breaks if we revert. |
| 7b | Keep as an optional "photo mode" toggle — two visual languages to maintain and test. |

### D8 — Room scope in this phase
| Opt | Description |
|---|---|
| **8a (default)** | The **7 main-floor rooms** in `geometry.py`. Dining and bathroom ship as drawn-but-empty (sheet says "No devices in this room" — truthful, not a dead tap). |
| 8b | Add basement + garage now (84 and 39 entities, no measured geometry — needs a second source map). |
| 8c | Main floor now, basement/garage as a fast-follow phase with their own map trace. |

### D9 — Review cadence
| Opt | Description |
|---|---|
| **9a (default)** | **Rendered review per phase**: I ship each phase, then send you tablet-portrait + desktop screenshots (and a day/night pair in P5) with a numbered change list. Max 5 items per round, re-rendered within the same round. |
| 9b | Single review at the end of all phases — one big feedback dump, more rework risk. |

> **Also worth telling me now (optional, not a formal decision):** if you have a
> cartoon/illustration reference you like, drop a link or image. Absent that, I
> spec the art from §5 below (thick outlines, flat fills, 2.5D, no gradients
> except lamp glow).

---

## 5. Visual specification — "cartoon"

Binding on the coder. Numbers exist so the result can be checked, not admired.

### 5.1 Projection (if D1 = isometric)

Plan coordinates are centimetres from `geometry.py`. Project with a 2:1 isometric:

```
sx = (x - y) * 0.8660
sy = (x + y) * 0.5000 - z * 0.5000        # z = height above floor, cm
```

- Wall height **270 cm**; wall thickness drawn as a **12 cm** top face.
- Front and south walls (the two nearest the viewer) are **omitted** — that is
  what makes it a cutaway rather than a box.
- Everything is generated into one `viewBox` computed from the projected bounds
  plus **24 px** padding. No manual viewBox tuning.

### 5.2 Line and fill language

| Token | Value | Rule |
|---|---|---|
| Outline | `#1B2432`, 3 px at base zoom | Every silhouette gets one. Uniform width — cartoon, not blueprint. |
| Room floor | per-room pastel, 5 hues, max ΔL 12 % between neighbours | Adjacent rooms must never share a hue. |
| Wall top | lighter tint of the wall face (8 % white) | Reads as a lit top edge. |
| Shadow | single soft ellipse per furniture item, `#000` at 12 % | No drop-shadow filters. |
| Corners | `rx = 4` on furniture rects | Rounded = friendly. |
| Texture | none | No grain, no noise, no photo. |

### 5.3 State → visual (single source of truth)

| State | Visual | Must NOT |
|---|---|---|
| Light **off** | fixture outline only, fill = 8 % white | be invisible |
| Light **on** | warm radial gradient pool on the floor (radius ≈ 90 cm), fixture glyph filled `#FFD98A`, room floor warms by one step | use `feGaussianBlur` (perf) |
| Motion detected | 1.2 s pulse: room outline opacity 0.35 → 1 → 0.35, `prefers-reduced-motion` respected | loop forever |
| Door / garage open | door group rotates **-75°** about its hinge over 300 ms, doorway shows a darker gap | animate without a hinge origin |
| Media playing | screen glyph gains a `#7FD1FF` glow rect | imply video |
| Entity **unavailable** | 40 % opacity + a `?` badge in the sheet row | silently show "off" (a dead sensor must not look like an off light) |
| Room with **no devices** | draw normally, no hover lift, sheet shows "No devices in this room" | look tappable-but-dead |

### 5.4 Night variant (if D5 = 5a)

CSS custom properties on the card root; the SVG references them via `var(--fp-…)`.
Sunset trigger is `sun.sun` (`below_horizon`), with a manual override chip.
Two palettes, **one** SVG file. No second asset, no re-upload.

---

## 6. Functional requirements

Format: `FR-n` — requirement — **Acceptance** (testable).

- **FR-1 Live state.** Every bound entity renders its state from `hass.states`,
  updated by HA WS state events, no polling.
  **A:** change a light in HA UI → the plan reflects it ≤ 2 s; JS console clean.
- **FR-2 Entity existence gate.** The card ships an entity map; every id in it
  must exist in HA.
  **A:** `tools/validate_entity_map.py` exits **non-zero** if any mapped id 404s;
  it runs in the test suite. *(This is the check that would have caught the
  laundry bug.)*
- **FR-3 Per-fixture control.** Tap a fixture → `light.toggle` /
  `switch.toggle` / `media_player.media_play_pause` as appropriate.
  **A:** state returns from HA (not optimistically flipped); a failed call shows
  an inline error and reverts the glyph.
- **FR-4 Room sheet.** Tap room floor → sheet with every device in that room.
  **A:** device count in the sheet equals the count in `§2.3` for that room;
  each row toggles its entity; sheet closes on Esc / swipe-down / backdrop.
- **FR-5 Long-press = room master.** Long-press room → toggles all lights in it.
  **A:** on kitchen (3 lights) all three flip; the action is undoable by a second
  long-press.
- **FR-6 Temperature per room.** Rooms with a temperature sensor show it.
  **A:** study, corridor, kitchen show values matching HA within 0.2 °F; rooms
  without a sensor show **nothing** (not `--`, not `0`).
- **FR-7 Alarm chip.** Header shows house mode + a zone summary; a **triggered**
  zone (siren on, or a configured zone opening while mode ≠ Home) turns the chip
  red and pulses once.
  **A:** zones `7..12` never appear; siren state reads correctly; no false
  trigger from an unused loop.
- **FR-8 Climate.** Corridor sheet shows `climate.hallway_hallway` current temp,
  setpoint, and mode buttons **limited to that entity's `hvac_modes`**.
  **A:** rendered mode buttons ⊆ `attributes.hvac_modes`; a mode write is
  confirmed by a returned state change.
- **FR-9 Weather + clock.** Header shows `weather.forecast_home` condition +
  temperature and local time.
  **A:** degrades to a dash if the entity is unavailable; never invents a value.
- **FR-10 Empty rooms are honest.** Dining and bathroom say "No devices in this
  room".
  **A:** no control rendered; no `pointer` cursor on any element inside them.
- **FR-11 No dead affordances.** Every element either controls, navigates, or
  displays — and displays never look interactive.
  **A:** `tests/test_cartoon_interactivity.py` enumerates all SVG elements with a
  handler and asserts each maps to a live entity; any element with
  `cursor:pointer` and no handler fails the test.
- **FR-12 Cache-busting.** Asset URLs carry `?v=N`; the config write is read back.
  **A:** `repoint_dashboard.py` prints `after:` JSON and the served bytes match
  local (md5), as already done for the SVG today.

---

## 7. Performance budget (A7 Lite, 800 × 1280)

| Metric | Budget | How measured |
|---|---|---|
| SVG asset | ≤ 250 kB raw, ≤ 80 kB gzip | `wc -c`, `gzip -9` |
| DOM nodes in card | ≤ 400 | `document.querySelectorAll('*').length` in the card's shadow root |
| Cold render | ≤ 2.0 s to first painted plan on tablet over LAN | `performance.now()` marks, screenshot |
| State update | ≤ 16 ms JS per event | `performance.measure` around the update path |
| Animation | ≥ 30 fps during a motion pulse | DevTools FPS meter, recorded |
| Filters | **zero** `feGaussianBlur` / `feDropShadow` | `grep -c '<feGaussianBlur'` must be 0 |
| Memory | ≤ 80 MB tab RSS after 10 min | tablet browser task manager |

**Banned by budget:** full-SVG re-render on every state event (must be keyed,
per-element attribute updates), any layout thrash in a loop, any animated `d`
attribute on a path (animate `transform`/`opacity` only).

---

## 8. Accessibility

- Text contrast ≥ **4.5:1** against whatever it sits on, in **both** day and night
  palettes; the existing contrast suite is extended, not replaced.
- Hit targets ≥ **44 × 44 px** measured on rendered boxes (this repo has been
  bitten twice by rules matching zero elements — measure, don't declare).
- Keyboard: every room and fixture is focusable in reading order; Enter opens the
  sheet / toggles; Esc closes; focus ring visible at 3:1.
- `aria-label` on every interactive group: e.g. `"Kitchen, 3 lights, 1 on"`.
- `prefers-reduced-motion` disables pulses and door swings (state still shown).
- Colour is never the only channel: lit fixtures also change shape/fill, not just
  hue.

---

## 9. Architecture and file layout

```
floorplan/cartoon/
  geometry_iso.py        # 3D→2D projection of geometry.ROOMS + wall extrusion
  fixtures.json          # per-room furniture/fixture placements in PLAN cm coords
  palette.json           # day + night tokens (single source for CSS vars)
  entity_map.json        # room → entity ids (validated against HA)
  render_cartoon.py      # emits floorplan_cartoon.svg (self-contained: CSS inlined)
  floorplan_cartoon.svg  # build output, uploaded to /config/www/floorplan/
www/
  floorplan-cartoon-card.js   # LitElement card, no build step, ~600–900 LOC
tools/
  validate_entity_map.py      # FR-2 gate, exits non-zero on a missing entity
tests/
  test_cartoon_geometry.py    # projection, bounds, non-overlap, rectilinearity
  test_cartoon_assets.py      # size budget, no blur filters, ids present, cache-bust
  test_cartoon_entity_map.py  # every id resolves (needs HA creds; skipped if unset)
  test_cartoon_interactivity.py
```

**Rules carried over from hard-won lessons (do not re-learn these):**

1. **One uploadable asset.** CSS is inlined into the SVG; never ship a second file
   the user must remember to upload.
2. **Never rename an asset to bust cache** — bump `?v=N` instead.
3. **`ha-floorplan`'s `class_set` replaces the class attribute**, which is why the
   old CSS is ID-scoped. If D3 = 3b, keep that discipline; if 3a, moot.
4. **No `<image>` inside a CSS comment** — it truncates the stylesheet when the SVG
   is parsed as HTML.
5. **Never bind the foyer siren switches** to any tap target.
6. **Pass-through assets are copied, not re-encoded** (a lossy round-trip made the
   room photos irreproducible — see `floorplan/README.md`).
7. Assert on the **rendered** box, not on the CSS rule.

---

## 10. Phases with gates that can fail

Each phase ships independently. A phase is done only when its gate passes **on the
tablet**, not just in a browser.

### P0 — Data contract and validation (no visuals)
Write `entity_map.json` from §2.3, `tools/validate_entity_map.py`, and the test
that runs it.
**Gate:** validator exits non-zero on a deliberately broken id; with the real map
it exits 0; **the laundry id is corrected to `switch.double_relay`**; suite green.

### P1 — Cartoon art, static
`geometry_iso.py`, `fixtures.json`, `render_cartoon.py` → one SVG, no interaction.
**Gate:** 7 room polygons present with stable ids · file ≤ 250 kB · zero blur
filters · viewBox == projected bounds + 24 px · screenshot reviewed by the user ·
renders in ≤ 2 s on the tablet.

### P2 — Live state
Card renders the SVG and binds lights, motion, doors, media, temps.
**Gate:** toggling from the card changes HA ≤ 2 s · all 7 rooms match HA state
simultaneously · no console errors · state update ≤ 16 ms.

### P3 — Interaction
Fixture taps, room sheet, long-press master, empty-room honesty.
**Gate:** every row in every sheet toggles its entity · 44 px targets measured ·
keyboard traversal reaches all rooms/fixtures · zero dead affordances (FR-11).

### P4 — House status
Alarm chip + `input_select.house_mode` (if D6 = 6a), climate in the corridor
sheet, weather + clock header.
**Gate:** `zone_7..12` never rendered · mode write persists across reload ·
`hvac_modes` respected · no false alarm state with the siren off.

### P5 — Polish and animation
Glow pools, motion pulse, door swings, media glow, day/night palettes.
**Gate:** ≥ 30 fps measured · contrast suite passes in **both** palettes ·
reduced-motion path verified · no layout shift (CLS ~0) on the tablet.

### P6 — Iteration to "useful and user-friendly"
Three review rounds, D9 cadence. Each round: I send screenshots (tablet portrait,
desktop, day + night, plus one "3 lights on / motion active" state), you reply with
a numbered list, I re-render.
**Gate:** your explicit sign-off against this checklist —
(a) I can find and toggle any light in ≤ 2 taps; (b) the plan reads as a cartoon
house at arm's length; (c) the tablet shows it without scrolling; (d) nothing looks
tappable that isn't; (e) I would use this instead of the HA app.

---

## 11. Iteration protocol (how we converge)

- One numbered feedback list per round, **max 5 items**, ordered by pain.
- Every item gets one of three responses before the next round: *done*, *rejected
  with a reason*, or *deferred to phase N with a card*. No silent drops.
- Visual changes come with a screenshot in the reply — never "it should look
  right now".
- Anything that changes a stated number (palette, budget, geometry) updates this
  document in the same commit, so the spec never drifts from the code.

---

## 12. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Isometric art looks amateurish | Whole premise fails | P1 is a cheap static prototype reviewed before any JS is written |
| Tablet SVG performance | Jank, unusable kiosk | Budget in §7; glow via gradients not filters; animation limited to transform/opacity |
| Scope creep into other floors | Phase never lands | D8 decision; main floor only in this phase |
| Entity ids drift (renames in HA) | Silent dead taps — the bug we already have | FR-2 validator in CI |
| Card JS unmaintained | Future breakage | One file, no build step, ~600–900 LOC, tested via Playwright harness already in `tools/` |
| Two visual languages (old plan still linked) | Confusion | Replace `/floor-plan` in place; no parallel route shipped |

---

## 13. Handoff checklist for the coder

1. Read §4 decisions (user answers) → record them in this file's header.
2. Read `floorplan/geometry.py` docstring — the coordinates are measured, do not
   "tidy" them.
3. Build P0 first and make the validator **fail** on purpose before making it pass.
4. Generate, never hand-draw, anything derivable from geometry.
5. Every commit: tests green, `?v=N` bumped, config read back after write.
6. Report per phase: what changed, the gate numbers measured, what you could not
   verify and why. "Green save" is not verification.
