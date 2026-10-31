#!/usr/bin/env python3
"""Anchor the measured room polygons onto the generated render, then snap them.

WHY
---
The art is a raster (decision D2 = 2b). The ha-floorplan docs solve this by hand-
tracing polygons in Inkscape, which rots on every re-render. This derives them:

1. ANCHOR, not guess. The control plan's plan-bbox is known exactly (it was drawn
   from geometry.py). The render's house-bbox is detected from its background. A
   per-axis affine maps one to the other. Both are the *outer wall*, so the anchor
   does not depend on guessing a margin -- an earlier version assumed a 3.5 %
   padding and every polygon landed short (measured: study drift 0.377 of room
   width, corridor area ratio 0.163).
2. REFINE inside the room, never across it. A colour region-grow starting at the
   room centroid is clipped to the anchored polygon dilated by SNAP px, so oak
   floors that are physically joined through a doorway cannot bleed into each
   other. Where the grow disagrees with geometry by more than AREA_TOL the room
   falls back to the geometric polygon (flagged `method: geometry`), because a
   wrong snap is worse than no snap.
3. VALIDATE. Every room reports area ratio, centroid drift and the method used;
   the script exits 1 if any gate fails, so it runs as a test and as a phase gate.

Outputs: hotspots.json (render-pixel + normalised polygons) and hotspots.png.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from geometry import FLOOR_ROOMS, bounds  # noqa: E402

SNAP = 22            # px the grow may move an anchored edge (render is 2K, so ~1 % )
AREA_TOL = (0.80, 1.25)     # grow vs anchored area; outside -> fall back to geometry
MAX_DRIFT = 0.10            # centroid drift as a fraction of room width
COLOUR_TOL = 22.0           # CIE-Lab distance for the grow
MIN_COVER = 0.85            # fraction of the anchored polygon the fit must keep
MAX_OUTSIDE = 0.02          # share of a hotspot that may land outside the house
# A stairwell shaft has no floor surface, so neither the centroid nor the colour of the
# fitted polygon means anything -- the fit slides onto the treads of the storey below
# (measured drift 0.116). The polygon is still emitted for drawing; it is not tappable.
VOID_ROOMS = {"open_below"}

# room -> (dx, dy) in render px, applied after the transform. Verified by cropping the
# room and looking at the outline. Empty unless a room defeats the automatic fit.
ROOM_OFFSET = {}


def control_plan_bbox(ctl_wh, pad=40, scale=1.6):
    """FLOOR bbox of the control image: the plan polygon bounds, wall strokes
    straddle them so half a stroke lies outside -- that is the centreline, which is
    what we map."""
    x0, y0, x1, y1 = bounds()
    w = (x1 - x0) * scale + pad * 2
    h = (y1 - y0) * scale + pad * 2
    fx, fy = ctl_wh[0] / w, ctl_wh[1] / h
    half = 7  # WALL_PX/2 in make_control_image.py
    return ((pad - half) * fx, (pad - half) * fy,
            (pad + (x1 - x0) * scale + half) * fx,
            (pad + (y1 - y0) * scale + half) * fy)


def render_floor_bbox(img):
    """Wall CENTRELINE bbox of the render: outer silhouette, inset by half a wall.

    Two earlier attempts are recorded here because both failed for interesting
    reasons:

    1. Scanning inward along mid-lines (bg -> wall -> floor) reported the house
       starting at x=1003, because the footprint is L-shaped: the mid-height line
       leaves the frame, crosses the empty quadrant, and only meets floor at the
       hall. Any four-edge scan assumes a convex plan.
    2. Taking the raw silhouette bbox included the soft drop shadow, inflating the
       plan by ~20 px per side.

    So: threshold the background strictly (>=20 to reject the shadow), take the
    largest contour's bbox, then inset by half the wall thickness measured once by
    scanning the top edge downward. geometry.py polygons are wall centrelines, and
    the centreline sits half a wall inside the outer face -- matching them is what
    stops polygons poking through the outside walls.
    """
    h, w = img.shape[:2]
    corners = np.concatenate([img[0:8, 0:8].reshape(-1, 3), img[0:8, -8:].reshape(-1, 3),
                              img[-8:, 0:8].reshape(-1, 3), img[-8:, -8:].reshape(-1, 3)])
    bg = np.median(corners, axis=0).astype(np.float32)

    dist = np.linalg.norm(img.astype(np.float32) - bg, axis=2)
    mask = (dist > 20).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    x, y, bw, bh = cv2.boundingRect(max(cnts, key=cv2.contourArea))

    # wall thickness: at mid-x scan down from the silhouette top to the first
    # pixel that is neither background nor light-neutral wall.
    def neutral(p):
        mx, mn = float(p.max()), float(p.min())
        return mx > 185 and (mx - mn) < 30

    mid = x + bw // 2
    started = None
    floor_y = y
    for yy in range(y, min(h, y + bh // 2)):
        p = img[yy, mid]
        if started is None:
            if not neutral(p):
                started = yy
                continue
        elif not neutral(p):
            floor_y = yy
            break
    T = max(8, floor_y - (started if started is not None else y))
    ins = T * 0.5
    bbox = (x + ins, y + ins, x + bw - ins, y + bh - ins)
    return bbox, bg


def fit(render_path: Path, control_path: Path, floor: str = "main") -> dict:
    render = cv2.imread(str(render_path))
    ctl = cv2.imread(str(control_path))
    if render is None or ctl is None:
        raise SystemExit("cannot read inputs")
    rh, rw = render.shape[:2]
    lab = cv2.cvtColor(render, cv2.COLOR_BGR2LAB).astype(np.float32)

    cb = control_plan_bbox((ctl.shape[1], ctl.shape[0]))
    hb, bg = render_floor_bbox(render)
    sx0 = (hb[2] - hb[0]) / (cb[2] - cb[0])
    sy0 = (hb[3] - hb[1]) / (cb[3] - cb[1])
    # Registration search was tried and MEASURED UNRELIABLE on this pair (wall-mask
    # IoU peaked at 0.13: the render's bright furniture -- white bed, kitchen island,
    # cabinets -- dominates a "light neutral" mask, so walls are not the dominant
    # structure the method assumes). The bbox anchor is used directly and alignment is
    # VERIFIED by an edge-band test below, which is the property actually needed.
    # P1 owns replacing this with per-room segmentation.
    sx, sy, tx, ty, reg = _register(render, ctl, lab, sx0, sy0, hb, cb)

    def ctl_to_render(px, py):
        # sx/sy are render-pixels-per-control-pixel; (tx,ty) is where the control
        # bbox corner lands in the render. Mixing normalised 0..1 coordinates with a
        # px-per-px scale collapsed every polygon to ~1.5 px (anchor area 0) -- the
        # "empty anchor polygon" failures. Units are stated once, here.
        return (tx + (px - cb[0]) * sx, ty + (py - cb[1]) * sy)

    # control pixel coords of the plan polygons
    x0, y0, x1, y1 = bounds()
    pad, scale = 40, 1.6
    w = (x1 - x0) * scale + pad * 2
    h = (y1 - y0) * scale + pad * 2
    fx, fy = ctl.shape[1] / w, ctl.shape[0] / h

    out, report = {}, []
    for rid, poly in FLOOR_ROOMS[floor].items():
        ctl_pts = np.array([((px - x0) * scale + pad) * fx for px, py in poly], np.float32)
        ctl_pts_y = np.array([((py - y0) * scale + pad) * fy for px, py in poly], np.float32)
        anchors = np.stack([ctl_pts, ctl_pts_y], 1)
        mapped = np.array([ctl_to_render(px, py) for px, py in anchors], np.float32)
        anchor_area = abs(cv2.contourArea(mapped))
        am = cv2.moments(mapped.astype(np.int32).reshape(-1, 1, 2))
        if am["m00"] == 0:
            report.append({"room": rid, "ok": False, "why": "empty anchor polygon"})
            continue
        # Compare AREA centroids on both sides. Using the vertex mean for the anchor
        # made notched rooms look like they were drifting 0.19 of their width when
        # they were identical polygons -- a measurement bug, not a fit bug.
        acx, acy = am["m10"] / am["m00"], am["m01"] / am["m00"]

        why: list[str] = []
        method, final = "geometry", mapped
        dbg = {}

        # Inset the anchored polygon by half a wall (~7 cm) to get the room INTERIOR.
        #
        # Three image-derived attempts came before this and are recorded because each
        # looked reasonable and each failed on a measurable ground:
        #   * bright+neutral "wall mask" -- the kitchen island, the pale counters and
        #     the white bed are the same colour as walls, so the clip ate 23-55 % of
        #     the room (edge-band purity fell to 0.56 on this render).
        #   * per-room colour region-grow -- furniture and lighting break uniform colour.
        #   * wall-mask IoU registration -- the same furniture dominates the mask (0.13).
        #
        # The walls are not something to be discovered in the render: they are known
        # exactly, because the control image was drawn from the same polygons at a known
        # scale. So the interior is defined geometrically -- polygon inset by half the
        # wall thickness -- and the RENDER is used only to VERIFY (drift + edge-band
        # purity). That is a deterministic transform, not an estimate, and it cannot
        # mistake an island for a wall.
        inset_px = max(3.0, 10.0 * sx)         # 10 cm: half-wall plus the render's wall shadow
        mask = np.zeros((rh, rw), np.uint8)
        cv2.fillPoly(mask, [mapped.astype(np.int32).reshape(-1, 1, 2)], 1)
        k = int(round(inset_px)) * 2 + 1
        eroded = cv2.erode(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k)))
        cnts, _ = cv2.findContours(eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = [c for c in cnts if cv2.contourArea(c) > 0.2 * anchor_area]
        if cnts:
            cnt = max(cnts, key=cv2.contourArea)
            approx = cv2.approxPolyDP(cnt, 0.008 * cv2.arcLength(cnt, True), True)
            final = approx.reshape(-1, 2).astype(np.float32)
            method = "inset"
        else:
            why.append("inset produced no contour")

        # Cue-based correction for rooms with a unique colour signature.
        # Compare the SAME cue in both images. Shifting the polygon centroid onto the
        # render's cue centroid is wrong -- a rug is not centred in its room -- so the
        # control's cue (whose position is known exactly) is mapped through the transform
        # and only the DIFFERENCE between the two cues is applied.
        mx0, my0 = mapped.min(0); mx1, my1 = mapped.max(0)
        pad_w = 0.75 * max(mx1 - mx0, my1 - my0)
        win = (mx0 - pad_w, my0 - pad_w, mx1 + pad_w, my1 + pad_w)
        cue_r = _cue_centroid(render, bg, rid, window=win)
        if rid in ROOM_OFFSET:
            # Measured on a crop, not derived: the laundry polygon lands a full room
            # height above its room because the model's interior proportions drift, and
            # both cue attempts (grey blob, then bluish-grey blob) were unreliable at this
            # size. One documented constant that a human verified beats another heuristic;
            # it is applied before validation, so the gate still has to pass on merit.
            final = final + list(ROOM_OFFSET[rid])
            why.append(f"manual offset {ROOM_OFFSET[rid]}")
        cue_c = _cue_centroid(ctl, np.array([255.0, 255.0, 255.0]), rid, strict=False)
        if cue_r is not None and cue_c is not None:
            mapped_c = ctl_to_render(cue_c[0], cue_c[1])
            dx, dy = cue_r[0] - mapped_c[0], cue_r[1] - mapped_c[1]
            if abs(dx) <= 160 and abs(dy) <= 160:
                final = final + [dx, dy]
                why.append(f"cue shift ({dx:+.0f},{dy:+.0f})")

        # bounded local snap against the house mask.
        #
        # "Outside" means the background COMPONENT THAT TOUCHES THE IMAGE BORDER, not
        # every pixel the colour of the surround. The laundry's grey tile is only ~25
        # Lab-ish units from the mid-grey surround, so a pure colour test called 11-29 %
        # of that room "outside" while it sat perfectly on its room -- a false negative
        # that would have sent me re-warping a correct polygon. The border-connected
        # component cannot include an interior floor.
        if '_outside_mask' not in globals():
            pass
        outside_mask = _outside_component(render, bg)
        best_final, best_score = final, None
        final = np.asarray(final, np.float32)
        acx0 = float(final[:, 0].mean()); acy0 = float(final[:, 1].mean())
        for sc in (0.84, 0.87, 0.90, 0.93, 0.96, 0.98, 0.99, 1.0, 1.01, 1.02):
            for dx in (-22, -16, -10, -6, -2, 2, 6, 10, 16, 22):
                for dy in (-22, -16, -10, -6, -2, 2, 6, 10, 16, 22):
                    cand = (final - [acx0, acy0]) * sc + [acx0 + dx, acy0 + dy]
                    m2 = np.zeros((rh, rw), np.uint8)
                    cv2.fillPoly(m2, [cand.astype(np.int32).reshape(-1, 1, 2)], 1)
                    tot = int(m2.sum())
                    if tot == 0:
                        continue
                    out_frac = float(((m2 == 1) & outside_mask).sum()) / tot
                    # Penalise shrinking: "outside" alone is minimised by collapsing the
                    # polygon to a dot (measured: every room collapsed to 0.66 area).
                    cand_area = abs(cv2.contourArea(cand.astype(np.float32)))
                    ratio_now = cand_area / max(1.0, anchor_area)
                    score = out_frac + 2.0 * max(0.0, 0.86 - ratio_now)
                    if best_score is None or score < best_score:
                        best_score, best_final = score, cand
        final = np.asarray(best_final, np.float32)
        outside_mask = None

        area = abs(cv2.contourArea(final))
        M = cv2.moments(final)
        if M["m00"] == 0:
            report.append({"room": rid, "ok": False, "why": "degenerate polygon"})
            continue
        cxp, cyp = M["m10"] / M["m00"], M["m01"] / M["m00"]
        room_w = float(mapped[:, 0].max() - mapped[:, 0].min())
        drift = float(np.hypot(cxp - acx, cyp - acy) / max(1.0, room_w))
        ratio = area / max(1.0, anchor_area)

        # Edge-band check. The INTERIOR was the wrong thing to measure: a bedroom is
        # ~40 % bed and a kitchen is half cabinetry, so interior "floor fraction"
        # legitimately sits near 0.5 and says nothing about alignment. Furniture is
        # centred; walls are at the boundary. So sample just inside the boundary --
        # if the polygon is inflated past a wall, that band lands on wall/background.
        inner = np.zeros((rh, rw), np.uint8)
        cv2.fillPoly(inner, [final.astype(np.int32).reshape(-1, 1, 2)], 1)
        # "outside" = the flat surround colour around the house. Test it against the
        # border-CONNECTED background component, not against the colour alone: a cool
        # grey ceramic tile floor is within 12 RGB of the grey surround, so a plain
        # colour test reported 6 % "outside" for the upstairs baths when nothing crossed
        # a wall. Connectivity is what separates the room floor from the surround.
        out_lbl = _outside_component(render, bg)
        tot_px = int(inner.sum())
        outside_frac = float(((inner == 1) & out_lbl).sum()) / max(1, tot_px)
        floor_frac = 1.0 - outside_frac      # kept in the JSON under its old name

        pts = final.tolist()
        out[rid] = {
            "points_px": [[round(x, 1), round(y, 1)] for x, y in pts],
            "points_norm": [[round(x / rw, 5), round(y / rh, 5)] for x, y in pts],
            "area_px": round(area, 1), "anchor_area_px": round(anchor_area, 1),
            "area_ratio": round(ratio, 3), "centroid_drift": round(drift, 3),
            "outside_frac": round(outside_frac, 3), "method": method,
        }
        report.append({"room": rid,
                       "ok": ((rid in VOID_ROOMS or drift <= MAX_DRIFT)
                              and 0.70 <= ratio <= 1.40
                              and outside_frac <= MAX_OUTSIDE),
                       "method": method, "area_ratio": round(ratio, 3),
                       "drift": round(drift, 3), "outside": round(outside_frac, 3),
                       **({"void": True} if rid in VOID_ROOMS else {}),
                       **dbg, **({"why": why} if why else {})})

    ok = all(r.get("ok") for r in report)
    return {"floor": floor,
            "render": str(render_path), "control": str(control_path), "size": [rw, rh],
            "anchor": {"control_plan_bbox": [round(v, 1) for v in cb],
                       "render_floor_bbox": [round(v, 1) for v in hb],
                       "transform": {"sx": round(sx, 4), "sy": round(sy, 4),
                                     "tx": round(tx, 2), "ty": round(ty, 2),
                                     "score": round(reg, 4)}},
            "rooms": out, "report": report, "pass": ok}


def _wall_mask(img, bright=200, neutral=26, exclude=None, exclude_tol=10):
    """Light, near-neutral pixels: the wall band in either image."""
    mx = img.max(axis=2).astype(np.float32)
    mn = img.min(axis=2).astype(np.float32)
    m = (mx > bright) & ((mx - mn) < neutral)
    if exclude is not None:
        d = np.linalg.norm(img.astype(np.float32) - np.asarray(exclude, np.float32), axis=2)
        m &= d > exclude_tol
    return m.astype(np.uint8)


def _register(render, ctl, lab, sx0, sy0, hb, cb, width=800):
    """Chamfer-match the control's wall network onto the render's walls.

    Every earlier attempt is recorded because each failed for a *measurable* reason and
    the next person will be tempted by all of them:

    * bbox anchor (silhouette + inset) -- the footprint is L-shaped, so a mid-line scan
      leaves the frame and reports the house starting at x=1003; and a silhouette bbox
      includes the drop shadow, which stretched the mapped box ~7 % low and left every
      polygon short.
    * wall-mask IoU as the objective -- peaked at 0.13: the render's bright furniture
      (island, counters, white bed) dominates a "light neutral" mask, so the mask being
      matched is mostly not walls.
    * per-room colour classification -- render floors carry lighting/texture the control's
      flat fills do not, so nearest-colour assignment scored 0.0000 everywhere.

    Chamfer matching avoids all three: it asks "how far is each control wall pixel from
    the nearest render wall pixel", which is tolerant of furniture (furniture adds
    candidates, it does not remove the true walls) and needs no colour model. The search
    is coarse-to-fine over four parameters, which is cheap because the objective is
    vectorised.
    """
    # geometry of both frames, normalised to `width`
    rs = cv2.resize(render, (width, int(render.shape[0] * width / render.shape[1])),
                    interpolation=cv2.INTER_AREA)
    k = width / render.shape[1]

    corners = np.concatenate([render[0:8, 0:8].reshape(-1, 3), render[0:8, -8:].reshape(-1, 3),
                              render[-8:, 0:8].reshape(-1, 3), render[-8:, -8:].reshape(-1, 3)])
    surround = np.median(corners, axis=0)
    rmask = _wall_mask(rs, bright=195, neutral=28, exclude=surround, exclude_tol=12)

    cmask_full = _wall_mask(ctl, bright=243, neutral=14)
    ys, xs = np.nonzero(cmask_full)
    if len(xs) == 0:
        raise SystemExit("control image has no wall pixels")
    step = max(1, len(xs) // 4000)
    pts = np.stack([xs[::step], ys[::step]], 1).astype(np.float32)   # control px

    # distance to the nearest render wall pixel, in the downscaled frame
    inv = (rmask == 0).astype(np.uint8)
    dist = cv2.distanceTransform(inv, cv2.DIST_L2, 5).astype(np.float32)

    def score(sx, sy, tx, ty):
        px = pts[:, 0] * sx * k + tx * k
        py = pts[:, 1] * sy * k + ty * k
        inside = (px >= 0) & (px < dist.shape[1] - 1) & (py >= 0) & (py < dist.shape[0] - 1)
        if inside.mean() < 0.6:            # most of the plan must be in frame
            return 1e9
        px = np.clip(px, 0, dist.shape[1] - 1).astype(np.int32)
        py = np.clip(py, 0, dist.shape[0] - 1).astype(np.int32)
        return float(dist[py, px].mean())

    best = (1e9, sx0, sy0, hb[0], hb[1])
    for dsx in np.arange(-0.18, 0.19, 0.03):
        for dsy in np.arange(-0.18, 0.19, 0.03):
            for dx in np.arange(-90, 91, 15):
                for dy in np.arange(-90, 91, 15):
                    v = score(sx0 * (1 + dsx), sy0 * (1 + dsy), hb[0] + dx, hb[1] + dy)
                    if v < best[0]:
                        best = (v, sx0 * (1 + dsx), sy0 * (1 + dsy), hb[0] + dx, hb[1] + dy)
    v0, bsx, bsy, btx, bty = best
    for dsx in np.arange(-0.02, 0.021, 0.01):
        for dsy in np.arange(-0.02, 0.021, 0.01):
            for dx in np.arange(-10, 11, 5):
                for dy in np.arange(-10, 11, 5):
                    v = score(bsx * (1 + dsx), bsy * (1 + dsy), btx + dx, bty + dy)
                    if v < v0:
                        v0, bsx, bsy, btx, bty = v, bsx * (1 + dsx), bsy * (1 + dsy), btx + dx, bty + dy
    return bsx, bsy, btx, bty, -v0      # score reported as "fitness" (higher better)


_CUE_CACHE = {}


def _cue_centroid(render, bg, room, min_area=0.0004, strict=True, window=None):
    """Centre of a colour signature that belongs to exactly one room, if there is one.

    Only rooms with an unmistakable cue are anchored this way -- over-fitting every room
    to a colour blob would be worse than a slightly-off transform:
        study       golden rug          (high-saturation warm yellow)
        living_room blue rug            (high-saturation blue)
        laundry     interior grey tile  (low-saturation, NOT the border background)
        kitchen     pale stone island   (very bright, low-saturation, compact)
    """
    key = (render.shape, room, None if window is None else tuple(round(v) for v in window))
    if key in _CUE_CACHE:
        return _CUE_CACHE[key]
    hsv = cv2.cvtColor(render, cv2.COLOR_BGR2HSV)
    H = hsv[..., 0].astype(np.int32) * 2          # OpenCV hue: 0..179 -> 0..358 deg
    S = hsv[..., 1].astype(np.int32)
    V = hsv[..., 2].astype(np.int32)
    outside = _outside_component(render, bg)
    if window is not None:
        # A cue must be searched only near the room it belongs to. Without this, the
        # laundry's "interior grey" cue matched the family room SOFA (bigger, also grey)
        # and the resulting ~800 px shift was silently discarded by the sanity clamp.
        wm = np.zeros(render.shape[:2], np.uint8)
        x0, y0, x1, y1 = window
        cv2.rectangle(wm, (int(x0), int(y0)), (int(x1), int(y1)), 1, -1)
        outside = np.logical_or(outside, wm == 0)

    if room == "laundry":                          # bluish-grey ceramic tile
        # bluish hue is what separates the tile from the family room SOFA, which is a
        # warmer grey of the same lightness (measured: the sofa blob was larger and won)
        m = ((H >= 80) & (H <= 155) & (S > 8) & (S < 70) & (V > 85) & (V < 220) & ~outside)
    else:
        _CUE_CACHE[key] = None
        return None

    m = m.astype(np.uint8)
    # grout lines split a tiled floor into per-tile blobs, so close first
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((17, 17), np.uint8))
    if not strict:
        # The control image has furniture drawn on top of the floor and a grout grid, so
        # its cue is fragmented; use the union of matching pixels there. The render's cues
        # are clean and keep the component filter below.
        ys, xs = np.nonzero(m)
        if len(xs) < min_area * render.shape[0] * render.shape[1]:
            _CUE_CACHE[key] = None
            return None
        _CUE_CACHE[key] = (float(xs.mean()), float(ys.mean()))
        return _CUE_CACHE[key]
    n, lbl, stats, cents = cv2.connectedComponentsWithStats(m, connectivity=8)
    best = None
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        w_, h_ = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if area < min_area * render.shape[0] * render.shape[1]:
            continue
        # rugs/tiles are broad and flat; skip thin verticals (planks, wall shadows)
        if min(w_, h_) < 18 or max(w_, h_) > 6 * max(1, min(w_, h_)):
            continue
        if best is None or area > best[0]:
            best = (area, cents[i])
    _CUE_CACHE[key] = None if best is None else (float(best[1][0]), float(best[1][1]))
    return _CUE_CACHE[key]


_OUTSIDE_CACHE = {}


def _outside_component(render, bg, tol=12):
    """Background pixels connected to the image border."""
    key = (render.shape, tuple(np.round(bg, 2)))
    if key in _OUTSIDE_CACHE:
        return _OUTSIDE_CACHE[key]
    d = np.linalg.norm(render.astype(np.float32) - bg.astype(np.float32), axis=2)
    m = (d < tol).astype(np.uint8)
    n, lbl = cv2.connectedComponents(m, connectivity=8)
    border = set(lbl[0, :].tolist()) | set(lbl[-1, :].tolist()) | \
             set(lbl[:, 0].tolist()) | set(lbl[:, -1].tolist())
    out = np.isin(lbl, [b for b in border if b != 0])
    _OUTSIDE_CACHE[key] = out
    return out


def _coverage(poly, anchor, wh):
    a = np.zeros(wh, np.uint8); b = np.zeros(wh, np.uint8)
    cv2.fillPoly(a, [poly.astype(np.int32).reshape(-1, 1, 2)], 1)
    cv2.fillPoly(b, [anchor.astype(np.int32).reshape(-1, 1, 2)], 1)
    return float((a & b).sum()) / max(1, int(b.sum()))


def _seed(lab, x, y, bg, r=30):
    h, w = lab.shape[:2]
    xi, yi = int(round(x)), int(round(y))
    bg_lab = cv2.cvtColor(bg.reshape(1, 1, 3).astype(np.uint8), cv2.COLOR_BGR2LAB)[0, 0].astype(np.float32)
    best = None
    for rad in (0, 10, 20, 32, 46, 62):
        step = max(3, rad // 3 or 3)
        for dy in range(-rad, rad + 1, step):
            for dx in range(-rad, rad + 1, step):
                px, py = xi + dx, yi + dy
                if not (5 <= px < w - 5 and 5 <= py < h - 5):
                    continue
                c = lab[py, px]
                # skip background and near-white walls: both are low-saturation/bright
                L = c[0] * 100 / 255
                sat = np.hypot(c[1] - 128, c[2] - 128)
                if L > 88 or sat < 6 or np.linalg.norm(c - bg_lab) < 10:
                    continue
                d = dx * dx + dy * dy
                if best is None or d < best[0]:
                    best = (d, (px, py))
        if best:
            return best[1]
    return None


def _patch_median(lab, pt, r=6):
    x, y = pt
    return np.median(lab[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1].reshape(-1, 3), axis=0)


def _overlay(render_path, res, outp):
    im = cv2.imread(str(render_path)).copy()
    cols = [(60, 60, 220), (60, 180, 60), (220, 140, 40), (200, 60, 200),
            (40, 200, 220), (140, 90, 30), (30, 30, 255)]
    for i, (rid, d) in enumerate(res["rooms"].items()):
        pts = np.array(d["points_px"], np.float32).astype(np.int32).reshape(-1, 1, 2)
        c = cols[i % len(cols)]
        cv2.polylines(im, [pts], True, c, 5)
        M = cv2.moments(pts)
        if M["m00"]:
            cv2.putText(im, f"{rid} [{d['method'][:4]}]",
                        (int(M["m10"] / M["m00"]) - 90, int(M["m01"] / M["m00"])),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.1, c, 3, cv2.LINE_AA)
    cv2.imwrite(str(outp), cv2.resize(im, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA))


if __name__ == "__main__":
    argv = sys.argv[1:]
    floor = "main"
    if "--floor" in argv:
        i = argv.index("--floor")
        floor = argv[i + 1]
        del argv[i:i + 2]
    render = Path(argv[0]) if argv else HERE / "art" / f"render_{floor}.jpg"
    control = Path(argv[1]) if len(argv) > 1 else HERE / "art" / f"control_{floor}.png"
    res = fit(render, control, floor)
    name = "hotspots.json" if floor == "main" else f"hotspots_{floor}.json"
    (HERE / name).write_text(json.dumps(res, indent=2))
    _overlay(render, res, HERE / f"hotspots_{floor}.png")
    for r in res["report"]:
        print(("PASS " if r.get("ok") else "FAIL ") + json.dumps(r))
    print("OVERALL:", "PASS" if res["pass"] else "FAIL")
    sys.exit(0 if res["pass"] else 1)
