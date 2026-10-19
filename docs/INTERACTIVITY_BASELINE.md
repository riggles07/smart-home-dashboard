# Interactivity baseline — measured 2026-10-19

Starting point for Phase 4 (card `t_ff8c5949`). These are measurements taken on
the **live** dashboard (`http://192.168.4.100:1880/ui`), not readings of source.

## Home Assistant tab (`#!/5`)

| Metric | Value |
|---|---|
| Visible controls | **104** |
| Controls under 44 px in either axis | **1** |
| Breakdown | 96 × `button.shd-row-btn` ("Turn on/off"), 7 × nav `button.md-no-style`, 1 × `md-switch` |

### The one failure, and why it has survived

The `md-switch` labelled **"Primary Light"** renders at **164 × 30 px** — 30 px
tall, below the 44 px touch floor.

This is the defect already suspected in the plan: the theme's 44 px rules target
selectors that match nothing real.

```
.ui_switch .mdc-switch      ->  0 elements
.ui_slider input[type=range]->  0 elements
md-switch (actually rendered)->  1 element
md-slider (actually rendered)->  0 elements
```

So `min-height: 44px` has been declared for years against two selectors that
resolve to zero nodes. The rule looks like coverage in the CSS and provides none.
Fixing it means targeting `md-switch` / `md-slider`, not the Material-2 class
names from a newer library version.

## What this baseline does NOT cover (P4 must add it)

- **Per-element classification** (control / navigation / display) for all seven
  tabs. Only the HA tab was measured.
- **Dead-control detection.** A button that renders and does nothing cannot be
  found by measuring boxes — it needs a click that produces no state change.
- **Keyboard traversal.** Tab order and visible focus were not exercised.
- **Failure messaging.** Whether a failed HA call surfaces anything.
- **Grafana iframes.** Cross-origin, so their inner controls are classified as
  EMBEDDED and are out of reach — this needs to be stated in the UI, not just here.

## Prior evidence this baseline agrees with

- The 44 px selector mismatch was first flagged in the UI audit
  (`t_86098dd7`) as "likely <44px, needs live DOM". It is now measured: 30 px.
- The nav rail icons were rendering a `?` fallback until 2026-10-19
  (`tests/test_nav_icons.py` now pins the verified set) — another instance of the
  same class: *declared* intent that never reaches a rendered element.
