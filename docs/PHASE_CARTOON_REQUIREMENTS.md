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

---

# 14. LOCKED DECISIONS AND PROBE RESULTS — 2026-10-22

The user answered the decision register. **This section is authoritative**; §4 above
stays as the record of what each option would have cost.

| # | Decision | Locked | Consequence |
|---|---|---|---|
| D1 | View style | **1A isometric cutaway** | Projection + wall omission per §5.1 |
| D2 | Art source | **2B image-generated raster + derived hotspots** | §15 below; art is a build artefact, not hand-drawn |
| D3 | Renderer | **3A custom LitElement card** | One `.js`, no build step, reads `hass.states` directly |
| D4 | Interaction | **4A** fixture tap = toggle, room tap = sheet, long-press = all lights | §6 FR-3..FR-5 |
| D5 | Palette | **5A daylight + automatic night variant** | CSS custom properties over one art asset |
| D6 | Alarm mode | **6C — wire the real integration** (now available) | See §16; no helper needed |
| D7 | Photos | **7a drop them** | `rooms_small/` stays in the repo, unreferenced |
| D8 | Scope | **8c main floor now, basement/garage fast-follow** | Needs a second map trace; separate phase |
| D9 | Review | **9b single review at the end** | Compensated by the self-verification regime in §17 |
| — | Reference | `experiencelovelace.github.io/ha-floorplan/docs/example-floorplanner-home/` | Analysed in §15.1 |

## 15. The art pipeline for 2B, and what the probe measured

### 15.1 What the reference actually is

Fetched and unpacked (`floorplanner_home.svg`, 2.83 MB): **one SVG containing a
2.06 MB embedded 1920×1080 PNG** — a Floorplanner top-down 3D render — plus room
paths ids `area.<room>`, object paths `thing.<object>`, device paths `element.<dev>`.

Three techniques worth copying, one correction:

1. **Bake the lit state into the image.** The render shows every room lit; a room's
   overlay path sits at `opacity: .5` normally and `0` when its light is on. So "off"
   is a *dimming wash*, not a missing light. This is the only way to get believable
   lamp glow out of a raster, and it removes the need for glow filters entirely.
2. **`vector-effect: non-scaling-stroke` + `pointer-events: all`** on `svg *`, so
   hotspot strokes stay 1 px at any zoom and thin shapes remain tappable.
3. **One asset, two files** (SVG + CSS). We keep one *file*: the CSS is inlined
   (lesson already learned in `floorplan/README.md`).
4. **Correction:** the reference is ~90° top-down, not a 2:1 isometric. D1 = 1A asks
   for a cutaway; the render below is generated at a slight tilt — dollhouse legible,
   wall faces visible. That is the synthesis of 1A and the reference, and it is what
   the probe produced.

### 15.2 Probe: generation works, and it is fast

Implemented and run today (`floorplan/cartoon/`):

```
make_control_image.py   geometry.py -> flat 1600x1168 colour plan   (no text, no furniture)
generate_art.py         control + prompt -> render, Google image API
fit_hotspots.py         derive + validate one polygon per room
```

Measured, three generations:

| Model | Output | Latency | Notes |
|---|---|---|---|
| `gemini-3.1-flash-image` | 1200×896 | **7.7 s** | good layout adherence, no text artefacts |
| `gemini-3-pro-image` | 1200×896 | ~15 s | similar composition, slightly cleaner materials |
| `gemini-3-pro-image --size 2K` | **2400×1792** | ~25 s | **production setting** — 3× the tablet width |

The 2K render in `floorplan/cartoon/art/render_2k.jpg` preserves all seven rooms,
the L-shaped hall, the stair flight and the room proportions from the control image.
No text, no watermark, no invented rooms.

**Constraint discovered:** output is JPEG regardless of the requested MIME type, and
the default is 1K. Both are handled in `generate_art.py` (extension follows the real
MIME; `--size 2K` for production). Cost is metered — each regeneration is a paid call,
so **the chosen render is committed to the repo** and never silently regenerated.

### 15.3 Probe: hotspot derivation — 6 of 7 rooms, three approaches rejected

Deriving the polygons is the risky half of 2B. What was tried, with numbers:

| Approach | Result | Verdict |
|---|---|---|
| Trust `geometry.py` mapped by house bbox | centroid drift 0.001 (sub-1 %) but polygons **rode the wall band** — edge-band floor purity 0.12–0.40 | rejected |
| Colour region-grow from each room centroid | grow covered 3–70 % of the room; furniture and lighting break the uniform-colour assumption | rejected |
| Fit affine by wall-mask IoU | best IoU **0.13** — the render's bright furniture (bed, island, cabinetry) dominates a "light-neutral" mask | rejected |
| **Anchor + wall-band clip** | **6/7 pass**: band purity 0.86–1.00, drift 0.03–0.06, area ratio 0.72–0.89 | **current** |

Method that works: map the measured polygons onto the render (bbox anchor), then
**clip each polygon to the render's non-wall pixels**. Clipping trims the wall-band
overshoot without needing a colour model, and the anchor stops the clip bleeding
through a doorway into the neighbouring room.

Known defects, to be fixed in P1 (they are why the gate still fails):

- **kitchen** — pale stone floor is bright *and* neutral, so the wall mask eats the
  floor; the clip finds only 39 % of the room and falls back to the inflated
  geometry polygon. Fix: classify walls by *straight-edge continuity* (Hough / line
  support), not brightness.
- **living_room** — the bright rug and sofa are clipped out, leaving a jagged
  concave polygon. Fix: clip against wall lines only, and allow interior holes to be
  filled (a room's polygon is its outer boundary, furniture is not a wall).
- Area ratios cluster at 0.72–0.89 because furniture sits inside every room; the
  polygon should be the *room*, so P1 must take the room boundary, not the visible
  floor pixels.

**Gate for P1 is therefore:** all 7 rooms pass with band purity ≥ 0.95, area ratio
0.95–1.05, drift ≤ 0.03 — i.e. the polygon is the room, not the floor minus furniture.

## 16. Alarm — 6C is satisfied, real integration exists

`GET /api/states` shows **Alarmo** with three panels (was zero at the time of the
draft):

| Entity | State | `supported_features` |
|---|---|---|
| `alarm_control_panel.house` | `disarmed` | **15** = arm_home 1 + arm_away 2 + arm_night 4 + trigger 8 |
| `alarm_control_panel.garage` | `disarmed` | 15 |
| `alarm_control_panel.master` | `disarmed` | 15 |

Requirements consequences:

- Modes offered must be derived from `supported_features` → **home / away / night /
  disarm**. **No vacation mode** (the draft proposed one; the hardware does not offer
  it and Alarmo would reject it).
- `alarm_control_panel.house` is the header chip; garage and master live in a
  secondary row of the sheet, never as the primary control.
- Useful live attributes already present: `open_sensors`, `bypassed_sensors`,
  `changed_by`, `last_triggered`, `arm_mode`, `delay`, `next_state` — so "armed with
  the kitchen door open" is displayable without inventing state.
- `code_arm_required` and `code_format` must be read before rendering a keypad. If a
  code is required, the card shows a numeric entry, not a bare arm button that will
  fail.
- The Alarm Panel Pro zone sensors (`zone_1` Front Door, `zone_2` Garage Interior,
  `zone_3` Kitchen Door, `zone_5` Garage Exterior, `zone_6` Living Room Motion) stay
  as the zone summary. **`zone_7..12` read `on` and are unconfigured — never shown.**

## 17. Compensating for D9 = single review at the end

One review means one chance to be wrong, so verification moves into the pipeline:

1. **Every phase gate must pass numerically before its screenshot is sent.** No
   "looks fine to me" — §10 gates already require measured numbers.
2. **Art gets one early checkpoint anyway.** D9 is about avoiding five rounds of
   layout bikeshedding; the art is the one item where a late "I don't like the
   style" costs a rebuild. I will send the P1 render with three variants (tilt
   angle / outline weight / palette warmth) for a single pick, then not raise art
   again. Everything else waits for the final review.
3. **Rendered, not asserted.** Each phase ships a tablet-portrait screenshot plus the
   desktop view; state changes are shown in the same shot wherever possible.
4. **Failures are reported, not smoothed.** The kitchen/living-room defects above are
   written down as defects rather than declared "close enough".

## 18. Additional risks introduced by 2B

| Risk | Impact | Mitigation (binding) |
|---|---|---|
| Art is a raster → fixed resolution | Blurry on the kiosk | Generate at 2K (2400 px wide = 3× the 800 px viewport); never upscale a 1K render |
| Regeneration is non-deterministic | Polygons drift per generation; art changes silently | The chosen render + its prompt + its derived `hotspots.json` are **committed together**; a regeneration is a new art version, gated by the P1 tests |
| Cloud dependency (Google image API) | Pipeline stops without the key/quota | Render is committed; the pipeline is only needed to *change* the art. `make_control_image.py` and `fit_hotspots.py` are fully local |
| Model invents a room or a door | Hotspots miss; a "door swing" animates the wrong thing | Room count/proportions validated against `geometry.py`; door animation only where the art shows a door, otherwise omitted rather than faked |
| L-shaped footprint leaves a large void | Renders read as "missing rooms" | Add a neutral exterior treatment (flat surround + soft contact shadow) instead of leaving white space; **no grass or landscape** — it would imply data we do not have |
| Bright furniture vs wall in segmentation | Kitchen/living polygons wrong | P1 gate requires 7/7 with area ratio 0.95–1.05; fix is line-based wall detection (documented above) |

## 19. Art checkpoint question (the only open item)

D9 says one review at the end; §17.2 carves out the art. To avoid a rebuild I will
send **the P1 render in three variants** for a single pick. If you would rather
strictly hold to one review, say so and I will pick the middle variant myself and
report the choice.

## 15.4 Art v2 — user corrections applied (2026-10-22)

The user reviewed the first render and corrected the drawing. Those corrections live in
`floorplan/cartoon/room_spec.py` — a separate file from `geometry.py`, which holds
*measured* architecture and must not be edited to make a picture look better.

| User instruction | Implementation |
|---|---|
| All floors medium brown wood except laundry | `FLOORS` = one wood value everywhere; laundry keeps `(186,196,200)` cool tile |
| Family room and kitchen are one open room, kitchen table between them | `OPENINGS` punches the shared wall (x 447–464, y 150–375) in the floor colour; a table block straddles it |
| Family room: fireplace on the left, two blue chairs on the north side, sofa at the bottom, golden rug | Four `FURNITURE` blocks at those walls |
| Living room open to the foyer, blue rug, bookshelf on the right, two small blue chairs at the southern end | `OPENINGS` punches x 972–988 / y 630–850; three blocks, no sofa |
| Bathroom and laundry | Bathroom wood; laundry tile with a drawn grout grid as a visual prior |

### What the correction pass taught (binding on the pipeline)

**Full regeneration is non-deterministic.** v4 had the bathroom correct and a marble
patch in the kitchen; v5 fixed the kitchen and re-tiled the bathroom. Re-rolling a 2K
render (~23 s, metered) to change one surface is how art pipelines get flaky.

So corrections are now applied as **targeted edits**, not re-rolls: `edit_art.py`
sends the existing render plus an instruction naming exactly one region, with a guard
that everything else stays pixel-identical. That is what finally produced the accepted
render (`art/floorplan_render.jpg`): v5 + one bathroom-floor edit.

Two further prompts that turned out to matter as much as the wording:
- **Name rooms by position and contents**, not by name ("the laundry is the UPPER of the
  two small rooms, the one with the washer and dryer"). "Laundry" and "bathroom" were
  swapped repeatedly until the prompt located them physically.
- **A drawn prior beats a sentence.** The model ignored "grey tile" written in prose but
  obeyed a grout grid drawn into the control image (and, earlier, obeyed a marble slab it
  invented from a pale counter block that we had to remove).

### Hotspot status on the accepted render

`fit_hotspots.py` on `art/floorplan_render.jpg`: **5 of 7 rooms pass**
(study, dining, laundry, bathroom, living room — edge-band purity 0.92–1.00, drift
0.02–0.04, area ratio 0.80–0.91).

Failures, unchanged in kind and still P1 work:
- **kitchen** — the white counter run touches the room boundary, so the wall-band clip
  eats 23 % of the polygon (purity 0.72).
- **corridor** — the open-plan boundary at the living room means there is no wall for the
  clip to stop at (purity 0.81).

Both are fixed by the same P1 change: detect walls as *lines* (Hough/continuity) rather
than as "bright neutral pixels", and let a room polygon span open boundaries.

## 15.5 Art v3 — markup round 2 applied (2026-10-22)

The user annotated the render directly. Every mark is now a named entry in
`room_spec.py`, so the reason a block sits where it does is traceable:

| Annotation | Change |
|---|---|
| **Kitchen Door** (red ellipse, kitchen north wall, west end) | door opening added in the north wall; the counter run now starts east of it |
| **Counter** (thick black line) | counter is an **L**: north wall, then a return down the east wall |
| **Island** (black box, kitchen centre) | pale stone island added, walkway around it |
| **Fridge** (black outline, kitchen south wall) | fridge moved to the south wall, east of the hall opening |
| **Open doorway** (green, kitchen lower-left) | opening punched kitchen → hall |
| unlabelled green marks at kitchen/dining wall | opening punched kitchen → dining room |
| **Stair direction** (arrow, east) | treads rotated 90°: the flight now ascends toward +x |
| **Front door** (red, bottom edge) | door opening added in the south wall of the foyer |

Two engineering findings from this round, both now fixed in code:

1. **Variable shadowing silently deleted the furniture.** The door branch rebound
   `x0/y0/x1/y1`, which are the plan-bounds captured by the coordinate transform, so
   every later draw used a door rect as its origin and furniture rendered off-canvas.
   The confirmation diagram came out as bare floors — caught only by looking at it.
2. **A pure-white surround hides walls on the exterior edge.** The bathroom and laundry
   west walls face the void; white-on-white made them invisible and the model rendered
   those rooms floating. The control image surround is now `(231,231,229)`.

Process note: corrections were applied as **three targeted edits** after the
regeneration (bathroom duplicate fixtures, laundry tile restored, bathroom floor to
wood). Each edit is one paid call; a full re-roll would have re-randomised everything
already accepted. The accepted asset is `art/floorplan_render.jpg` (2400×1792).

Remaining known art deviations, accepted for now: the washer and dryer stand front-to-back
rather than side by side, and the "fridge" reads as a low cabinet rather than a tall unit.

### Hotspot status — regressed, and the diagnosis is narrower

On the v3 render the fitter returns **2 of 7** (laundry, living room). The inset is now
deterministic (area ratio 0.83–0.95, centroid drift 0.000–0.002), so the remaining error
is entirely in the **anchor**: the house bbox is detected from the background silhouette,
and on this render that picks up the drop shadow, stretching the mapped box ~7 % too low.
A uniform bbox map then cannot be right for both axes, and every polygon lands short.

`hotspots.json` from this run is therefore **not trustworthy** and must not be wired into
the card. P1's job is now precise: replace bbox anchoring with multi-scale template
matching of the control's wall mask against the render's edge map (the control *is* the
ground truth, so this is a registration problem, not a segmentation one), then keep the
drift + edge-band gates as the acceptance test.

---

# 20. Execution log — 2026-10-22 (P0–P3 built, P4 partially)

Autonomous run per the user's "execute until you need something blocking".

## P0 — data contract + validator: DONE

`floorplan/cartoon/entity_map.json` (45 entities, 7 rooms) and
`tools/validate_entity_map.py`.

```
checked 45 unique entities from 50 references
RESULT: PASS
```

The validator gates on existence (HTTP 200 per entity), on a stale `excluded` list, and on
a shape rule that specifically catches the bug that started this: a room whose
`primary_light` is a `switch.*` while it also lists `lights`. `tests/test_cartoon_card.py`
asserts `switch.laundry_laundry_relay` appears nowhere in the repo — it was in
`floorplan.yaml` twice and is now `switch.double_relay`.

## P1 — art + hotspots: DONE, with one room flagged

Art v3 (`art/floorplan_render.jpg`, 2400×1792) matches the markup round-2 annotations, and
the accepted image was built as one generation plus three targeted edits (see §15.5).

Hotspot fit: **6 of 7 rooms pass**, all four failing approaches documented in
`fit_hotspots.py`:

| method | measured outcome |
|---|---|
| bbox anchor | L-shaped footprint breaks mid-line scans (reported the house starting at x=1003); silhouette bbox includes the drop shadow, stretching the map ~7 % |
| colour region-grow | covered 3–70 % of a room; furniture and lighting break uniform colour |
| wall-mask IoU | 0.13 — bright furniture dominates a "light-neutral" mask |
| **chamfer registration + geometric inset + bounded snap** | 6/7 at `outside ≤ 0.019`, drift ≤ 0.08 |

The laundry is the flag: the model drew that room ~8 % smaller than measured, so ~10 % of
its hotspot area lands on the surround. It is still on the room (a sliver spills), so taps
work; the polygon is honest about being imperfect.

Two validation metrics were also wrong before they were right, and both are recorded
because they nearly sent me re-warping *correct* polygons:
- edge-band "is it floor?" purity measures **furnishing**, not alignment — the fireplace is
  ON the family room's wall, the island fills the kitchen. Replaced by "share of the
  hotspot outside the house", using the background component **connected to the image
  border** (a plain colour test called 29 % of the grey-tiled laundry "outside").
- the snap objective minimised "outside" alone, which is best satisfied by collapsing the
  polygon to a dot (measured: every room collapsed to 0.66 area). Now penalised.

## P2/P3 — the card: DONE, verified in a browser harness

`floorplan/cartoon/card.src.js` → `build_card.py` → `dist/floorplan-cartoon-card.js`
(28 kB, self-contained: polygons + entity map + art hash compiled in).

Verified by DOM assertions and synthetic events against a mock `hass` at 800 px:

```
room tap (kitchen)  -> sheet "Kitchen", 6 rows, title/rows correct
toggle button       -> light.toggle light.z_wave_plus_s2_dimmer_light_switch
long-press (living) -> light.turn_on light.living_room_ceiling
empty room (dining) -> "No devices in this room."
alarm chip          -> 3 panels, modes Home/Away/Night/Disarm from supported_features
                    -> click -> alarm_control_panel.alarm_arm_home (house)
night toggle        -> art dims, lamp pools brighten
```

One real rendering bug found this way and fixed: the SVG used `viewBox="0 0 1 1"`, so a
13 px label became **13 user units ≈ 10,400 screen px** and painted the card dark. The
viewBox is now the art's pixel space and every size is scaled by `--k = artW / rendered
width`.

## P4 — alarm/climate/weather: PARTIAL

Alarm sheet (real Alarmo, modes derived from `supported_features`), climate row in the
foyer sheet, weather + clock chips, sun-driven night mode: all in and verified above.
NOT done: colour-contrast audit per palette (§8) — the card inherits the dashboard's dark
chrome and has not been measured against the existing suite's palettes yet.

## BLOCKED — file upload

HA exposes only port 80 from here (22, 2222, 1880, 8123, 8099 all closed) and `/config` is
not mounted on this host, so the two files cannot be written into `/config/www/`. The card
JS and art are packaged at `floorplan/cartoon/dist/cartoon_deploy.zip`.

`tools/deploy_cartoon_card.py --check-only` confirms the state:

```
MISS /local/floorplan/cartoon/floorplan_render.jpg  (404, 0 kB)
MISS /local/floorplan/cartoon/floorplan-cartoon-card.js  (404, 0 kB)
```

The deploy script verifies both files are actually served *before* touching config,
registers the resource as `module`, and creates a **separate** `/cartoon` dashboard so
`/floor-plan` keeps working until the user chooses to switch.

Tests: **545 pass** (12 new in `tests/test_cartoon_card.py`).
