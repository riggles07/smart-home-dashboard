CARTOON FLOORPLAN -- UPLOAD BUNDLE (version 78376f0d)
==================================================
ONLY floorplan-cartoon-card.js CHANGED. Art unchanged (included for a clean install).

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  floorplan_render.jpg      -> /config/www/floorplan/cartoon/floorplan_render.jpg

Then, on the box:
  python3 tools/deploy_cartoon_card.py        # re-points the resource at ?v=78376f0d

TWO CHANGES IN THIS BUILD
1. Layout: the plan is fitted to the shorter screen axis (panel-mode 1006x601 shows the
   whole plan, centred, no bottom clipping). Verified at that viewport: 805x601, 0px
   overflow.
2. Foyer now commands light.foyer_hall -- the new HA light group containing
   light.foyer_d1..d4. Candelabras stay as secondary controls in the room sheet.
