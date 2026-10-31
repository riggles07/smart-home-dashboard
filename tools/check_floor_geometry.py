#!/usr/bin/env python3
"""Validate the floor layers: no overlaps, full tiling, every room inside bounds.

A dashboard layer that overlaps its neighbour produces two hotspots on the same
pixel: the top one wins and the other room becomes unreachable. A gap paints the
surround grey through the middle of a house. Both are cheap to catch here and
expensive to catch on the tablet.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "floorplan"))
sys.path.insert(0, str(HERE.parent / "floorplan" / "cartoon"))

from geometry import FLOOR_ROOMS, ROOF, bounds  # noqa: E402
import room_spec as spec  # noqa: E402


def area(poly):
    a = 0.0
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        a += x1 * y2 - x2 * y1
    return abs(a) / 2


def inside(poly, x, y):
    res = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            res = not res
        j = i
    return res


def check(floor, step=5):
    rooms = FLOOR_ROOMS[floor]
    bx0, by0, bx1, by1 = bounds()
    problems = []

    for rid, poly in rooms.items():
        for x, y in poly:
            if not (bx0 - 1 <= x <= bx1 + 1 and by0 - 1 <= y <= by1 + 1):
                problems.append(f"{floor}/{rid}: vertex {(x, y)} outside bounds")

    overlap, covered, covered_all, total = {}, 0, 0, 0
    roof = ROOF.get(floor, ())
    for x in range(bx0, bx1, step):
        for y in range(by0, by1, step):
            total += 1
            px, py = x + step / 2, y + step / 2
            hit = [rid for rid, poly in rooms.items() if inside(poly, px, py)]
            if len(hit) > 1:
                overlap[tuple(sorted(hit))] = overlap.get(tuple(sorted(hit)), 0) + 1
            elif hit:
                covered += 1
            if hit or any(inside(p, px, py) for p in roof):
                covered_all += 1
    for k, n in overlap.items():
        problems.append(f"{floor}: {n} sample points in two rooms at once: {k}")

    roof_area = sum(area(p) for p in ROOF.get(floor, ()))
    habitable = sum(area(p) for p in rooms.values())
    foot = (bx1 - bx0) * (by1 - by0)
    frac = covered / total if total else 0
    frac_all = covered_all / total if total else 0

    # a plate that leaves gaps shows up as grey through the house
    expected = (habitable + roof_area) / foot
    if abs(frac_all - expected) > 0.03:
        problems.append(
            f"{floor}: covered {frac_all:.1%} of the footprint but rooms+roof are "
            f"{expected:.1%} -- there is a gap between rooms")

    return {"floor": floor, "rooms": len(rooms), "covered": round(frac, 4),
            "covered_with_roof": round(frac_all, 4),
            "habitable_sqft_at_21": round(habitable / 441), "problems": problems}


if __name__ == "__main__":
    bad = 0
    for floor in FLOOR_ROOMS:
        r = check(floor)
        print(f"{floor:6s} rooms={r['rooms']:2d} covered={r['covered']:.1%} "
              f"~{r['habitable_sqft_at_21']} sqft")
        for p in r["problems"]:
            print("   !!", p)
            bad += 1
    sys.exit(1 if bad else 0)
