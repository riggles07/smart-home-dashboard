CARTOON FLOORPLAN -- UPLOAD BUNDLE (version b575eae7)
==================================================
ONLY floorplan-cartoon-card.js CHANGED (art is unchanged, included for a clean install).

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  floorplan_render.jpg      -> /config/www/floorplan/cartoon/floorplan_render.jpg

Then, on the box:
  python3 tools/deploy_cartoon_card.py        # re-points the resource at ?v=b575eae7

CHANGES IN THIS BUILD
1. Layout: plan fitted to the shorter screen axis (panel-mode 1006x601: whole plan,
   centred, 0px bottom clipping). Verified at that viewport: 805x601.
2. Foyer commands light.foyer_hall ONLY (new HA light group over foyer_d1..d4).
   Candelabras removed from the foyer room -- they belong to the living-room device.
