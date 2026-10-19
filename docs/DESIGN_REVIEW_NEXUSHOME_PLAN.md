# Design Review & Redesign Plan — "NexusHome" smart-home dashboard

**Reference:** <https://www.behance.net/gallery/207956087/Smart-Home-Dashboard-Design>
Raju Ahmed & Sadia Afrin, published 2024-09-15 · 313 appreciations
**Reviewed:** 2026-10-19 · images cached in `docs/reference/behance_*.jpg`
**Scope:** visual language + information architecture for our existing
node-red-dashboard, not a rebuild.

---

## 1. What the reference actually specifies

The fourth board is the author's design-system page, so these are the designer's
own numbers — not my estimates off a screenshot.

### Typography — Roboto Flex

| Role | Size / line-height | Weight |
|---|---|---|
| h1 | 32 / 42 pt | Bold |
| h2 | 28 / 32 pt | Bold |
| h3 | 22 / 24 pt | Bold |
| h4 | 22 / 14 pt | Semibold |

Body and labels sit below that: ~15–16 px regular for copy, ~12–13 px with
letter-spacing for micro-labels ("Fan Level", "12 AM", table headers). Numbers
are the loudest thing on the screen — the weather figure is ~64 px bold.

### Palette (exact, from the spec board)

| Token | Hex | Role in the design |
|---|---|---|
| Coral | `#FA6F63` | **Primary accent**: active nav pill, chart stroke, toggles-ON, highlighted tile |
| Navy | `#243A54` | Card surface (elevated above page) |
| Teal | `#009CB0` | Semantic: appliances |
| Blue | `#0083EC` | Semantic: AV / climate units |
| Page | ~`#0B1420` → `#0E1A26` | Near-black blue, subtle vertical gradient |
| Text | `#FFFFFF` / ~`#9FB0C6` | Headings / muted secondary |

Note the discipline: **one** accent (coral) for interaction, and the other three
colours are *semantic*, assigned per device class. Nothing is coloured decoratively.

### Layout

Three columns on a ~1600 px canvas:

```
┌──────────┬─────────────────────────┬──────────────┐
│ rail     │ main (2 sub-columns)    │ control      │
│ ~200 px  │ hero / weather / media  │ thermostat   │
│          │ chart                   │ My Devices   │
└──────────┴─────────────────────────┴──────────────┘
```

- Rail: logo, avatar + "Good day, Amanda Jennifer", nav list. Active item is a
  **solid coral pill** (~12 px radius). Two items carry chevrons (expandable groups).
- Cards: **16–20 px radius, flat** — no drop shadow, just a 1 px
  `rgba(255,255,255,.06)` border, and generous 16–20 px internal padding.
- Gutters ~16 px. Density is low-to-medium: lots of air inside cards, tight
  gutters between them.

### Components worth stealing

1. **Greeting header** — h2 "Hello Jennifer", 2 lines of muted copy, then small
   icon pills for weather and clock/date.
2. **Device tile grid** — the strongest idea on the board. Each device is a
   solid-colour tile: white line icon top-left, `ON`/`OFF` + switch top-right,
   name bottom-left. Colour = device class. 2 columns × 3 rows.

   > ⚠️ **The reference's own tile contrast fails WCAG AA.** Measured white on
   > each tile fill: coral `#FA6F63` = **2.79:1**, teal `#009CB0` = **3.29:1**,
   > blue `#0083EC` = **3.85:1** — all below 4.5:1 for normal text. This is a
   > Behance mockup, not a shipped product, so it was never tested. We take the
   > *pattern* (colour by device class, icon + state + name, one tap) but not the
   > literal fill: tiles will use a tinted surface (device colour at ~14 % alpha
   > over the card navy) with the colour carried by the **icon**, and white text
   > on the navy surface. That keeps the visual grouping and passes AA.
   >
   > Verified for **14 % alpha over `#1F2B47`**: white text lands at **11.6:1**
   > (light), **11.6:1** (switch), **12.0:1** (media) — comfortable AA. The
   > coloured icon against its own tint is **4.14 / 3.53 / 3.11:1**, all above
   > the 3:1 non-text floor (WCAG 1.4.11). Higher alphas make the tint prettier
   > but push the blue icon under 3:1 (2.86:1 at 20 %), so 14 % is the ceiling,
   > not an arbitrary pick.
3. **Thermostat dial** — circular, tick marks around the rim, centre readout
   with the setpoint and a flame icon; flanked by a stat trio and a mini bar chart.
4. **Area chart** — smooth coral stroke, gradient fill fading to transparent,
   dotted vertical guides with circular markers, Y axis 0–100 % in 25 % steps.
5. **Media card** — 44 px album art, title/artist stack, coral progress rail with
   a knob, circular play buttons.
6. **Hero image card** — 16:10 photo, bottom gradient scrim, overlay title, coral
   circular FAB bottom-right.
7. **Weather block** — oversized numeral + condition icon, location line, five
   hourly chips with the current hour filled coral.

---

## 2. Gap analysis — ours vs the reference

| Area | Current (`smart-home-dashboard`) | Reference | Verdict |
|---|---|---|---|
| Accent | Indigo `#7c95f0` (after the a11y fix) | Coral `#FA6F63` | **Change** — brand-level |
| Cards | Material `md-card` default elevation | Flat, bordered, 16–20 px radius | **Change** |
| Page bg | `#1a1a2e` flat | Near-black gradient `#0B1420→#0E1A26` | **Change** |
| Type scale | Ad-hoc sizes, dashboard default font | Roboto Flex, 4-step scale | **Change** |
| Nav | Material icons, no active treatment | Coral pill active state | **Change** |
| **Device control** | **Table, 96 rows, one "Turn on" button per row** | Colour-coded tile grid | **Biggest win — replace** |
| Greeting/header | None | Greeting + muted copy + status pills | **Add** |
| Charts | Donut gauges + a line chart + **Grafana iframes** | Area chart with gradient | **Partial** |
| Semantic colour | None — everything one accent | Colour per device class | **Add** |
| Hero card | None | Photo + scrim + FAB | **Substitute** (no camera) |
| Weather | None | Large numeral + hourly chips | **Gated** |
| Thermostat | None | Circular dial | **Gated** |
| Energy chart | None | "Power Consumed" | **Substitute** |

### The headline problem this redesign should fix

The HA tab renders **96 rows in a table**, each with a single "Turn on/Turn off"
button. On an 800 px-wide A7 Lite that is several screens of scrolling to reach
one light, and the table gives no sense of what is currently on. The reference's
tile grid solves exactly this: scan-ability first, one tap to toggle, state
visible without reading.

---

## 3. Constraints that decide what is copyable

Measured against the live deployment, not assumed:

1. **No climate entities.** HA has 96 controllable entities and **zero**
   `climate.*`. The thermostat dial has **no data source**.
2. **No energy/power sensors.** No `sensor.*` with W/kWh. "Power Consumed" and
   "Top Consumer" have **no data source** either.
3. **No weather entity.** The weather block is also gated.
4. **Device inventory is lights, switches, media players, covers, locks:**

   | Domain | Count | Reference colour mapping |
   |---|---|---|
   | `switch` | 47 | Teal `#009CB0` |
   | `light` | 29 | Coral `#FA6F63` |
   | `media_player` | 16 | Blue `#0083EC` |
   | `cover` (garage doors) | 2 | Navy `#243A54` |
   | `lock` | 2 | Amber (new token) |

5. **node-red-dashboard 3.6.6 layout is a 6-unit grid per group.** Arbitrary
   asymmetric three-column composition is not achievable with `ui_group` alone —
   the reference layout is approximated with per-tab groups plus a
   `ui_template` that owns its own CSS grid.
6. **Icon set is Material, and unknown names silently render a "?" glyph**
   (measured — see `tests/test_nav_icons.py`). Custom iconography needs inline
   SVG in a `ui_template`.
7. **Grafana iframes are cross-origin and cannot be restyled.** They will always
   look like a foreign body inside a coral/flat design. Either wrap-and-accept,
   or replace with native chartjs fed from Prometheus.
8. **Accessibility gates already exist and must keep passing**: WCAG AA 4.5:1 on
   text, 44 px touch targets, the 3-palette contrast suite.

> **Rule for this project:** do not build a widget around a data source we do not
> **Rule for this project (revised 2026-10-19):** a widget may not *pretend*.
> Where we lack a data source we either omit the widget, or build it on an
> explicitly-labelled placeholder (see §4a). What is never acceptable is a
> plausible-looking number that reads as measured fact.

---

## 4a. Interaction contract — "fully interactive" (requirement, 2026-10-19)

The dashboard must be **fully interactive**. Made testable, that means every
element on every tab falls into exactly one of three classes, and the class is
verifiable by clicking it:

| Class | Requirement |
|---|---|
| **Controls** | Do the real thing. A toggle writes to HA and the widget reflects the returned state within 2 s. If it cannot, it is not a control — remove it. |
| **Navigation** | Move the view with no page reload (hash routing, already proven). |
| **Display** | Never look interactive. No pointer cursor, no hover lift, no button chrome. |

Concretely, per surface:

- **Tiles** toggle the device; the tile state follows the HA event, not an
  optimistic local flip (a flip that silently fails is worse than a spinner).
- **Thermostat** dial is draggable *and* keyboard-adjustable (arrow keys), with
  a numeric readout. It writes a setpoint somewhere real (see placeholder policy).
- **Charts** respond to a click/drag: hover shows the exact value at that point,
  and a time-range selector (24 h / 7 d) actually re-queries.
- **Search / filter** narrow the tile grid live as you type, and a "no matches"
  state appears instead of an empty grid.
- **Media card** play/pause acts on the actual player; if the player is off the
  control is disabled, not a dead button that appears to work.
- **Every button has a pressed state** and a >= 44x44 px hit area (measured, not
  declared — this repo has been bitten twice by rules that match zero elements).
- **Keyboard**: Tab reaches every control, Enter/Space activates, focus is
  visible. The kiosk tablet is touch-first, but the browser view is not.
- **No dead ends**: a failed action surfaces a message. Silence after a tap is a
  bug, not a UI style.

**Global acceptance (applies to every phase):** an interactivity audit walks all
seven tabs and records, per element, which of the three classes it claims and
whether the claim holds. Any element that claims "control" but does nothing is a
release blocker.

---

## 4b. Placeholder policy for thermostat + energy

**Decision (user, 2026-10-19):** build the thermostat and energy widgets now on
placeholder data; the real HA entities will be added later.

Placeholders are allowed on these terms:

1. **Marked in code, not on screen.** *(Revised 2026-10-19 at the user's
   request: no visible demo tag.)* Each placeholder carries `data-demo="true"`
   on its container plus a comment naming the entity that will replace it, so the
   provenance is greppable and reviewable but never shown to the household. The
   trade-off is explicit: a placeholder will look like real data on screen, so
   the code marker and the swap condition are the only guard.
2. **Deterministic, not random.** The synthetic series is generated from a fixed
   seed so it looks identical across reloads and tabs. A series that reshuffles
   on every refresh reads as broken and destroys trust in the real charts next
   to it.
3. **Writes go to a real store.** The thermostat setpoint persists in Node-RED
   flow context so dragging it is genuinely stateful (and survives a deploy),
   rather than snapping back — which would make the control feel broken.
4. **Single swap point.** Each placeholder reads through one function that
   returns either the live entity or the placeholder. When the HA entity appears,
   the swap is one condition, not a rewrite; the `data-demo` marker disappears by
   itself because it keys off "is this the live source".
5. **Never mixed.** A card is either fully live or fully demo — never a live
   total blended with a demo component.

---

## 4. Reference → our data mapping

| Reference component | Our substitute | Data source | Phase |
|---|---|---|---|
| Greeting header | Time-of-day greeting + date + availability pill | Node-RED clock + HA `96/96` | 2 |
| Weather block | **Gated** — needs a `weather.*` entity | — | 5 |
| Thermostat dial | **Gated** — needs `climate.*` | — | 5 |
| Hero image card | "House status" hero: lights on / doors / locks, coral FAB → Kiosk tab | HA states | 2 |
| Device tile grid | **96-entity tile grid**, domain-coloured, ON/OFF + toggle, room filter | HA REST + WS | **1** |
| Power Consumed area chart | Activity area chart: entity state-changes per hour, last 24 h | HA history API | 3 |
| Top Consumer avatars | "Recently changed" — last N entities that changed state | HA WS events | 3 |
| Media card | "Now playing" from the 16 `media_player` entities | HA states | 3 |
| Mini bar chart (Last Days) | Lights-on count per day, last 7 days | HA history | 3 |
| Coral active nav pill | Same | Flows | 0 |
| Flat bordered cards, 16–20 px radius | Same, via CSS overrides on `md-card` | CSS | 0 |
| Roboto Flex type scale | Same — self-host the font or fall back to system sans | CSS | 0 |

---

## 5. Phased plan

Each phase is independently shippable and has a gate that can fail.

### Phase 0 — Design tokens (foundation, no layout change)
Introduce coral as the accent, switch page/card surfaces to the reference values,
flatten cards to a 1 px border + 16 px radius, apply the 4-step type scale.

**Gate:** 3-palette WCAG AA suite still passes at 4.5:1 · all nav/icon tests
green · live screenshot shows flat cards and coral active pill · no layout shift
on the 800×1280 viewport.

**Risk:** coral `#FA6F63` on navy `#1F2B47` is ~5.9:1 (passes), but on the *light*
**Risk (measured, not estimated):** coral as TEXT clears AA on our dark card —
`#FA6F63` on `#1F2B47` = **5.03:1**, on page `#1a1a2e` = **6.11:1**. But it
**fails** on the lighter palettes: `#434c5e` (Nord card) = **3.09:1** and the
reference's own navy `#243a54` = **4.16:1**. So coral needs a per-palette
text-variant exactly like `--shd-accent-text` does today, and the contrast suite
must run per palette. Worth noting: indigo had the same Nord failure (3.05:1),
so this is a pre-existing structural issue, not one coral introduces.

### Phase 1 — Device tile grid (the actual UX win)
Replace the 96-row table with a responsive tile grid rendered by a
`ui_template` (own CSS grid, so it can be 2 columns on the A7 Lite and 4 on
desktop). Domain → colour. Each tile carries icon, name, state, and a toggle
wired to the existing HA control path. Add a room/domain filter and a search box.

**Gate:** toggling a real light from a tile is verified on the live dashboard ·
state refresh ≤ 2 s after the HA state event · all tiles ≥ 44 px touch targets ·
grid renders 96 tiles without jank on the A7 Lite · the table is removed, not
hidden behind a flag.

### Phase 2 — Header + house-status hero
Greeting header, availability pill, and a hero card summarising "N lights on ·
2 doors closed · 2 locks locked" with a coral FAB that jumps to the Kiosk tab.

**Gate:** counts match HA `get_states` at time of render · header readable at
800 px · no hardcoded values.

### Phase 3 — Charts + media
Activity area chart (coral stroke, gradient fill, dotted guides) from HA history;
"Recently changed" strip; "Now playing" media card. Decide the Grafana iframe
question (restyle the wrapper vs replace with chartjs).

**Gate:** chart shows real history for the last 24 h · no empty-state that reads
as zero (must say "no data") · media card degrades cleanly when nothing is playing.

### Phase 4 — Kiosk + device tuning
Fold the new language into the Kiosk tab (already has MQTT control), tune for the
A7 Lite: 800×1280 portrait, tab order, and the wake/view buttons.

**Gate:** verified on the physical tablet once WallPanel is deployed (parent card
`t_3ed8e1bb`).

### Phase 4 — Interactivity pass (all tabs)
Enforce §4a across everything that exists, including the tabs this redesign does
not touch (Home Lab, Network, Kanban, System Health settings). Remove or wire
every element that claims to be a control but is not one.

**Gate:** the interactivity audit is written down, per element, with the class it
claims; zero "control" elements that do nothing; 44 px hit areas measured on the
rendered boxes; keyboard traversal reaches every control.

### Phase 5 — Thermostat + energy on labelled placeholders (UNBLOCKED 2026-10-19)
Per the user's decision, build the thermostat dial and the energy chart **now**,
on placeholder data, to the terms in §4b: `data-demo` marker (invisible), deterministic seed,
setpoint persisted in flow context, one swap point per widget so the real HA
entity drops in later.

**Gate:**
- `data-demo="true"` present on both placeholder containers in the live DOM, and
  the swap entity named in a code comment (no visible badge -- user decision).
- The synthetic series is byte-identical across two page reloads and two deploys.
- Dragging the thermostat and reloading the page returns the same setpoint
  (proves it persists rather than snapping back).
- Swapping in a real entity is a one-condition change: document the exact
  condition and the entity id that will satisfy it.
- No demo value is ever summed into a live total.

---

## 6. What I would deliberately NOT copy

- **The photo hero.** It implies a room camera feed we do not have; a stock photo
  on a live dashboard is decoration pretending to be data. Substitute the
  house-status hero.
- **The "Top Consumer" avatars.** They are a people/energy leaderboard. With no
  energy data it would be a fake ranking. Substitute "recently changed".
- **The decorative character illustration.** Seasonal art in a monitoring surface
  competes with alerts, and our alerts are the one thing that must never be missed.
- **Chevron nav groups.** We have 7 flat tabs; nesting would hide content on a
  800 px tablet for no gain.

---

## 7. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Coral accent vs existing 3 palettes | Nord/Cyberpunk contrast failures | Extend the contrast suite to coral per palette in Phase 0 |
| 96 tiles in one template | Slow first paint on A7 Lite | Render on WS event, cap at ~120 nodes, measure paint time |
| Grafana iframes look foreign | Visual inconsistency | Decide in Phase 3: accept a framed treatment, or replace with chartjs |
| Layout expectations vs 6-unit grid | Design can't be reproduced exactly | Approximate; the tile grid + header carry most of the identity |
| Building gated widgets early | Dead widgets with fake numbers | Phase 5 gate: entity must exist first |
