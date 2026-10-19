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
