#!/usr/bin/env python3
"""Rectify the room photos to a straight-on ("looking in from the doorway") view.

THE PROBLEM
-----------
Both shots are handheld, from the doorway, wide-angle, and tilted: the camera is
rolled a few degrees and pitched down, so wall corners lean and the floor eats the
bottom third. Pasting that into a room polygon reads as a photo lying at an angle.

Picking four corners by hand is not available: in the laundry shot the left jamb is
hidden behind the open door and the sill is out of frame; in the bathroom shot the
shower curtain covers the back wall's lower-left corner. So this does what an
architectural photographer does instead -- it measures the room's own geometry:

  1. detect long straight edges (LSD),
  2. split them into near-vertical and near-horizontal,
  3. intersect the verticals -> the vertical vanishing point (least squares, SVD),
  4. build the homography that sends that point to infinity, so every vertical in
     the room becomes parallel and upright,
  5. rotate so the remaining lean is level, then crop to the room.

Nothing here is a guess about the room's dimensions: step 4 is exact given the
vanishing point, and the vanishing point is measured from the pixels.

Usage:
    python3 rectify_rooms.py <src-dir> <dst-dir> [room ...]

Output keeps the source filename so the normal build just points at the new dir.
"""
import os
import sys

import cv2
import numpy as np


def detect_segments(gray, min_len_frac=0.10):
    """Long straight edges, as ((x1,y1,x2,y2), angle_deg, length)."""
    h, w = gray.shape
    min_len = min_len_frac * min(h, w)
    g = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    lines = cv2.HoughLinesP(cv2.Canny(g, 50, 150), 1, np.pi / 180,
                            threshold=80, minLineLength=int(min_len),
                            maxLineGap=int(0.02 * min(h, w)))
    out = []
    if lines is None:
        return out
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        L = float(np.hypot(dx, dy))
        ang = np.degrees(np.arctan2(dy, dx)) % 180.0
        out.append(((x1, y1, x2, y2), ang, L))
    return out


def vertical_vanishing_point(segs, tol=22.0):
    """Least-squares intersection of the near-vertical lines, via SVD.

    Each line contributes a·x + b·y + c = 0. Stacking those and taking the
    smallest singular vector gives the point closest to all of them.
    """
    A = []
    for (x1, y1, x2, y2), ang, _L in segs:
        near_vertical = abs(ang - 90.0) < tol or ang > 180.0 - tol
        if not near_vertical:
            continue
        a, b = (y2 - y1), -(x2 - x1)          # normal of the line
        c = -(a * x1 + b * y1)
        n = np.hypot(a, b)
        A.append([a / n, b / n, c / n])
    if len(A) < 4:
        return None, 0
    _u, _s, vt = np.linalg.svd(np.asarray(A))
    vp = vt[-1]
    if abs(vp[2]) < 1e-9:
        return None, len(A)
    return (vp[0] / vp[2], vp[1] / vp[2]), len(A)


def rectify(im, vp, crop_frac=0.0):
    """Homography that sends vp to infinity along the vertical direction."""
    h, w = im.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    vx, vy = vp[0] - cx, vp[1] - cy
    d = float(np.hypot(vx, vy))

    # rotate so the vanishing point sits on the +y axis through the centre
    alpha = np.arctan2(vy, vx) - np.pi / 2
    ca, sa = np.cos(alpha), np.sin(alpha)

    def T(tx, ty):
        return np.array([[1, 0, tx], [0, 1, ty], [0, 0, 1]], float)

    R = np.array([[ca, -sa, 0], [sa, ca, 0], [0, 0, 1]], float)
    Ri = np.array([[ca, sa, 0], [-sa, ca, 0], [0, 0, 1]], float)
    # (0, d, 1) -> (0, d, 0): the point at infinity in the vertical direction
    Hpp = np.array([[1, 0, 0], [0, 1, 0], [0, -1.0 / d, 1.0]], float)
    H = T(cx, cy) @ Ri @ Hpp @ R @ T(-cx, -cy)

    corners = np.array([[0, 0, 1], [w, 0, 1], [w, h, 1], [0, h, 1]], float).T
    proj = H @ corners
    proj = (proj[:2] / proj[2]).T
    x0, y0 = proj.min(axis=0)
    x1, y1 = proj.max(axis=0)
    sx = w / (x1 - x0)
    sy = h / (y1 - y0)
    S = np.array([[sx, 0, -x0 * sx], [0, sy, -y0 * sy], [0, 0, 1]], float)
    M = S @ H
    return cv2.warpPerspective(im, M, (w, h), flags=cv2.INTER_CUBIC,
                                borderMode=cv2.BORDER_REPLICATE)


def main(src, dst, rooms):
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        room = os.path.splitext(name)[0]
        if not name.lower().endswith((".jpg", ".jpeg")):
            continue
        if rooms and room not in rooms:
            continue
        im = cv2.imread(os.path.join(src, name))
        gray = cv2.cvtColor(im, cv2.COLOR_BGR2GRAY)
        segs = detect_segments(gray)
        vp, n = vertical_vanishing_point(segs)
        if vp is None:
            print(f"{room}: only {n} vertical lines found -- copied unchanged")
            cv2.imwrite(os.path.join(dst, name), im)
            continue
        h, w = im.shape[:2]
        out = rectify(im, vp)
        cv2.imwrite(os.path.join(dst, name), out, [cv2.IMWRITE_JPEG_QUALITY, 96])
        print(f"{room}: {len(segs)} segments, {n} vertical -> vp "
              f"({vp[0]:.0f},{vp[1]:.0f}) [{vp[0]/w:+.2f}w {vp[1]/h:+.2f}h]")
        # how far the verticals leaned before: angle between vp and the centre line
        lean = np.degrees(np.arctan2(vp[0] - w / 2, vp[1] - h / 2))
        print(f"    vertical convergence {lean:+.2f} deg off-axis -> corrected")


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "/tmp/rooms_orig"
    dst = sys.argv[2] if len(sys.argv) > 2 else "/tmp/rooms_rect"
    main(src, dst, sys.argv[3:])
