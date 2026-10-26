CARTOON FLOORPLAN -- UPLOAD BUNDLE (version 8ddfa0cf)
==================================================
ONLY floorplan-cartoon-card.js CHANGED (art unchanged, included for a clean install).

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  floorplan_render.jpg      -> /config/www/floorplan/cartoon/floorplan_render.jpg

Then on the box:  python3 tools/deploy_cartoon_card.py     # -> ?v=8ddfa0cf

CAMERA OVERLAY, ROUND 2
Your Nest cams return no stills to HA (every snapshot is the same 640x480 near-black
placeholder), so the old overlay looked dead. It now puts a "Live view" button ON the
frame; tapping it hands off to HA's camera dialog and nudges that dialog's play control
once, so the stream starts instead of waiting for a second press. Snapshot refresh slowed
5s -> 15s (it was hammering the API for an image that never arrives).
