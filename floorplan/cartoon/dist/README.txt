CARTOON FLOORPLAN -- UPLOAD BUNDLE (version d97fa3b5)
====================================================
THREE FILES. The card now carries all three floors, so both new renders must land with it
-- a card that names an art file the server does not have shows an empty layer.

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  render_upper.jpg          -> /config/www/floorplan/cartoon/render_upper.jpg
  render_lower.jpg          -> /config/www/floorplan/cartoon/render_lower.jpg

floorplan_render.jpg (main floor) is UNCHANGED -- do not re-upload it.

Then on the box:  python3 tools/deploy_cartoon_card.py     # -> ?v=d97fa3b5

MULTI-FLOOR
The card shows one layer at a time and switches with the Main / 2nd / Basement tabs in the
bottom-right corner. All three floors were fitted into ONE coordinate space (plan frame
136..1186 x 118..884), so the overlays, temperature pills and glow pools move with the art
and no hotspot has to be re-registered per floor. The chosen floor is remembered in
localStorage['fpc.floor'], so the panel comes back up on the floor you left it on.

The upper floor does not cover the garage: its west wall sits at plan x=361 and the strip
west of it is a hatched roof plane, drawn as roof, not as a room. The stairwell is a void
(open_below) -- drawn, never tappable, because there is no floor to stand on.

CAMERA PINS are main-floor only. Every camera in this house is a main-floor or exterior
mount, so on the 2nd and Basement layers the pins are hidden rather than left floating
over unrelated rooms.

TEMPERATURE PILLS now carry the unit when it is not Celsius. Every sensor in this house
reports Fahrenheit, so a pill reads 68.4 with a trailing F (matching HA's more-info dialog)
instead of a bare 68.4 that looked like a Celsius reading.

ROOMS THAT ARE DRAWN BUT NOT TAPPABLE
walk_in_closet, hall_bath, ll_bath, utility, corridor_b and garage_lower are on the plan
but hold no controllable load in HA, so tapping them does nothing. They are listed in
entity_map.json under _notes with the reason. The lower garage stays unbound on purpose so
the garage-door covers and locks cannot appear on two floors at once.

CAMERA OVERLAY (unchanged from 8ddfa0cf)
Nest cams return no stills to HA (every snapshot is the same 640x480 near-black
placeholder), so the frame carries a "Live view" button that hands off to HA's camera
dialog and nudges its play control once. Snapshot refresh is 15 s.
