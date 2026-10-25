CARTOON FLOORPLAN -- UPLOAD BUNDLE (version a258523d)
==================================================
ONLY floorplan-cartoon-card.js CHANGED (art unchanged, included for a clean install).

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  floorplan_render.jpg      -> /config/www/floorplan/cartoon/floorplan_render.jpg

Then on the box:  python3 tools/deploy_cartoon_card.py     # -> ?v=a258523d

CHANGES IN THIS BUILD
1. Fit: plan scaled to the shorter screen axis. HA's lovelace view measures 691px in a
   601px window (header hidden by kiosk-mode but still reserved), so the card now caps
   itself at min(container, window.innerHeight) AND pins its ancestor view to 100vh.
   Verified in a 1006x601 viewport: host 601, stage/img 805x601, 0px overflow, scroll 601.
2. Foyer commands light.foyer_hall only; candelabras removed (living-room device).
