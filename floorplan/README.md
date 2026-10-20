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


## Visual fixes after the first on-device screenshot (2026-10-19)

The card worked on first try -- taps controlled the lights -- but looked bad.
Three separate causes, none of them guesswork:

1. **The white "Clear log" panel** covering half the screen. Cause: `log_level:
   warn`. The docs are explicit that setting ANY level *displays* the panel; it is
   not a silent verbosity setting. Removed from the dashboard config (re-saved
   over WS; readback keys are now `image,stylesheet,rules`).
2. **Rooms rendering near-black.** The old CSS used `#243a54` at 0.55 alpha
   (`#1b2a3d` at 0.55 for off) over a dark page -- which composites to almost the
   page colour. Alpha is not the same as "muted". Fills are now opaque:
   base `#2b3f57`, off `#22303f`, unbound `#1b2734`, on `#fa6f63` @ 0.92.
3. **The plan floating in dead space.** The trace inherited the screenshot's
   viewBox (`0 0 1280 1048`) while the plan only occupies the middle. `render_floorplan.py`
   crops the viewBox to the union of the room paths -- 1086x802, i.e. 65% of the
   old area -- and adds `<text>` labels from the measured centroids with
   `pointer-events:none` so labels can never intercept a tap.

### Verified before asking for another upload

The browser cannot open `file://` or `data:` URLs, and this container sits on a
docker bridge the browser cannot reach. So the preview was served for real: a
temporary `http in -> template -> http response` flow on the Node-RED LXC, viewed
in the browser, two panels side by side (nothing on / study+corridor on) to check
both states in one shot. Then the temporary flow was removed -- live Node-RED is
back to 135 nodes with zero leftovers.

Result: rooms clearly visible, labels readable, coral highlight unmistakable,
plan filling the card.


## Why a refresh showed no change (2026-10-19)

Uploads were landing correctly -- HA served byte-identical copies of the new
assets:

```
floorplan.svg  2539 b  md5 3992164f...  MATCHES LOCAL
floorplan.css  1997 b  md5 fd3a925f...  MATCHES LOCAL
```

The problem was the response header:

```
Cache-Control: public, max-age=2678400     <- 31 days
```

HA serves everything under `/local/` with a 31-day browser cache. The phone kept
using the previous SVG and CSS and never re-requested them, so no amount of
refreshing could show a change. Files on disk were right; the client was right too
-- it was told the bytes were good for a month.

Fix: **cache-bust the URL itself.** The dashboard config now uses

```yaml
image: {location: /local/floorplan/floorplan.svg?v=3, cache: false}
stylesheet: /local/floorplan/floorplan.css?v=3
```

`cache: false` alone does NOT help here -- that controls Floorplan's own caching,
not the browser's max-age. Only a different URL forces a re-fetch. Verified by
reading the saved config back: `image=...svg?v=3`, `cache=False`,
`stylesheet=...css?v=3`, `rules=4`.

**Bump `?v=` whenever a floorplan asset changes**, or the same stale-cache symptom
returns and looks exactly like a broken upload.


## Palette v3 -- "still black and grey" (2026-10-19)

Second feedback round. Root cause was my own v2 decision, twice over:

1. v2 replaced every room colour with ONE muted slate (`#2b3f57`). Slate is
   blue-grey; on a phone it reads as grey. The Roborock colours were doing real
   work -- they let you find a room without reading a label.
2. Then the unbound rooms (kitchen, dining) were forced to grey `#38414d` to signal
   "inert". Those are the two LARGEST rooms on the plan, so grey dominated the
   whole view.

v3 rule: **colour encodes WHICH room it is; interactivity is encoded separately**
(cursor + dashed stroke + absence of glow). So:

| class | rooms | base | lit |
|---|---|---|---|
| blue | study, corridor | `#2f6ea8` | `#63b3ff` |
| orange | kitchen, bathroom | `#a8542f` | `#ff8f5a` |
| teal | dining room | `#177a74` | `#3fe0d0` |
| gold | laundry, living room | `#8a6d1f` | `#ffd75e` |

ON = brighter version of the room's OWN hue plus
`drop-shadow(0 0 14px rgba(255,214,140,.65))`. Off = same hue at 0.55 alpha.
Unbound = own hue at 0.45 with a dashed stroke and no glow.

Verified in the preview: all seven rooms colour-coded, Study+Corridor glowing,
reads as a floorplan rather than a grey diagram.

## Animated / photo-realistic rooms -- what is actually possible

The question was whether room photos or videos can make rooms look animated.
Short answer: **photos yes, video no (not as room fills)**, and the animation
worth doing does not need either.

- **Photos: yes.** SVG can embed rasters with `<image href>`, clipped to a room
  with `<clipPath>`. So each room polygon can be filled with a photo of that room.
  Requirements: roughly top-down, consistent orientation, no people, and the room
  crop must match the polygon's aspect or it stretches. Same 31-day cache rule --
  each new image needs a `?v=` bump.
- **Video: not recommended.** It needs `<foreignObject><video muted playsinline>`;
  N simultaneously decoding videos on an A7 Lite destroys battery and frame rate,
  autoplay policies are unreliable, and a perspective video cannot align with a
  2-D plan. If a video is the only asset, extract a frame (`ffmpeg -ss`) and use it
  as a still -- same result, none of the cost.
- **Animation: CSS, driven by entity state.** The glow/pulse already present is the
  mechanism; it can be made richer (breathing glow on ON, warm flicker) with zero
  new assets and no performance risk.


## Room photos + label correction (2026-10-20)

Five photos uploaded: study, kitchen, dining_room, corridor, living_room.
Missing: laundry, bathroom (still flat colour, as expected).

### The photos are not overhead shots

Measured by looking at each one, not by trusting the filenames:

- **living_room.jpg** -- standing height, ~50 degree angle, and the photographer's
  bare leg fills the bottom third.
- **corridor.jpg** -- eye level at the TOP OF THE STAIRS, feet and socks in frame.
- **kitchen.jpg** -- genuinely overhead, but the photographer's legs, arm and head
  are in the bottom of the frame, and the island is very cluttered.

So they cannot be pasted in as room fills: stretched across a polygon they read as
a wall at the top and a floor at the bottom, which looks broken.

### What makes them usable anyway

- `preserveAspectRatio="xMidYMid slice"` on `<image>` -- crops to fill the polygon
  instead of stretching it, so portrait phone photos are not distorted.
- `filter: blur(5px) saturate(.85) brightness(.5)` -- removes the perspective and
  the clutter; the photo becomes texture.
- the room's own fill at reduced opacity ON TOP (`.room.has-photo`), so light state
  still reads over the photo.
- each image is clipped to exactly its own room polygon with `<clipPath>`. This is
  what fixes "the living room photo flows into foyer": the living-room photo *does*
  contain the open-plan foyer, but a clip path cannot bleed, so the foyer only ever
  shows its own photo.

### Labels changed, ids deliberately left alone

The visible text is now **Family Room** (was Study) and **Foyer** (was Corridor).
The SVG ids stay `study` and `corridor`, because `floorplan.yaml` binds every rule
by id -- renaming an id silently breaks that room's tap. The label was wrong, the
id is just a key.


## Photos did not show on the device -- TWO bugs, 2026-10-20 (second round)

Reported as "partially updated: still no background graphics on rooms with
lighting controls". Two independent causes, both invisible in source:

### 1. The card needed two uploaded files and only one was uploaded

`image:` + `stylesheet:` are separate assets. The new SVG went up; the CSS did
not, so the device rendered new geometry with the OLD stylesheet -- which had no
`.room-photo` / `.has-photo` rules at all. Measured on HA while debugging:

```
/local/floorplan/floorplan.svg   200  4495 b   MATCHES local
/local/floorplan/floorplan.css   200  3156 b   MISSING the whole photo layer
                                 (local was 4167 b)
```

That also explains the exact symptom shape: unbound rooms (kitchen, dining) are
painted at `fill-opacity: .45`, so their photos showed through; bound rooms were
at `1.0`, so theirs were covered. "Graphics appear only where there are NO
controls" was the fingerprint of a missing stylesheet, not of a missing image.

Fix: the stylesheet is now INLINED into the SVG (`render_floorplan.py` reads
`floorplan.css` and emits a `<style>` block). One file to upload, and the two can
no longer drift -- `tests/test_floorplan_assets.py` fails if they do. The
dashboard config no longer has a `stylesheet:` key at all (`repoint_dashboard.py`,
saved over WS and read back: `image=/local/floorplan/floorplan.svg?v=6`,
`stylesheet` absent, `rules=4`).

### 2. `floorplan.class_set` REPLACES the class attribute

In ha-floorplan 1.1.5 (the build on this HA):

```js
static setClass(e, t) { e.setAttribute('class', t) }
```

So `service_data: '${entity.state === "on" ? "room-on" : "room-off"}'` turns
`class="room blue has-photo"` into `class="room-on"` on the very first state
update. `.room.has-photo` then stops matching, the fill goes fully opaque and
covers the photo -- even with the correct stylesheet. Fix: every rule that paints
a room is id-scoped (`#study.room-on`), and each path also carries its hue as a
`fill=""` attribute so the SVG default (black) can never win. A test asserts no
room-painting rule depends on a class other than the state class.

### 3. A '<' anywhere in the inlined CSS silently truncates it

An inline `<style>` in an HTML-parsed SVG is text only until the first `<`. One
comment containing `<image>` cut the sheet off at 5 of 18 rules in a real browser
-- the photo tint AND every ON/OFF rule simply did not exist. The renderer now
refuses to emit a stylesheet containing `<` or `&`; a test backs it up.

### Verified, by measurement rather than by eye

A local preview reproduces floorplan's own path (fetchText -> innerHTML ->
`querySelector('svg')` -> append into a **shadow root** -> `class_set` via
`setAttribute`), with the real photos served from HA. Three panels: as-shipped /
after `class_set "room-off"` / after `class_set "room-on"`.

```
computed (shadow root)   study fill / opacity       laundry fill / opacity
as shipped               #2f6ea8  0.42              #8a6d1f  1
after "room-off"         #2f6ea8  0.50              #8a6d1f  0.55
after "room-on"          #63b3ff  0.55              #ffd75e  1
photo filter             blur(5px) saturate(.85) brightness(.5)   applied

pixels that change when .room-photo{display:none} is injected: 373,833
Family Room mean RGB   with photo [50.2 74.1 98.0]  without [37.1 67.5 98.2]
```

The last two lines are the ones that matter: the photo layer is doing real work
behind the tint, in a shadow root, after the class attribute has been wiped.

Note: the five room photos are 1.6-2.3 MB each (~9 MB total). They are cached
after first load, but they are worth downscaling to ~100 kB each if the kiosk
ever feels sluggish.

## Photo orientation -- north-up photos, north-left plan (2026-10-20)

Reported: "all photos were taken with north up being to the left of the dashboard,
each one needs rotated with this orientation."

Mapping: the photo's up vector is north; the plan has north to the **left**; so the
photo must turn **counter-clockwise 90 degrees**. SVG `rotate()` is
clockwise-positive, so the transform is `rotate(-90 cx cy)`:

```
(0,-1) --rotate(-90)--> (-1,0)     photo-up  ->  left      (north-up == plan-left)
```

Two details that make this not break anything else:

- **The clip moved to a wrapper `<g>`.** A `clip-path` is resolved in the element's
  own (already transformed) user space, so a clip sitting on a rotated `<image>`
  would rotate with the pixels and the photo would spill out of its room. The `<g>`
  holds the clip, the `<image>` turns inside it.
- **The image box is pre-swapped (w<->h) about the same centre**, so the -90 turn
  maps it exactly back onto the room polygon's bbox. `preserveAspectRatio="slice"`
  therefore crops the same way before and after; nothing is stretched and no other
  element on the plan moves.

Only the SVG changed -- the five JPEGs on HA are untouched, no re-upload of binary
assets. `--rotate N --out /tmp/x.svg` renders any orientation from the same code,
which is how the four-way comparison was produced.

`tests/test_floorplan_assets.py` now asserts that *every* photo carries the same
`PHOTO_ROTATE` angle (one unrotated room is the likely future bug) and that the
turned box lands within 1 unit of the room bbox on all four edges.

## Normalisation: hand-set geometry replaces the trace (2026-10-20, third pass)

Asked for: "normalize the floor plan from our initial rough generation; stairs
should show in the top right corner of foyer and living room should fill out the
square area."

The trace was a colour segmentation of a Roborock screenshot, so it had two
classes of defect that no amount of CSS could fix:

1. **Jigsaw notches** wherever the vacuum's floor colour bled into a doorway --
   kitchen/dining wall, laundry's left side, the bathroom's left side, the
   kitchen's bottom edge, the study's bottom-right.
2. **Two rectangular holes punched through the living room** by the app's own
   "90 deg" and "layers" buttons, which the tracer masked out. The room was left
   as a 113-unit-wide strip instead of filling its 206 x 294 rectangle.

`floorplan/geometry.py` is now the source of truth: hand-set, rectilinear, and
**re-measured off `source-map-flat.jpg` by colour segmentation** (per-row min/max
of the orange/teal/gold/blue masks), not invented. The numbers are in that file's
docstring. Normalisation rules:

- every edge axis-aligned (test: `test_every_room_is_rectilinear`);
- no two rooms overlap (test samples a 4-unit grid and requires <= 1 hit per point);
- neighbours share one wall coordinate so no black sliver shows between them --
  kitchen.right == dining.left == 915, and the foyer body's east wall IS the
  living room's west wall at 980 (test: `test_neighbours_share_one_wall_coordinate`);
- the living room is a plain rectangle, right edge flush with the dining room
  (1186), bottom flush with the foyer (884);
- labels come from the polygon **area centroid** (shoelace), so they stay inside
  the room when geometry moves -- no hand-maintained label table any more.

Small steps remain where the house really has them (the kitchen's bottom-left
jog, the dining room's bottom-left step, the study's bottom-right return). Those
are rectilinear and measured; they are the plan, not tracer noise.

### Stairs

Never in the robot's map -- a vacuum cannot climb them -- so they are drawn:
two strings plus 8 evenly spaced treads inside the foyer's right arm
(x 986..1156, y 444..584, a 6-unit inset on all four sides), plus a chevron for
the direction of travel. Stroked, not tinted, so they read as an architectural
element rather than as photo texture, and `pointer-events: none` so a tap on the
stairs does nothing (tests pin both).

### What replaced what

`render_floorplan.py` no longer reads its own output or the raw trace; it imports
`geometry.py`. It still inlines `floorplan.css`, keeps the `fill=""` attribute on
every path, keeps the `rotate(-90)` photo transform and the wrapper `<g>` clip.
Dashboard bumped to `?v=8`. 531 tests pass (6 new for the normalisation).

## Photo weight: 8.85 MB -> 567 kB (2026-10-20)

The five originals came straight off a phone: 3072x4080, 1.6-2.3 MB each. The plan
never shows them larger than ~300 CSS px of room width, and `floorplan.css` blurs
them 5 px before drawing, so almost all of that is unshowable.

`downscale_rooms.py` rewrites them to 828x1100, quality 78 (dropping only if a file
exceeds a 120 kB budget -- the kitchen needed q=60), progressive, 4:2:0, no EXIF.
Output goes to `floorplan/rooms_small/` under the same filenames, so the plan only
needs a cache-busting bump, not a rename.

```
corridor.jpg     1806 kB -> 120 kB   (93.4%)
dining_room.jpg  1767 kB -> 113 kB   (93.6%)
kitchen.jpg      2271 kB -> 116 kB   (94.9%)   q=60
living_room.jpg  1572 kB -> 108 kB   (93.1%)
study.jpg        1643 kB -> 111 kB   (93.3%)
TOTAL            8.85 MB -> 567 kB   (93.7%)
```

Verified by running both through the card's **exact** pipeline (rotate -90 -> slice
crop to the room box -> resize to the rendered width -> 5 px blur -> 42% tint) and
comparing at 590 px (desktop card) and 300 px (phone):

```
worst PSNR across 5 rooms x 2 sizes: 53.1 dB      (>40 dB is visually identical)
mean absolute channel difference:    0.17-0.30 / 255
```

So the swap is invisible. `PHOTO_V = 2` in `render_floorplan.py` bumps the `?v=` on
every `rooms/*.jpg` href -- the filenames stay the same, but the URL must change or
the 31-day `/local/` cache keeps serving the 2 MB originals.

Upload target: `/config/www/floorplan/rooms/` (the five files, same names), plus the
new `floorplan.svg`. Dashboard is on `?v=9`.

## Bathroom + laundry photos, levelled and cropped (2026-10-20)

Both rooms were shot looking in from their doorway, so both are now photographic.
Every one of the seven rooms has a photo.

### Why this is "level + crop" and not a perspective warp

"Rectify" needs four known corners, and neither frame has them:

- **laundry** -- the left jamb is behind the open door, the sill is out of frame
- **bathroom** -- the shower curtain covers the back wall's lower-left corner

The standard fallback is to measure the room's **vertical vanishing point** from
detected edges. Tried, and rejected on these two images:

```
bathroom   1786 "vertical" segments -> vp 79 px below the bottom edge
           i.e. a 40 deg convergence, which no handheld room shot has.
           The wood-floor grain and the door leaf dominated the fit;
           applying it smeared the frame into streaks.
```

The per-line roll estimates then disagreed with each other by ~20 deg:

```
bathroom   Hough roll median -9.99     head line -28.99 (a sloping soffit, junk)
laundry    Hough roll median +9.02     head line -11.00
                    eye on a rotation strip: bathroom +6, laundry -6
```

So `level_rooms.py` uses **angles chosen by eye** from a rendered rotation strip --
the only guesses in the whole pipeline, isolated in one table. A wrong rotation
looks worse than none, and a "derived" number here would be invented precision.

What it does do, and what is measured:

- **crop** to the room and drop the door leaf, casing and threshold
  (bathroom `(1150,100,2760,4080)`, laundry `(430,760,2440,4080)`, source pixels);
- **level** by `+6.0` / `-6.0` deg, then trim 6% off each side to remove the
  rotation wedges;
- then the normal pipeline: rotate -90 for the plan, downscale, blur, 42% tint.

### Verified

A controlled pixel experiment at 1400 px render width (screenshot with the photo
layer, screenshot with `.room-photo{display:none}` injected into the shadow root,
per-room diff):

```
room         pixels changed        mean |d|
study         57340 / 77220          10.79
kitchen       98143 / 109056         14.85
dining_room   50646 / 62832          13.66
corridor     148902 / 185856         11.12
laundry        5880 / 11178           9.48   <- new
bathroom       8288 / 13013          12.25   <- new
living_room   33802 / 44073          12.34
```

Weight after adding both: 711 kB for seven rooms (was 8.85 MB for five).
Dashboard `?v=10`. 533 tests pass.

### Reproducibility fix: pass-through rooms must be COPIED, not re-encoded

`level_rooms.py` initially re-saved the five untouched rooms at quality 96 so the
output dir held all seven. That is a lossy round-trip through a file that had
already been encoded: the second-generation source then produced *different*
downscaled bytes at the same file size (study: max per-channel diff 22, mean 0.58),
so `rooms_small/` no longer matched what HA was serving, and re-running the pipeline
changed files that should have been identical forever.

Fixed with `shutil.copy2` for pass-through rooms. The whole chain is now
reproducible from the pristine originals: `level_rooms.py` -> `downscale_rooms.py`
reproduces the seven committed files byte-for-byte, and all seven md5-match the
live `/local/floorplan/rooms/`.
