CARTOON FLOORPLAN -- UPLOAD BUNDLE (version 53d684e0)
==================================================
ONLY floorplan-cartoon-card.js CHANGED (art unchanged, included for a clean install).

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  floorplan_render.jpg      -> /config/www/floorplan/cartoon/floorplan_render.jpg

Then on the box:  python3 tools/deploy_cartoon_card.py     # -> ?v=53d684e0

NEW: camera pins. Six pins sit at the locations from the annotated screenshot (driveway,
backyard upper, kitchen, garage, front door, living room). Tap a pin -> overlay with a
refreshed snapshot every 5s; "Live view" hands off to HA's own more-info dialog, which owns
the real Nest stream (WebRTC/HLS + audio). Pins grey out when the camera is unavailable.
