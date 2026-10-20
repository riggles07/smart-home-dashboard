# Floorplan dashboard (ha-floorplan)

Goal: a second Lovelace dashboard showing the main floor as an interactive SVG —
tap a room to toggle its lights, room fills glow when ON.

Reference: <https://experiencelovelace.github.io/ha-floorplan/>

## What the reference workflow requires

From the official Quick Start, the intended path is:

1. Draw the plan in Floorplanner (or similar), export as an **image**.
2. Redraw it **on top of that image in Inkscape** — the docs are explicit that
   Floorplanner cannot export SVG, so the drawing happens twice.
3. **Add IDs to every element** you want to interact with.
4. Install `floorplan.js` via HACS (or drop it in `/config/www` manually).
5. Map HA entities to those SVG ids in YAML.

Steps 1–3 are the expensive part. We have skipped them — see below.

## What we did instead: trace the Roborock map

The source material was two **Roborock app map screenshots**: one isometric, one
flat top-down. Only the flat one is usable — ha-floorplan positions elements in
2D coordinate space, so a perspective view cannot be traced.

`trace_roborock_map.py` recovers the room geometry by colour segmentation:

- The Roborock renderer paints each room a flat colour, which makes rooms
  recoverable without Inkscape.
- Segment per colour family → connected components → contour → polygon simplify.
- Room names come from component position, and **each room becomes
  `<path id="kitchen">`** etc. — exactly the ids ha-floorplan binds to.

Output: `floorplan.svg` (7 room paths), `rooms.json` (measured geometry),
`trace-preview.png` (outlines drawn back over the source, for eyeball checks).

### Colours had to be MEASURED, not guessed

Three successive bugs, each caught by looking at the preview rather than trusting
the numbers:

| Symptom | Cause |
|---|---|
| Study traced as "kitchen"/"laundry" | Colour ranges came from a quantised histogram (cluster centres), not the actual paint. Also a **BGR/RGB mix-up**: `cv2.imread` returns BGR, so an RGB orange was matched as a blue. |
| Laundry missing entirely | Sampled at `dy=-45` from the label, which landed on the **dark label icon**, not the floor. Real paint is `(228,190,89)`, 39 away from the assumed gold. |
| Dining room traced the furniture | Target `(139,197,192)` is the dining **table**; the room floor is the saturated `(35,205,195)`. |

Rooms sharing a colour family (Kitchen/Bathroom identical orange; Laundry/Living
room within tolerance of each other) are separated by **connected components**
and, where needed, by centroid position.

### Honest limits

- It is a **trace of the vacuum's render**, not a designed floorplan. It will not
  be survey-accurate, and doorways appear wherever the renderer drew a wall.
- Furniture and labels are excluded on purpose — they must not become click
  targets.
- The app's own overlay (rotate button / "Map Details") is masked out, or it
  traces as a bogus room.
- Only the main floor exists in these screenshots; other floors need their own.

## Blocker: getting files into HA

`ha-floorplan` needs two files HA can serve: `floorplan.js` (the card) and
`floorplan.svg` (the plan) — normally `/config/www/floorplan/*`.

Measured state of the install path:

- **HACS integration is loaded** (`/api/config` components includes `hacs`) and
  already serves three frontend resources (`hacs:HomeAssistantLGThinkQCards`,
  `charger-card`, `bambu_lab`). So the HACS route is alive — contrary to an
  earlier note in this repo that HACS was missing entirely.
- **`floorplan` is NOT currently registered** as a Lovelace resource.

But this agent has **no write access to HA's `/config`** — no shell, no SSH
add-on (its image extraction failed with corrupted Docker layers), and the REST
API has no file-upload endpoint. HACS can install the card, but it cannot place a
custom SVG.

So one of these is needed before the floorplan can render:

| Option | Effort | Notes |
|---|---|---|
| **File Editor add-on** | install once, then paste | simplest; can write `/config/www/` |
| **Samba share / SSH add-on** | retry install | SSH add-on previously failed at image extract |
| **Serve from Node-RED** | no HA change | point `image:` at the Node-RED LXC URL; fails if the HA page is https (mixed content) |

## Next steps

1. Get `floorplan.svg` into `/config/www/floorplan/` (pick an option above).
2. Install ha-floorplan via HACS (search `floor`, download, add resource).
3. Create the dashboard (`url_path` must contain a hyphen — `floor-plan`).
4. Write `floorplan.yaml` mapping each room id → its HA entities, with
   `tap_action` toggles and `state_action` to drive the room fill.
5. Verify by tapping a room and watching the real device change — same standard
   applied to the kiosk MQTT work.


## Room → entity mapping: measured, and partly MISSING

`area_entities()` filtered to `light.*` / `switch.*`, one line per area:

```
living_room  L1  light.living_room_ceiling
kitchen      L0  S1
bedroom      L2  light.master_bedroom, light.bedroom_bedside          S4
exterior     L3  light.h7060, light.exterior_gd_l                     S1
basement     L3  light.basement_motion_light_1, light.basement_movie_dim  S9
media        L8  light.m2, light.seat_v                               S5
family_room  L1  light.family_room_family_room                        S3
foyer        L3  light.foyer_candelabra_1, light.foyer_candelabra_2   S2
laundry      L0  S3
kids_rooms   L0  S2
garage       L2  light.gdo_right_garage_light, light.gdo_left_garage_light  S7
office       L1  light.a1_03919c471500682_chamber_light               S3
outside      L1  light.outside_relay  /  virtual L0 S10
```

The traced floorplan has **Study, Kitchen, Dining room, Laundry, Bathroom,
Corridor, Living room**. HA has **no `bathroom`, `study` or `dining_room` area at
all**, and `laundry` owns zero lights (3 switches).

So a straight id-for-name binding is impossible for four rooms. Bindings are
written ONLY where a real area with real entities exists; the rest are left
explicitly unbound rather than pointed at a guessed entity. A floorplan that
silently toggles the wrong room's light is worse than one that does nothing.


## Live serving state (verified 2026-10-19)

Checked by HTTP GET against HA, which is the only honest way to know what the
frontend can actually load:

```
/local/floorplan/floorplan.svg   200  1774 b   image/svg+xml   <- uploaded
/local/floorplan/floorplan.css   404
/local/floorplan/floorplan.yaml  404
```

`/local/` maps to `/config/www/`, so a 200 proves the file is on disk AND served.
HACS is installed by the user; the card is not yet on any dashboard.

## Why the dashboard was NOT created via API

`lovelace/*` WebSocket commands became flaky mid-session: auth succeeds
(`auth_ok`), then `lovelace/resources` and `lovelace/dashboards/list` are sent and
never answered -- no result, no error, socket stays open. The same two commands
had succeeded minutes earlier, so it is intermittent, not a permissions problem.

Instrumenting the function with an immediate `prog()` write proved where it
stalls (`stage: listing-dashboards`), which is the only way to distinguish "HA
refused" from "HA never replied". Rather than hammer a live system with retries,
the dashboard is being created through the HA UI instead. Registry writes
(device/entity/area) and `lovelace/dashboards/create` + `lovelace/config/save` had
all worked earlier, so the capability exists -- it is just not reliable enough to
build on unattended.


## COMPLETE -- dashboard created (2026-10-19)

All assets verified served by HTTP GET against HA:

```
/local/floorplan/floorplan.svg          200  1774 b  image/svg+xml
/local/floorplan/floorplan.css          200  1554 b  text/css
/local/floorplan/floorplan.yaml         200  3855 b  application/yaml
/hacsfiles/ha-floorplan/floorplan.js    200  268026 b  (HACS install, also at
                                                       /local/community/ha-floorplan/)
```

Dashboard `floor-plan` ("Floor Plan", icon `mdi:home-floor-0`, in sidebar) created
over the WebSocket API with `lovelace/dashboards/create` +
`lovelace/config/save`. Readback confirms:

```
views=1  cards=1  type=custom:floorplan-card
```

### The workaround that made it work

`lovelace/dashboards/list` was the call that hung. `dashboards/list` loads every
dashboard's config to enumerate them -- including `by-room`, which is configured
with the auto-generating **areas strategy**. So the most likely cause was that
listing had to instantiate the very strategy dashboard created earlier in the
session, and blocked doing so.

Fix: **don't list.** Call `lovelace/dashboards/create` directly and treat an
"already exists" error as the exists-check. The create/save/readback sequence then
completed first try. Same capability, without the enumeration step that was
wedging.

### Still unverified (needs a logged-in browser)

Rendering and tap behaviour cannot be confirmed from here -- viewing a Lovelace
dashboard requires an interactive HA login, which this agent does not have. What
must be checked by eye:

- rooms render at all, and fills track light state
- tap on study / corridor / living_room / laundry changes the real device
- kitchen, dining_room, bathroom are inert (no pointer cursor, no tap)
- the four hazard entities are still unbound
