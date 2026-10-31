#!/usr/bin/env python3
"""Generate the cartoon/dollhouse floorplan render from the control plan.

Pipeline position:
    geometry.py -> make_control_image.py -> [this] -> fit_hotspots.py -> render_card_svg.py

The model is instructed to RESTYLE the supplied layout, not to invent one. Any
layout freedom it takes is a defect, because every hotspot polygon is derived from
the measured coordinates and validated against the render (see fit_hotspots.py).

Usage:
    python3 generate_art.py [--model gemini-3-pro-image] [--out art/render.png]

Requires GOOGLE_API_KEY in /root/.hermes/.env. Writes the raw response JSON next to
the image so a failed generation can be diagnosed without re-billing a call.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

import requests

HERE = Path(__file__).resolve().parent
ENV = Path("/root/.hermes/.env")

PROMPT = """\
Redraw the supplied flat floor plan as a high-quality 3D architectural "dollhouse"
visualisation, in the style of a Floorplanner top-down render.

CAMERA
- Viewed from directly above with a very slight tilt, orthographic projection.
- NOT a wide-angle perspective. NOT a 45-degree isometric.

WALLS
- Light warm grey (#E8E5DF) with visible thickness of about 12 cm, tops slightly
  lighter. The outer wall is continuous.
- Interior walls follow the white wall bands in the input exactly.
- OPENINGS. These must be open gaps with floor running continuously through them,
  not walls: between the family room (top-left) and the kitchen (top-centre); between
  the kitchen and the central hall below it; between the kitchen and the dining room
  (top-right); and between the living room (bottom-right) and the central hall.
- DOORWAYS with a visible door: one in the NORTH outside wall at the kitchen's west
  end (the kitchen door), and one in the SOUTH outside wall of the central hall
  (the front door).

FLOORS
- Every room is MEDIUM BROWN WOOD PLANK flooring -- the same warm medium brown
  throughout, with visible plank lines and a subtle grain. The GARAGE is the one
  exception besides the laundry: it has plain GREY CONCRETE.
- The only tiled floor in the whole plan is the laundry. Of the two small rooms on
  the left of the hall, the laundry is the UPPER one -- the room containing the white
  washer and dryer, directly below the hall's upper arm. Its floor is COOL GREY
  CERAMIC TILE with a visible square grid of grout lines.
- The bathroom is the LOWER of the two small rooms -- the one with the toilet, basin
  and glass shower, below the laundry. Its floor is MEDIUM BROWN WOOD, like every
  other room. Do not tile the bathroom.
- Do NOT create an extra tiled room. The hall floor is wood right up to the
  laundry's walls. The laundry is a single small room; do not split it in two and do
  not extend its tile into the hall.

FURNITURE, by room. Match these positions exactly; do not add large items that are
not listed, and do not remove listed items.

Top-left room (family room):
- A FIREPLACE with a stone surround and a dark firebox on the LEFT (west) wall,
  centred vertically.
- TWO BLUE ARMCHAIRS side by side along the NORTH (top) edge, facing south.
- A GREY SOFA along the SOUTH (bottom) edge, facing north.
- A GOLDEN / OCHRE area RUG in the centre, between the chairs and the sofa.

Between the family room and the kitchen:
- A WOODEN KITCHEN TABLE spanning the open boundary between the two rooms, with
  two chairs; it sits in the opening, half in the family room, half in the kitchen.

Top-centre room (kitchen):
- A white counter run along the NORTH wall starting east of the kitchen door, with a
  stainless sink, turning the corner and continuing DOWN THE EAST wall as an L.
- A pale stone KITCHEN ISLAND in the middle of the room, roughly centred, with a
  clear walkway around it.
- A stainless FRIDGE standing against the SOUTH wall of the kitchen, to the east of
  the opening to the hall.

Top-right room (dining room):
- A wooden dining table with a chair on its west and east sides.

Central hall (foyer):
- A stair flight in the upper-right of the hall whose steps ascend toward the EAST
  (the treads run north-south, and the flight rises to the right). A slim wooden
  console table against the hall's west wall. Keep the rest of the hall floor clear.

Small middle-left room (laundry):
- A white washer and a white dryer side by side against the north wall of that room.

Small lower-left room (bathroom):
- A white toilet, a white basin with a small counter, and a glass shower enclosure.

Garage (the large bottom-left room, below the family room, bare concrete):
- Grey concrete floor with a faint swept texture, and a visible floor slab edge.
- TWO OVERHEAD SECTIONAL GARAGE DOORS in the SOUTH wall, side by side, closed, with
  horizontal panel lines.
- ONE INTERIOR DOOR in the EAST wall near the top, opening into the house, with a step up.
- ONE EXTERIOR PEDESTRIAN DOOR in the WEST wall, mid-height.
- WOODEN SHELVING UNITS along the NORTH wall (the side nearest the family room), and TWO
  BICYCLES leaning/standing beside them against the same wall.
- Nothing else: no cars, no workbench, no boxes scattered on the floor.

Bottom-right room (living room):
- A BLUE area RUG in the centre.
- A tall wooden BOOKSHELF against the RIGHT (east) wall.
- TWO SMALL BLUE CHAIRS side by side at the SOUTHERN (bottom) end, facing north.
- No sofa in this room.

LIGHTING
- Bright, even daylight. Soft ambient occlusion in corners, gentle contact shadows
  under furniture. No harsh spotlights, no sunbeams across the floor.

FINISH
- Clean stylised realism, slightly softened edges, like a polished mobile game
  interior. NOT photorealistic, NOT a sketch, NOT cel-shaded with heavy black
  outlines.

EXCLUDE
- Absolutely no text, no labels, no numbers, no UI, no people, no pets, no plants
  outside the rooms, no watermark, no border, no vignette, no grass or landscape
  around the house.

FRAMING AND PROPORTIONS
- Keep the whole plan inside the frame with a small even margin, and keep every
  room's footprint, proportions and position identical to the input. Do not merge,
  split, add or remove rooms.
- The house is an irregular L-shaped footprint: the lower-left quadrant is OUTSIDE the
  house. Keep that area empty -- flat neutral background, no floor, no furniture, no
  shadow. Do not stretch or rearrange rooms to fill it, and do not change the relative
  width of one room against another.
"""


PROMPT_TAIL = """\
LIGHTING
- Bright, even daylight. Soft ambient occlusion in corners, gentle contact shadows
  under furniture. No harsh spotlights, no sunbeams across the floor.

FINISH
- Clean stylised realism, slightly softened edges, like a polished mobile game
  interior. NOT photorealistic, NOT a sketch, NOT cel-shaded with heavy black
  outlines.

EXCLUDE
- Absolutely no text, no labels, no numbers, no UI, no people, no pets, no plants
  outside the rooms, no watermark, no border, no vignette, no grass or landscape
  around the house.

FRAMING AND PROPORTIONS
- Keep the whole plan inside the frame with a small even margin, and keep every
  room's footprint, proportions and position identical to the input. Do not merge,
  split, add or remove rooms.
"""

PROMPT_UPPER = """\
Redraw the supplied flat floor plan as a high-quality 3D architectural "dollhouse"
visualisation, in the style of a Floorplanner top-down render. This is the UPPER
STOREY (second floor) of a two-storey house.

CAMERA
- Viewed from directly above with a very slight tilt, orthographic projection.
- NOT a wide-angle perspective. NOT a 45-degree isometric.

WALLS
- Light warm grey (#E8E5DF) with visible thickness of about 12 cm, tops slightly
  lighter. The outer wall is continuous.
- Interior walls follow the white wall bands in the input exactly.
- Every room boundary that shows a small brown door leaf in the input has a real
  DOORWAY with a visible door panel, slightly ajar: master bedroom to hall, hall to
  the shared bath, hall to the top-right bedroom, hall to each of the two
  south bedrooms, master bedroom to its bath, and the open cased arch from the master
  bedroom into the wardrobe room.

ROOF -- THIS IS THE MOST IMPORTANT PART
- The grey hatched area along the LEFT side and the BOTTOM-LEFT of the input is the
  sloped asphalt-shingle ROOF over the single-storey garage below.
- Render it as an EXTERIOR roof plane: visible horizontal shingle courses, a ridge
  and a fascia edge where it meets the house wall, and a low knee wall where the
  upper storey rises above it.
- It is NOT a room. No floor, no walls, no furniture, no railing on it, no shadow
  cast into the rooms. Do not tile it and do not put anything on it.

FLOORS
- Every room has MEDIUM BROWN WOOD PLANK flooring, the same warm medium brown
  throughout, with visible plank lines.
- The two BATHROOMS are the only tiled rooms: COOL GREY CERAMIC TILE with a visible
  square grid of grout lines. The master bath is the top-left room; the shared bath is
  the small room between the master bedroom and the top-right bedroom.
- The wardrobe room (directly below the master bath, on the left) is wood, with runs
  of open hanging rails and shelving on two of its walls.

FURNITURE, by room. Match these positions exactly; do not add large items that are
not listed, and do not remove listed items.

Top band, left to right:

1. Master bath (top-left, tiled):
- A white freestanding TUB along the left (west) wall, running north-south.
- A VANITY with a white basin against the north wall, to the right of the tub.
- A white TOILET below the vanity, against the same wall.
- A glass SHOWER enclosure in the bottom-left corner of the room.

2. Master bedroom (top band, second from the left -- the largest north room):
- A KING BED centred against the NORTH wall, beige/cream linen, two pillows.
- A wooden NIGHTSTAND on each side of the bed.
- A wooden DRESSER against the RIGHT (east) wall, mid-height.
- A grey ARMCHAIR in the bottom-left corner of the room.

3. Shared bath (small room, top band, third from the left):
- A white TUB across the NORTH end.
- A VANITY with basin and a white TOILET side by side along the south half.

WALL ALIGNMENT -- CHECK THIS CAREFULLY
- The wardrobe room sits directly BELOW the master bath and has EXACTLY THE SAME
  width and the same left and right walls as the master bath. The wall between the
  master bath and the wardrobe room is one straight horizontal line, and the east wall
  of both rooms is one continuous straight vertical line. There is NO step or jog in
  that wall.
- The landing therefore starts at that same vertical line and runs east to the
  stairwell. Its west end is straight, not stepped.

4. Bedroom, top-right corner:
- A SINGLE BED with BLUE bedding set against the north-west corner, head to the north.
- A wooden DESK against the right (east) wall.
- A wooden DRESSER at the bottom-left of the room.

Middle band, full width (the LANDING / upstairs hall):
- A STAIR FLIGHT at the RIGHT (east) end: horizontal treads, a handrail on the open
  side, descending toward the south. The stairwell opening is a real void with a
  railing around it.
- A slim wooden CONSOLE table against the left end of the landing. Keep the rest of
  the landing floor clear.

Bottom band, left to right:

5. Bedroom, bottom-left:
- A SINGLE BED with GOLDEN / OCHRE bedding, head against the left (west) wall.
- A wooden DESK against the right (east) wall of the room.
- A low wooden DRESSER along the bottom wall.

6. The narrow shaft between the two south bedrooms:
- It is OPEN TO THE STOREY BELOW. Show a short stretch of light-oak railing along its
  top edge and leave the shaft itself empty and in shadow. Do not floor it over.

7. Bedroom, bottom-right (the largest south room):
- A SINGLE BED with GREY bedding, head against the left (west) wall.
- A wooden DESK against the right (east) wall.
- A wooden DRESSER in the bottom-right corner.

""" + PROMPT_TAIL + """\
The storey is an irregular L-shaped plate: the hatched left / bottom-left area is
outside the upper floor (it is roof, see above). Do not stretch or rearrange rooms to
fill it, and do not change the relative width of one room against another.
"""

PROMPT_LOWER = """\
Redraw the supplied flat floor plan as a high-quality 3D architectural "dollhouse"
visualisation, in the style of a Floorplanner top-down render. This is the BASEMENT
(walk-out lower level) of a two-storey house. The garage is on THIS level.

CAMERA
- Viewed from directly above with a very slight tilt, orthographic projection.
- NOT a wide-angle perspective. NOT a 45-degree isometric.

WALLS
- Light warm grey (#E8E5DF) with visible thickness of about 12 cm, tops slightly
  lighter. The outer wall is continuous.
- Interior walls follow the white wall bands in the input exactly.
- The big recreation room opens onto the media room on its left with a wide cased
  OPENING and no door; everything else has a real DOORWAY with a visible door panel:
  the bath, the utility room, the office and the door from the garage into the house.
- TWO OVERHEAD SECTIONAL GARAGE DOORS in the SOUTH wall of the garage, side by side,
  closed, with horizontal panel lines.
- ONE EXTERIOR PEDESTRIAN DOOR in the garage's west wall.

FLOORS
- The MEDIA ROOM and the RECREATION ROOM have MEDIUM BROWN WOOD PLANK flooring, the
  same warm medium brown, with visible plank lines.
- The OFFICE / STUDY is the same wood.
- The GARAGE is plain GREY CONCRETE with a faint swept texture and a slab edge.
- The UTILITY ROOM is sealed grey concrete, slightly darker and plainer than the
  garage.
- The BATHROOM is COOL GREY CERAMIC TILE with a visible square grid of grout lines.

FURNITURE, by room. Match these positions exactly; do not add large items that are
not listed, and do not remove listed items.

1. Media room (top-left):
- A dark SCREEN / projection wall along the NORTH wall, the full width of the room.
- TWO GREY RECLINING SOFAS in two rows, both facing north toward the screen.
- A BLUE area rug under the seating.
- A wooden shelf unit against the RIGHT (east) wall of the room.

2. Recreation room (top-right -- the large open room, it wraps around to the right
   of the media room and down the right-hand side):
- A POOL TABLE with green felt, roughly centred in the north part of the room.
- A GREY SOFA against the north wall, to the east of the pool table.
- A BLUE ARMCHAIR in the south-west of the room.
- A GOLDEN / OCHRE rug under the pool table.

3. Office / study (right-hand side, below the recreation room):
- A wooden DESK against the north wall of the room with an office chair.
- A tall wooden BOOKSHELF against the east wall.

4. Utility room (bottom-centre):
- A white WATER HEATER cylinder, a grey FURNACE, and a white CHEST FREEZER along the
  north side of the room, with a run of wooden shelving below them.

5. Bathroom (small room between the recreation room and the utility room):
- A white TUB, a white TOILET and a white BASIN with a small counter.

6. GARAGE (large bottom-left room, bare concrete):
- TWO CARS parked side by side, nose toward the south doors.
- A run of WOODEN SHELVING along the bottom (south) wall beside the doors.
- Nothing else: no workbench, no boxes scattered on the floor, no bicycles.

7. The hall / corridor band along the bottom of the plan and the short corridor
   beside the bath: keep the floor CLEAR.

""" + PROMPT_TAIL

PROMPTS = {"main": PROMPT, "upper": PROMPT_UPPER, "lower": PROMPT_LOWER}


def api_key() -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith("GOOGLE_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GOOGLE_API_KEY not found in /root/.hermes/.env")


def generate(model: str, control: Path, out: Path, aspect: str = "4:3",
             size: str | None = None, floor: str = "main") -> dict:
    b64 = base64.b64encode(control.read_bytes()).decode()
    body = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": PROMPTS[floor]},
                {"inline_data": {"mime_type": "image/png", "data": b64}},
            ],
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": ({"aspectRatio": aspect, "imageSize": size}
                            if size else {"aspectRatio": aspect}),
        },
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent?key={api_key()}")
    r = requests.post(url, json=body, timeout=300)
    out.parent.mkdir(parents=True, exist_ok=True)
    raw = out.with_suffix(".response.json")
    raw.write_text(r.text[:200000])
    if r.status_code != 200:
        raise SystemExit(f"HTTP {r.status_code}: {r.text[:600]}")

    data = r.json()
    parts = (data.get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    imgs = [p for p in parts if "inlineData" in p or "inline_data" in p]
    if not imgs:
        raise SystemExit(f"no image in response; text parts: "
                         f"{[p.get('text','')[:200] for p in parts]}")
    blob = imgs[0].get("inlineData") or imgs[0].get("inline_data")
    mime = blob.get("mimeType") or blob.get("mime_type") or "image/png"
    # The model returns JPEG even when asked for PNG. Rename the target to match
    # the real payload -- a .png file holding JPEG bytes breaks tooling that
    # trusts the extension (and it already fooled one viewer).
    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime, ".png")
    out = out.with_suffix(ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(base64.b64decode(blob["data"]))
    return {"model": model, "floor": floor, "out": str(out),
            "bytes": out.stat().st_size, "mime": mime}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.1-flash-image")
    ap.add_argument("--floor", default="main", choices=["main", "upper", "lower"])
    ap.add_argument("--control", default=None,
                    help="defaults to art/control_<floor>.png")
    ap.add_argument("--out", default=None, help="defaults to art/render_<floor>.png")
    ap.add_argument("--aspect", default="4:3")
    ap.add_argument("--size", default=None, help="1K | 2K | 4K (model permitting)")
    a = ap.parse_args()
    control = Path(a.control) if a.control else HERE / "art" / f"control_{a.floor}.png"
    out = Path(a.out) if a.out else HERE / "art" / f"render_{a.floor}.png"
    print(json.dumps(generate(a.model, control, out, a.aspect, a.size, a.floor), indent=2))
