CARTOON FLOORPLAN -- UPLOAD BUNDLE (version 032a7d8b)
==================================================
ONLY floorplan-cartoon-card.js CHANGED. The art is unchanged -- you can skip the jpg
(already on the box as /config/www/floorplan/cartoon/floorplan_render.jpg), but it is in
the zip anyway for a clean install.

  floorplan-cartoon-card.js -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js
  floorplan_render.jpg      -> /config/www/floorplan/cartoon/floorplan_render.jpg

Then, on the box:
  python3 tools/deploy_cartoon_card.py        # re-points the resource at ?v=032a7d8b

WHAT CHANGED: the plan is now fitted to the SHORTER screen axis, so a panel-mode view
(1006x601 landscape) shows the whole plan instead of clipping the bottom, centred, with
the HUD pinned to the top. Verified at that exact viewport: stage/img/svg all 805x601,
101px and 100px side margins, 0px overflow.
