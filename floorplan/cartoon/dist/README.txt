CARTOON FLOORPLAN -- UPLOAD BUNDLE
=================================
Upload BOTH files to /config/www/floorplan/cartoon/   (create the folder if needed).
Use a binary-safe uploader: the .jpg must not be re-encoded.

  floorplan_render.jpg          -> /config/www/floorplan/cartoon/floorplan_render.jpg
  floorplan-cartoon-card.js     -> /config/www/floorplan/cartoon/floorplan-cartoon-card.js

Then, from the project root:

  python3 tools/deploy_cartoon_card.py --check-only   # confirms HA serves both files
  python3 tools/deploy_cartoon_card.py                # registers the resource + creates
                                                      # a separate  /cartoon  dashboard

The new dashboard sits alongside the existing /floor-plan, so nothing the kiosk uses
changes until you decide to switch it over (point that view at
custom:floorplan-cartoon-card).

The .js is self-contained: hotspot polygons and the entity map are compiled into it, and
the image URL carries a hash of both. If the art is regenerated, run build_card.py and
upload the new .js too -- the polygons are fitted to that exact image.
