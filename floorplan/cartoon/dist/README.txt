CARTOON FLOORPLAN -- UPLOAD BUNDLE (version ebcf511f)
====================================================
Upload BOTH files to /config/www/floorplan/cartoon/  (binary-safe; do not re-encode the jpg)

  floorplan_render.jpg          -> /config/www/floorplan/cartoon/floorplan_render.jpg
  floorplan-cartoon-card.js     -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js

The card file name is unchanged, so the existing Lovelace resource keeps working -- but
/local is cached for 31 days, so the resource URL must carry the new version:

  python3 tools/deploy_cartoon_card.py        # re-points the resource at ?v=ebcf511f
                                              # and refreshes the /cartoon-plan view

This build adds the GARAGE: 8 rooms, garage doors (cover), deadbolts (lock) and the two
garage lights are all in the room sheet.
