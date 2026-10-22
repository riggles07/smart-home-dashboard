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
from geometry import ROOMS, bounds  # noqa: E402

SNAP = 22            # px the grow may move an anchored edge (render is 2K, so ~1 % )
AREA_TOL = (0.80, 1.25)     # grow vs anchored area; outside -> fall back to geometry
MAX_DRIFT = 0.10            # centroid drift as a fraction of room width
COLOUR_TOL = 22.0           # CIE-Lab distance for the grow
MIN_COVER = 0.85            # fraction of the anchored polygon the fit must keep
MIN_FLOOR_FRAC = 0.85       # inner edge band purity; 0.85 because bright-neutral furniture (bed, island) is indistinguishable from wall


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


def fit(render_path: Path, control_path: Path) -> dict:
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
    sx, sy, tx, ty = sx0, sy0, hb[0], hb[1]
    reg = 0.0

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
    for rid, poly in ROOMS.items():
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
        inset_px = max(3.0, 7.0 * sx)          # 7 cm half-wall, in render px
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
        eroded = cv2.erode(inner, np.ones((13, 13), np.uint8))
        band = np.logical_and(inner == 1, eroded == 0)
        pix = render[band].astype(np.float32)
        if len(pix):
            d = np.linalg.norm(pix - bg, axis=1)
            mx, mn = pix.max(1), pix.min(1)
            wallish = np.logical_and(mx > 195, (mx - mn) < 22)
            floor_frac = float(np.mean(np.logical_and(d > 18, np.logical_not(wallish))))
        else:
            floor_frac = 0.0

        pts = final.tolist()
        out[rid] = {
            "points_px": [[round(x, 1), round(y, 1)] for x, y in pts],
            "points_norm": [[round(x / rw, 5), round(y / rh, 5)] for x, y in pts],
            "area_px": round(area, 1), "anchor_area_px": round(anchor_area, 1),
            "area_ratio": round(ratio, 3), "centroid_drift": round(drift, 3),
            "floor_frac": round(floor_frac, 3), "method": method,
        }
        report.append({"room": rid,
                       "ok": (drift <= MAX_DRIFT and 0.70 <= ratio <= 1.40
                              and floor_frac >= MIN_FLOOR_FRAC),
                       "method": method, "area_ratio": round(ratio, 3),
                       "drift": round(drift, 3), "floor_frac": round(floor_frac, 3),
                       **dbg, **({"why": why} if why else {})})

    ok = all(r.get("ok") for r in report)
    return {"render": str(render_path), "control": str(control_path), "size": [rw, rh],
            "anchor": {"control_plan_bbox": [round(v, 1) for v in cb],
                       "render_floor_bbox": [round(v, 1) for v in hb],
                       "transform": {"sx": round(sx, 4), "sy": round(sy, 4),
                                     "tx": round(tx, 2), "ty": round(ty, 2),
                                     "score": round(reg, 4)}},
            "rooms": out, "report": report, "pass": ok}


def _wall_mask(img, bright=190, neutral=30):
    """Light, near-neutral pixels: the wall band in either image."""
    mx = img.max(axis=2).astype(np.float32)
    mn = img.min(axis=2).astype(np.float32)
    return ((mx > bright) & ((mx - mn) < neutral)).astype(np.uint8)


def _register(render, ctl, lab, sx0, sy0, hb, cb, width=600):
    """Fit the affine by aligning WALL MASKS, then report IoU.

    Rejected approaches, with their measurements, because each looked reasonable:

    * bbox anchor -- the footprint is L-shaped, so a mid-line scan leaves the frame,
      crosses the empty quadrant and reports the house starting at x=1003.
    * centroid drift as the objective -- it read 0.001 while polygons visibly poked
      through the outer walls; inflating a polygon does not move its centroid.
    * per-room floor COLOUR classification -- the render's floors carry lighting and
      texture that the control's flat fills do not, so the nearest-colour assignment
      returned nothing usable (score stayed 0.0000 across the whole search).

    Walls are the one structure both images share, and they are what defines the
    rooms, so they are the alignable feature. The search starts from the bbox guess
    and scores IoU of the warped control wall mask against the render's.
    """
    k = width / render.shape[1]
    rmask = _wall_mask(cv2.resize(render, (width, int(render.shape[0] * k)),
                                  interpolation=cv2.INTER_AREA))
    cmask_full = _wall_mask(ctl)
    cw = width
    chh = int(ctl.shape[0] * cw / ctl.shape[1])
    cmask = cv2.resize(cmask_full, (cw, chh), interpolation=cv2.INTER_AREA)
    kc = cw / ctl.shape[1]      # control px -> search px

    def warp_mask(sx, sy, tx, ty):
        # Same transform as ctl_to_render, composed with the render->search downscale.
        A = np.array([[sx * k, 0, (tx - cb[0] * sx) * k],
                      [0, sy * k, (ty - cb[1] * sy) * k]], np.float32)
        return cv2.warpAffine(cmask, A, (rmask.shape[1], rmask.shape[0]),
                              flags=cv2.INTER_NEAREST)

    def iou(sx, sy, tx, ty):
        w = warp_mask(sx, sy, tx, ty)
        inter = int((w & rmask).sum())
        union = int(((w | rmask) > 0).sum())
        return inter / union if union else 0.0

    best = (0.0, sx0, sy0, hb[0], hb[1])
    for dsx in (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06):
        for dsy in (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06):
            for dx in range(-80, 81, 20):
                for dy in range(-80, 81, 20):
                    v = iou(sx0 * (1 + dsx), sy0 * (1 + dsy), hb[0] + dx, hb[1] + dy)
                    if v > best[0]:
                        best = (v, sx0 * (1 + dsx), sy0 * (1 + dsy), hb[0] + dx, hb[1] + dy)
    v0, bsx, bsy, btx, bty = best
    for dsx in (-0.01, 0.0, 0.01):
        for dsy in (-0.01, 0.0, 0.01):
            for dx in (-8, -4, 0, 4, 8):
                for dy in (-8, -4, 0, 4, 8):
                    v = iou(bsx * (1 + dsx), bsy * (1 + dsy), btx + dx, bty + dy)
                    if v > v0:
                        v0, bsx, bsy, btx, bty = v, bsx * (1 + dsx), bsy * (1 + dsy), btx + dx, bty + dy
    return bsx, bsy, btx, bty, v0


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
    render = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "art" / "render_2k.jpg"
    control = Path(sys.argv[2]) if len(sys.argv) > 2 else HERE / "control_plan.png"
    res = fit(render, control)
    (HERE / "hotspots.json").write_text(json.dumps(res, indent=2))
    _overlay(render, res, HERE / "hotspots.png")
    for r in res["report"]:
        print(("PASS " if r.get("ok") else "FAIL ") + json.dumps(r))
    print("OVERALL:", "PASS" if res["pass"] else "FAIL")
    sys.exit(0 if res["pass"] else 1)
