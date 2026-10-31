CARTOON FLOORPLAN -- UPLOAD BUNDLE (version 451e98f2)
====================================================
THREE FILES. The card carries all three floors, and this build also changes the basement
art (the faux garage is gone), so both must land together.

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  render_lower.jpg          -> /config/www/floorplan/cartoon/render_lower.jpg   (CHANGED)
  render_upper.jpg          -> /config/www/floorplan/cartoon/render_upper.jpg   (unchanged
                               from d97fa3b5 -- upload only if it is missing)

floorplan_render.jpg (main floor) is UNCHANGED -- do not re-upload it.

Then on the box:  python3 tools/deploy_cartoon_card.py     # -> ?v=451e98f2

WHAT CHANGED SINCE d97fa3b5
The basement's bottom-left room was drawn as a second two-car garage, with cars and two
overhead doors. The house has one garage and it is on the main floor; that corner of the
basement is bare under-garage storage. The cars and doors are gone from the lower render,
replaced by shelving and stacked boxes, and the room is called storage in geometry.py. It is
art only -- nothing in HA is switchable down there -- so it is not tappable. The main floor's
garage keeps its doors, locks and GDO lights, unchanged.

MULTI-FLOOR
One layer at a time, switched with the Main / 2nd / Basement tabs bottom-right. All three
floors share ONE coordinate space (plan frame 136..1186 x 118..884), so overlays,
temperature pills and glow pools move with the art. The chosen floor is remembered in
localStorage['fpc.floor'].

The upper floor does not cover the garage: its west wall sits at plan x=361 and the strip
west of it is a hatched roof plane, drawn as roof, not as a room. The stairwell is a void
(open_below) -- drawn, never tappable, because there is no floor to stand on.

CAMERA PINS are main-floor only: every camera here is a main-floor or exterior mount, so
the pins are hidden on the 2nd and Basement layers rather than floating over other rooms.

TEMPERATURE PILLS carry the unit when it is not Celsius. Every sensor in this house reports
Fahrenheit, so a pill reads 68.4 with a trailing F (matching HA's more-info dialog) instead
of a bare 68.4 that looked like a Celsius reading.

ROOMS THAT ARE DRAWN BUT NOT TAPPABLE
walk_in_closet, hall_bath, ll_bath, utility, corridor_b and storage hold no controllable
load in HA, so the card paints no hotspot for them. They are listed in entity_map.json
_notes with the reason.

CAMERA OVERLAY (unchanged from 8ddfa0cf)
Nest cams return no stills to HA (every snapshot is the same 640x480 near-black
placeholder), so the frame carries a "Live view" button that hands off to HA's camera
dialog and nudges its play control once. Snapshot refresh is 15 s.
