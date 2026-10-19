#!/usr/bin/env python3
"""
Generate real Node-RED flows (Path B) for the Smart Home Dashboard.

Produces flow JSON containing ACTUAL node instances (tabs, dashboard widgets,
inject/function/http-request/debug) -- not custom node-type definitions.

# All node types used are verified present in the live palette
# (tools/data/nr-types.txt, vendored from the live Node-RED palette).

Credentials are NEVER hardcoded: function nodes read them from env vars
(PROXMOX_URL / PROXMOX_TOKEN / HUBITAT_* / UNIFI_*).

# Visual hierarchy & progressive disclosure (2026-10-17 card t_b3218913):
# Every monitored tab carries an "Alerts" group at order 1 -- collapse: False,
# so the banner is the most prominent element on load and can never be hidden
# behind a collapsed section. Secondary groups (host details, device/client
# directories, Grafana embeds) are collapsible and start COLLAPSED via the
# SHD_COLLAPSE_DEFAULTS script (the stock dashboard's `collapse:true` only
# draws the caret; see the comment on that script below).
"""
import json, os, hashlib, re

# Resolve output paths relative to THIS script so the generator works in any
# checkout (CI, fresh clone), not only on the author's machine.
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(_ROOT, "flows")

def _id(seed):
    """Deterministic 16-hex-char node id."""
    return hashlib.sha1(seed.encode()).hexdigest()[:16]

def nid(seed):
    return _id(seed)

flows_all = []

def add(*nodes):
    flows_all.extend(nodes)

# ---------------------------------------------------------------- Global theming
#
# The legacy node-red-dashboard has NO `css:` setting. Verified against the
# bundled README: the only documented settings are
#   ui.path / ui.middleware / ui.ioMiddleware / ui.readOnly / ui.defaultGroup
# and theme/layout live in the `ui_base` (UI Settings) config node, not here.
# `config/settings.js` therefore cannot apply css/dashboard.css, and it is not
# served over HTTP (httpStatic is unset) -- so a <link> would 404.
#
# The working, dependency-free route is to INLINE the theme into a ui_template
# on an invisible ui_group. A ui_template renders into the page, so a <style>
# block inside it applies globally, and the dashboard pushes it over the
# existing websocket -- no extra HTTP plumbing required.
THEME_CSS_PATH = os.path.join(_ROOT, "css", "dashboard.css")


def load_theme_css(path=THEME_CSS_PATH):
    """Inline the theme, stripping anything that could break the <style> block."""
    with open(path) as fh:
        css = fh.read()
    # A stray "</style" would terminate the block early and spill CSS as text.
    css = css.replace("</style", "<\\/style")
    # Strip comments: they carry no runtime value and keep the node compact.
    while "/*" in css and "*/" in css:
        a = css.index("/*")
        b = css.index("*/", a) + 2
        css = css[:a] + css[b:]
    return css


# ---------------------------------------------------------------- Theme Manager
#
# Palette switching (task t_2fd8fb10). js/themes.js holds EVERY palette as a
# mapping of the --shd-* tokens to concrete values; the browser-side manager
# applies a palette by setting the custom properties on the document root.
# The dashboard serves no static files, so the module is INLINED into a
# global-scope ui_template appended to <head> (same delivery mechanism as the
# theme's <style> block above): its <script> executes on load.
#
# The picker buttons and the "Set theme" node below are built from the palettes
# PARSED OUT OF js/themes.js, so the UI can never drift from what ships.
THEMES_JS_PATH = os.path.join(_ROOT, "js", "themes.js")


def load_theme_manager_js(path=THEMES_JS_PATH):
    """Read js/themes.js and guard it against breaking the head <script> block.

    (No </script> can appear in a palette, but the check makes the invariant
    explicit -- the whole file is inlined into the node's format.)"""
    with open(path) as fh:
        src = fh.read()
    if "</script" in src:
        raise ValueError(f"{path} must not contain '</script' -- the whole "
                         "file is inlined into a ui_template <script> block")
    return src


BACKGROUND_JS_PATH = os.path.join(_ROOT, "js", "background.js")


def load_background_js(path=BACKGROUND_JS_PATH):
    """Read js/background.js and guard it against breaking the head <script>.

    THE ORPHAN TRAP: the previous attempt at this card shipped
    js/background.js as a file NOTHING loaded -- grep for its name in the
    generated flows returned zero hits, so the engine never ran in the browser
    and the card was (correctly) failed. Inlining the file text into the theme
    template is what makes it real; tests/test_background_engine.py asserts the
    generated JSON actually contains a marker from this file.
    """
    with open(path) as fh:
        src = fh.read()
    if "</script" in src:
        raise ValueError(f"{path} must not contain '</script' -- the whole "
                         "file is inlined into a ui_template <script> block")
    return src


def parse_themes_js(path=THEMES_JS_PATH):
    """Extract {palette_id: label} from js/themes.js.

    The file is an IIFE, not JSON, so parse it textually: each palette entry
    has the shape  '<id>': { ... label: '<label>' ... }. Deliberately strict --
    a shape change here fails loudly at generation time, not silently in the
    browser."""
    src = load_theme_manager_js(path)
    pattern = re.compile(
        r"'([a-z0-9-]+)':\s*\{[^{}]*?label:\s*'([^']*)'", re.S)
    found = pattern.findall(src)
    if not found:
        raise ValueError(f"no palettes found in {path} -- expected entries "
                         "like \"'nord': { label: 'Nord', ... }\"")
    out = []
    for pid, label in found:
        out.append({"id": pid, "label": label})
    return out



# The dashboard ships its own rule:
#     body.nr-dashboard-theme { background-color: #eee; ... }
# Specificity (0,1,1) beats the theme's plain `body {...}` (0,0,1) REGARDLESS of
# source order, so the theme's dark background silently loses and the page paints
# light while the text colour flips to #eee -- unreadable. Re-assert the page
# colours at the SAME specificity (injected later, so it wins on the tie) instead
# of reaching for !important, which would also stomp the dashboard's widget themes.
#
# Measured in the live UI (Node-RED 5.0.7 + legacy dashboard 3.6.6), the theme's
# own `.ui_tab .tab-link` rule matches NOTHING -- those classes are not in this
# version's DOM. Tab entries render as `md-list-item` (48px, fine) and the toolbar
# hamburger as `button.md-icon-button` (40px, UNDER the 44px target). Target the
# selectors that actually exist; the extra `body.nr-dashboard-theme` qualifier
# also lifts specificity above Angular Material's own rules.
THEME_OVERRIDE = """
/* Painted from the DERIVED token, not the palette token. This rule is
   specificity (0,1,1) and therefore BEATS the plain `body` rule in
   css/dashboard.css -- verified live: with only the body rule changed, the
   engine computed the right colour and the page still painted --shd-bg
   (measured body background rgb(26,26,46) instead of the night rgb(13,14,28)).
   js/background.js writes --shd-bg-effective; the fallback keeps the palette
   colour whenever the engine has not run. */
body.nr-dashboard-theme {
  background-color: var(--shd-bg-effective, var(--shd-bg));
  color: var(--shd-text);
  transition: background-color 0.8s ease;
}

/* ------------------------------------------------------------------
   The dashboard's own theme block defines the --nr-dashboard-* variables
   but then PAINTS its primary surfaces with hardcoded colours that ignore
   them. Measured in dashboard 3.6.6 (selector -> colour):
     body.nr-dashboard-theme md-content md-card   -> #fff
     .nr-dashboard-theme ui-card-panel            -> #fff
     body.nr-dashboard-theme md-toolbar           -> #0094CE
     body.nr-dashboard-theme md-sidenav           -> #eee
   Overriding only the variables therefore darkens :root while the page
   still renders light. These rules match or exceed each original's
   specificity, and this block is injected last, so ties resolve here.
   Deliberately not !important: nothing here is inline, and !important
   would also defeat the dashboard's later runtime theming.
   ------------------------------------------------------------------ */
body.nr-dashboard-theme md-content md-card {
  background: var(--shd-card);
  color: var(--shd-text);
}
body.nr-dashboard-theme ui-card-panel {
  background: var(--shd-card);
  color: var(--shd-text);
}

/* The dashboard paints ui_template content on its OWN white panel:
     .nr-dashboard-theme .nr-dashboard-template { background-color: #fff }
   That selector is specificity (0,2,0) and therefore BEATS the (0,1,3)
   `body.nr-dashboard-theme md-content md-card` rule above -- so templated
   widgets (the device and client tables) stayed white while the theme's
   `#eee` text sat on top of them. Measured contrast ratio: 1.16:1, i.e.
   invisible. Matching at (0,2,1) wins. Verified: the tables were the ONLY
   white surfaces left; every other widget card was already on --shd-card. */
body.nr-dashboard-theme .nr-dashboard-template {
  background: transparent;
  color: var(--shd-text);
}
/* The dashboard's legacy `.table` class is written for a light background.
   Its own rules only set borders/padding, so rows need explicit dark-theme
   separation or the list reads as one undifferentiated block. */
body.nr-dashboard-theme table.table {
  color: var(--shd-text);
  border-collapse: collapse;
}
body.nr-dashboard-theme table.table th {
  color: var(--shd-text);
  background: transparent;
  border-bottom: 2px solid var(--shd-accent);
}
body.nr-dashboard-theme table.table td {
  color: var(--shd-text);
  border-bottom: 1px solid rgba(255, 255, 255, 0.14);
}
body.nr-dashboard-theme table.table tbody tr:nth-child(even) {
  background: rgba(255, 255, 255, 0.045);   /* zebra striping for scanability */
}
/* `--shd-muted` is deliberately lighter than the 4.5:1 floor against
   --shd-card, so secondary text stays legible rather than decorative. */
body.nr-dashboard-theme .nr-dashboard-template .shd-muted,
body.nr-dashboard-theme .shd-muted {
  color: var(--shd-muted);
}
/* The slider's floating value bubble paints TEXT on the dashboard's hardcoded
   accent (--nr-dashboard-widgetBackgroundColor / #4FBAE4), which the theme's
   light text sat on at ~2.2:1 -- the number was barely legible. Give the
   bubble a dark surface. The track FILL keeps the accent: it is decorative
   and carries no text, so it is not a contrast problem. */
body.nr-dashboard-theme .nr-dashboard-slider .md-sign,
body.nr-dashboard-theme md-slider .md-sign {
  background-color: var(--shd-card);
  color: var(--shd-text);
}
/* GAUGE TEXT -- this is the rule that actually works in dashboard 3.6.6.
   justgage renders its labels as SVG <text fill="#111111"> (near-black).
   A presentation attribute sits at the BOTTOM of the cascade, so any CSS rule
   beats it -- no !important needed. Setting the node's `valueFontColor` does
   NOT work here: the 3.6.6 ui_gauge controller never forwards it to justgage
   (verified -- the attribute stayed #111111 with the property set). Measured
   before: values 0/4.7/100 at ~1.4:1, effectively invisible on the dark card. */
body.nr-dashboard-theme .nr-dashboard-gauge svg text {
  fill: var(--shd-text);
}
body.nr-dashboard-theme md-toolbar {
  background: var(--shd-surface);
  color: var(--shd-text);
}
body.nr-dashboard-theme md-sidenav {
  background: var(--shd-surface);
  color: var(--shd-text);
}

/* Tab drawer entries and the toolbar button are Angular Material elements,
   not `.ui_tab .tab-link` (which matches nothing in this version). The
   toolbar button measured 40px -- under the 44px touch target. */
body.nr-dashboard-theme md-sidenav md-list-item,
body.nr-dashboard-theme md-sidenav .md-button {
  min-height: var(--shd-touch-target);
  touch-action: manipulation;
}
body.nr-dashboard-theme md-sidenav md-list-item p,
body.nr-dashboard-theme md-sidenav .md-button {
  color: var(--shd-text);
}
body.nr-dashboard-theme button.md-icon-button,
body.nr-dashboard-theme .md-icon-button {
  min-height: var(--shd-touch-target);
  min-width: var(--shd-touch-target);
  touch-action: manipulation;
  color: var(--shd-text);
}

/* Charts/gauge/template content the dashboard paints on its own light panel. */
body.nr-dashboard-theme md-card .nr-dashboard-text,
body.nr-dashboard-theme md-card table,
body.nr-dashboard-theme md-card th,
body.nr-dashboard-theme md-card td {
  color: var(--shd-text);
}
body.nr-dashboard-theme md-card th {
  border-bottom-color: var(--shd-accent);
}

/* ==================================================================
   LANDSCAPE / WIDE-SCREEN LAYOUT
   ------------------------------------------------------------------
   The dashboard's masonry JS writes INLINE pixel widths onto
   `.nr-dashboard-cardcontainer` (measured: width 318px for a width-12
   group -> ~53.3px per grid unit) and INLINE `left`/`top` onto
   `ui-card-panel`. It derives those from the group's `width` in grid
   units and ignores the viewport, so on a 2166px screen every tab is a
   ~320px column pinned near the centre and the rest of the screen is
   empty.

   Because the widths are INLINE they outrank any normal CSS rule, so
   `!important` is required here — this is the case it exists for. We
   then reflow the cards ourselves.

   `!important` cannot beat inline styles for `left` on the same
   element, so a group that sits right-of-centre would still be offset;
   `margin-left: auto` is therefore applied with `!important` too, and
   the panel is pinned with left/right as well. Measured before/after
   below in tests/test_theme_wiring.py. */

/* Any reasonably wide viewport: stop the dashboard pinning a fixed
   narrow column. */
@media (min-width: 900px) {
  body.nr-dashboard-theme ui-card-panel {
    width: auto !important;
    max-width: none !important;
    /* The panel carries inline left/top from the masonry layout. `auto` with
       !important neutralises them without introducing an offset of its own
       (`right` must NOT be set here: on a relatively-positioned box a non-auto
       `right` shifts the element left by its own width). */
    position: relative !important;
    left: auto !important;
    top: auto !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
  }
  body.nr-dashboard-theme .nr-dashboard-cardcontainer {
    width: 100% !important;
    height: auto !important;
  }
  /* The title bar carries an inline width matching the old fixed column. */
  body.nr-dashboard-theme .nr-dashboard-cardtitle {
    width: auto !important;
  }
  /* Let the masonry container span the content area. */
  body.nr-dashboard-theme .masonry-container {
    width: 100% !important;
  }
  /* The widgets inside a card are `position: absolute` with an inline `top`
     (measured: top 0/54/108/216/324px), so the card had no height of its own
     and collapsed to 0 -- the panel then shrank to a 56px strip and the
     widgets, though still painted, were clipped out of the layout. Returning
     them to normal flow makes the container grow to fit.

     They are then laid out as a wrapping row rather than stretched to the full
     width: the dashboard sizes each widget's inline height for the ORIGINAL
     ~318px column, so stretching a widget to 2166px stretched its canvas to
     2144x221 (measured) -- a badly distorted, unreadable gauge. Content-sized
     cards that wrap into columns keep every widget at a sane aspect ratio and
     still fill the screen.

     `height` is deliberately left alone: gauges and charts depend on their
     dashboard-computed inline height to size the canvas. */
  body.nr-dashboard-theme .nr-dashboard-cardcontainer md-card,
  body.nr-dashboard-theme .nr-dashboard-card {
    position: static !important;
    left: auto !important;
    top: auto !important;
    display: inline-block;
    vertical-align: top;
    width: auto !important;
    max-width: 100% !important;
    min-width: 180px;
    margin: 8px 12px 12px 0;
  }
}

/* Genuinely wide screens (tablet landscape, desktop, wall panel). Every tab
   currently carries ONE group, so the panel fills the content width.
   NOTE: this block must NOT set a width on `md-card` -- the 900px block above
   already sizes widgets for their own aspect ratio, and an equal-specificity
   `width: 100% !important` here would win on source order and stretch every
   canvas again (measured: a gauge canvas blown out to 2144x221). */
@media (min-width: 1280px) {
  body.nr-dashboard-theme ui-card-panel {
    display: block;
    width: 100% !important;
  }
  body.nr-dashboard-theme .masonry-container {
    text-align: left;
  }
}

/* Short-and-wide (tablet held in landscape): trim vertical padding so
   more fits above the fold. */
@media (max-height: 600px) and (orientation: landscape) {
  body.nr-dashboard-theme .nr-dashboard-cardcontainer {
    padding-top: 0;
  }
  body.nr-dashboard-theme ui-card-panel {
    margin-top: 0;
  }
}

"""

# ---------------------------------------------------------------- Visual hierarchy
#
# PROGRESSIVE DISCLOSURE -- the stock dashboard's `collapse: true` does NOT
# collapse a group on load. Verified against the node-red-dashboard 3.6.6 dist
# (ui-card-panel directive + template):
#   o.collapsed = "true" == localStorage.getItem(r.id)   <- ONLY source of state
#   config.collapse is consulted exclusively by ng-if on the caret <span>
# The flag merely draws the expander affordance. Worse, the panel's `id`
# attribute is the RAW interpolation text at link time, so every panel shares
# one broken localStorage key and stored state can never round-trip per group.
# Without help, every group renders expanded on every fresh load.
#
# THE STOCK CLICK PATH (what we drive):
#   o.collapseCard() flips scope.collapsed, slideToggles the container,
#   writes localStorage[r.id] (the shared broken key) and $emits "collapse".
#   The stock restore path itself collapses a panel by triggering a click:
#     e(function(){ a.find(".nr-dashboard-cardcarat").trigger("click") }, 20)
#
# TWO STOCK QUIRKS THE SCRIPT MUST NEUTRALISE (both verified in the dist):
#   1. group `className` lands on the INNER .nr-dashboard-cardpanel div via
#      ng-class -- the <ui-card-panel> host element never carries it. Select
#      `.nr-dashboard-cardpanel.shd-collapsible` and walk up to the host for
#      its node-id. A `ui-card-panel.shd-collapsible` selector matches
#      NOTHING and fails silently.
#   2. every carat click (including OURS) writes the shared literal key
#      "{{group.header.id}}" = "true". On the next load EVERY panel then
#      auto-restores COLLAPSED via the stock +20ms path -- including groups
#      the user pinned open. The script scrubs that key after every click
#      and re-opens user-pinned groups if the stock path collapsed them.
#
# The SHD_COLLAPSE_DEFAULTS script (a global ui_template, appended to <head>
# on every page load exactly like the theme CSS -- the bundled jQuery 3.7.1
# append path evaluates <script> tags via globalEval) applies per-group
# defaults on every render of every tab (MutationObserver -- ng-repeat
# re-creates panels on tab switch). It keeps its OWN per-group localStorage
# keys ('shd_collapsed_<group-node-id>' -- real node ids, unlike the stock
# shared key) so a group the user expanded stays expanded across reloads,
# while fresh groups start collapsed: the acceptance criterion.
SHD_COLLAPSE_DEFAULTS = """<script>
/* shd-collapse-defaults: progressive disclosure (card t_b3218913).
   Groups configured with className 'shd-collapsible' start collapsed; the
   stock dashboard cannot do this itself (its localStorage key is shared by
   every panel). Collapse by clicking the group's own caret -- the identical
   code path the dashboard uses to restore a saved state -- so the caret icon
   and scope state stay in sync. */
(function () {
  if (window.__shdCollapseDefaults) { return; }
  window.__shdCollapseDefaults = true;
  var PREFIX = 'shd_collapsed_';
  var SHARED_KEY = '{{group.header.id}}';  /* the stock key: same literal text
     for every panel (interpolation is unresolved at link time) */

  function groupKey(host) {
    var id = host.getAttribute('node-id') || '';
    // Before interpolation resolves, the attribute holds the raw {{...}} text.
    return id && id.indexOf('{') === -1 ? PREFIX + id : null;
  }

  function scrubShared() {
    /* Our click made the stock write the shared key; if it is ever read at
       link time again, EVERY panel auto-collapses on load. It must never
       decide anything. */
    try { localStorage.removeItem(SHARED_KEY); } catch (e) {}
  }

  function armCarat(host, carat) {
    // Record the user's toggle in OUR namespace so choices survive reloads.
    if (!carat || carat.getAttribute('data-shd-armed')) { return; }
    carat.setAttribute('data-shd-armed', '1');
    carat.addEventListener('click', function () {
      var k = groupKey(host);
      if (k) {
        var cur = null;
        try { cur = localStorage.getItem(k); } catch (e) {}
        /* The click always TOGGLES, so the new state is the inverse of the
           recorded one: 'false' (open) -> 'true'; anything else -> 'false'.
           A null record means the panel was collapsed-by-default, so the
           click opened it. */
        try {
          localStorage.setItem(k, cur === 'false' ? 'true' : 'false');
        } catch (e) {}
      }
      scrubShared();
    });
  }

  function armTitleBar(inner, host, carat) {
    /* The stock binds ng-click on the CARAT SPAN ONLY -- a ~14x14px tap
       target. The theme CSS enlarges the caret to the touch target and
       makes the whole title <p> a 44px-high flex row; forward taps anywhere
       on the row to the caret so the toggle area spans the full group
       width (acceptance: touch-friendly expand/collapse). */
    var title = inner.querySelector('.nr-dashboard-cardtitle');
    if (!title || title.getAttribute('data-shd-armed')) { return; }
    title.setAttribute('data-shd-armed', '1');
    title.addEventListener('click', function (e) {
      if (carat.contains(e.target)) { return; }  /* direct carat tap: the
        carat's own ng-click + our carat listener already handled it */
      carat.click();
    });
  }

  function applyDefaults() {
    /* className lives on the INNER .nr-dashboard-cardpanel div (ng-class in
       the stock template) -- never on the <ui-card-panel> host. */
    var inners = document.querySelectorAll(
        '.nr-dashboard-cardpanel.shd-collapsible');
    for (var i = 0; i < inners.length; i++) {
      var inner = inners[i];
      var host = inner.parentNode;             /* <ui-card-panel node-id=...> */
      var carat = inner.querySelector('.nr-dashboard-cardcarat');
      var container = inner.querySelector('.nr-dashboard-cardcontainer');
      if (!host || host.nodeType !== 1 || !carat || !container) { continue; }

      var k = groupKey(host);
      if (!k) { continue; }                    /* id not interpolated yet */

      // One action per render: a second click during the 150ms slideToggle
      // animation would flip the panel back the other way. The marker dies
      // with the panel element when the tab re-renders.
      var done = host.getAttribute('data-shd-done');
      if (!done) {
        var stored = null;
        try { stored = localStorage.getItem(k); } catch (e) {}
        var isCollapsed = container.offsetParent === null;
        var act = false;
        if (stored === 'false') {
          act = isCollapsed;      /* user pinned OPEN; the stock shared-key
             restore may have collapsed it anyway -> re-open */
        } else if (stored === 'true') {
          act = !isCollapsed;     /* user pinned CLOSED; keep it closed */
        } else {
          act = !isCollapsed;     /* fresh visit: default-collapsed */
        }
        if (act) {
          carat.click();
          scrubShared();
          host.setAttribute('data-shd-done', '1');
        }
      }
      // Arm AFTER any programmatic click so our own click is never recorded
      // as a user choice; both arms are idempotent per panel render.
      armCarat(host, carat);
      armTitleBar(inner, host, carat);
    }
  }

  var scheduled = false;
  function schedule() {
    if (scheduled) { return; }
    scheduled = true;
    setTimeout(function () { scheduled = false; applyDefaults(); }, 100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', applyDefaults);
  } else {
    applyDefaults();
  }
  setTimeout(applyDefaults, 500);
  setTimeout(applyDefaults, 1500);
  var observer = new MutationObserver(function (muts) {
    for (var i = 0; i < muts.length; i++) {
      if (muts[i].addedNodes.length) { schedule(); return; }
    }
  });
  if (document.body) {
    observer.observe(document.body, { childList: true, subtree: true });
  } else {
    document.addEventListener('DOMContentLoaded', function () {
      observer.observe(document.body, { childList: true, subtree: true });
    });
  }
})();
</script>"""


# ---------------------------------------------------------------- Alert banners
#
# One "Alerts" group at order 1 on every monitored tab, disp: False (no group
# chrome -- the banner stands alone), collapse: False -- so an alert can NEVER
# be hidden behind a collapsed section (acceptance criterion 3). The banner is
# a ui_template whose ng-class picks the severity class; the theme's
# .alert-critical/.alert-warning/.alert-info/.alert-ok ladder does the visual
# emphasis (critical: largest type, strongest contrast, pulse).
# The banner is also the STATE-BASED trigger for the background engine: every
# tab's evaluator already computes a severity, so the banner hands it to
# window.SHDBackground instead of the engine needing its own polling path.
# Guarded -- the engine lives in a global head template that may not exist yet
# during a cold load, and a missing engine must never break the banner.
TEMPLATE_ALERT = (
    '<div ng-class="msg.payload.severity === \'critical\' ? \'alert-critical\' : '
    'msg.payload.severity === \'warning\' ? \'alert-warning\' : '
    'msg.payload.severity === \'info\' ? \'alert-info\' : \'alert-ok\'">'
    '{{msg.payload.message}}</div>'
    '<script>'
    '(function (scope) {'
    '  if (scope.msg && scope.msg.payload && window.SHDBackground) {'
    '    window.SHDBackground.setSeverity(scope.msg.payload.severity);'
    '  }'
    '})(scope);'
    '</script>'
)

# Catch-node feed guard. Prepended to EVERY evaluator below.
#
# WHY: an `http request` node that fails (bad host, DNS, timeout, refused) does
# not emit a normal message -- its failure goes to `msg.error` on the CATCH
# path only. With no catch node in the graph the message dies silently and the
# banner keeps whatever it last showed (its template default, "Awaiting first
# result"). A dead integration then reads as "no data yet" instead of "broken",
# which is exactly how the Hubitat tab sat empty on 2026-10-19 while UniFi and
# Proxmox were healthy. One catch node per tab, wired into that tab's
# evaluator, converts every swallowed failure into a critical banner.
_ALERT_ERROR_GUARD = (
    "// Catch-node feed: a node failure MUST surface as a critical banner.\n"
    "if (msg.error) {\n"
    "  var src = (msg.error.source && msg.error.source.name)\n"
    "    ? msg.error.source.name : 'integration';\n"
    "  var emsg = String(msg.error.message || 'failed').slice(0, 110);\n"
    "  node.status({fill: 'red', shape: 'ring', text: 'node error'});\n"
    "  msg.payload = {severity: 'critical', message: src + ' failed: ' + emsg};\n"
    "  return msg;\n"
    "}\n"
)

# Shared status line for the evaluators (node.status colour follows severity).
_ALERT_STATUS = (
    "node.status({fill: sev === 'ok' ? 'green' : "
    "(sev === 'critical' ? 'red' : 'yellow'), shape: 'dot', text: sev});\n"
)


def _catch_node(seed, tab_id, alert_fn_id, x, y):
    """Catch every unhandled node error in this tab and feed the evaluator.

    `scope: None` catches all nodes in the containing flow (tab), so a new
    http/function node added later is covered without touching this list.
    """
    return {"id": nid(f"catch-{seed}"), "type": "catch", "z": tab_id,
            "name": f"Catch failures ({seed})", "scope": None, "uncaught": False,
            "x": x, "y": y, "wires": [[alert_fn_id]]}


def _alert_group(seed, tab_id, z_id, name):
    """The order-1 Alerts group for a tab: never collapsible, no header.

    `z` must be the FLOW TAB id (T) so the group lands in the same per-tab
    flow file as its widgets; `tab` is the ui_tab the dashboard groups it
    under. Mixing them up exiles the group to 99-other.flow.json and breaks
    cross-file refs (caught by tools/validate_flows.py).
    """
    return {"id": nid(f"grp-alert-{seed}"), "type": "ui_group", "z": z_id,
            "name": name, "tab": tab_id, "order": 1, "disp": False, "width": "12",
            "collapse": False, "className": ""}


def _alert_template(seed, group_id, tab_id, x, y):
    """The banner widget for an Alerts group."""
    return {"id": nid(f"tpl-alert-{seed}"), "type": "ui_template", "z": tab_id,
            "name": "Alert Banner", "group": group_id, "order": 1,
            "width": "12", "height": "2", "format": TEMPLATE_ALERT,
            "storeOutMessages": True, "fwdInMessages": False,
            "resendOnRefresh": True, "templateScope": "local",
            "x": x, "y": y, "wires": [[]]}


# Evaluator bodies. Classic per-message contract (return the outgoing message;
# no on()/send() -- this Node-RED does not provide them; see
# tests/test_flow_newline_guard.py). Thresholds live in the flow, not the
# browser, so a banner updates on the same cadence as its data.
#
ALERT_EVAL_HOMELAB = (
    _ALERT_ERROR_GUARD
    +     "// Home Lab alert banner: CPU/memory pressure on the Proxmox host.\n"
    "// Split metrics attaches mem + uptime to its CPU (out0) message, so a\n"
    "// single feed evaluates the whole tab state.\n"
    "var cpu = (typeof msg.payload === 'number') ? msg.payload : -1;\n"
    "var mem = (typeof msg.mem === 'number') ? msg.mem : 0;\n"
    "var up = msg.uptime || '';\n"
    "var sev = 'ok';\n"
    "var parts = [];\n"
    "if (cpu < 0) {\n"
    "  sev = 'critical';\n"
    "  parts.push('Proxmox data unavailable');\n"
    "} else {\n"
    "  if (cpu >= 90) { sev = 'critical'; parts.push('CPU ' + cpu + '%'); }\n"
    "  else if (cpu >= 75) {\n"
    "    sev = 'warning'; parts.push('CPU ' + cpu + '%');\n"
    "  }\n"
    "  if (mem >= 90) { sev = 'critical'; parts.push('Memory ' + mem + '%'); }\n"
    "  else if (mem >= 75) {\n"
    "    if (sev === 'ok') { sev = 'warning'; }\n"
    "    parts.push('Memory ' + mem + '%');\n"
    "  }\n"
    "  if (sev === 'ok') { parts.push('Proxmox OK' + (up ? ' - up ' + up : '')); }\n"
    "}\n"
    + _ALERT_STATUS +
    "msg.payload = {severity: sev, message: parts.join(' | ')};\n"
    "return msg;"
)


ALERT_EVAL_HA = (
    _ALERT_ERROR_GUARD
    + "// Home Assistant alert banner: API reachability + unavailable entities.\n"
    "// Format HA states attaches {total, unavailable, controllable} on _stats.\n"
    "if (msg.topic === 'ha/error' || msg._error) {\n"
    "  node.status({fill: 'red', shape: 'ring', text: 'ha down'});\n"
    "  msg.payload = {severity: 'critical',\n"
    "    message: 'Home Assistant unreachable: ' + String(msg._error || msg.payload || '').slice(0, 100)};\n"
    "  return msg;\n"
    "}\n"
    "var st = msg._stats;\n"
    "var sev = 'ok';\n"
    "var text;\n"
    "if (st) {\n"
    "  if (st.unavailable > 0) {\n"
    "    sev = st.unavailable >= 3 ? 'warning' : 'info';\n"
    "    text = st.unavailable + ' of ' + st.total + ' entities unavailable';\n"
    "  } else {\n"
    "    text = st.controllable + ' devices controllable, ' + st.total + ' entities tracked';\n"
    "  }\n"
    "} else {\n"
    "  sev = 'info';\n"
    "  text = String(msg.payload || 'Awaiting first result');\n"
    "}\n"
    + _ALERT_STATUS +
    "msg.payload = {severity: sev, message: text};\n"
    "return msg;"
)

ALERT_EVAL_NETWORK = (
    _ALERT_ERROR_GUARD
    +     "// Network alert banner: controller reachability + client-count anomaly.\n"
    "// Split client data tags its count output with topic 'unifi/error' when\n"
    "// the poll failed, so 'no clients' (warning) is distinguishable from an\n"
    "// unreachable controller (critical).\n"
    "var n = (typeof msg.payload === 'number') ? msg.payload : -1;\n"
    "var sev = 'ok';\n"
    "var text;\n"
    "if (n < 0 || msg.topic === 'unifi/error') {\n"
    "  sev = 'critical';\n"
    "  text = 'UniFi controller unreachable' + (msg._error ? ' -- ' + String(msg._error).slice(0, 100) : '');\n"
    "} else if (n === 0) {\n"
    "  sev = 'warning';\n"
    "  text = 'No clients online';\n"
    "} else {\n"
    "  text = n + ' clients online';\n"
    "}\n"
    + _ALERT_STATUS +
    "msg.payload = {severity: sev, message: text};\n"
    "return msg;"
)

ALERT_EVAL_HEALTH = (
    _ALERT_ERROR_GUARD
    +     "// System Health alert banner: Prometheus targets/probes + node pressure.\n"
    "// Parse health summary attaches the full stat map to its first output,\n"
    "// so one message evaluates the whole stack.\n"
    "var m = msg.stats || {};\n"
    "var cpu = m.pve_cpu, mem = m.pve_mem;\n"
    "var tUp = m.targets_up, tTot = m.targets_total;\n"
    "var pOk = m.probes_ok, pTot = m.probes_total;\n"
    "function pct(v) { return Math.round(v * 10) / 10 + '%'; }\n"
    "function escalate(s) {\n"
    "  if (s === 'critical') { sev = 'critical'; }\n"
    "  else if (s === 'warning' && sev !== 'critical') { sev = 'warning'; }\n"
    "}\n"
    "var sev = 'ok';\n"
    "var parts = [];\n"
    "if (!m || msg.payload === -1) {\n"
    "  // Parse health summary marks total failure with payload:-1 (stats\n"
    "  // null) or payload:-1 + empty stats (Prometheus up, nothing scraped).\n"
    "  sev = 'critical';\n"
    "  parts.push('Monitoring data unavailable');\n"
    "} else {\n"
    "if (typeof cpu === 'number') {\n"
    "  if (cpu >= 90) { escalate('critical'); parts.push('CPU ' + pct(cpu)); }\n"
    "  else if (cpu >= 75) { escalate('warning'); parts.push('CPU ' + pct(cpu)); }\n"
    "}\n"
    "if (typeof mem === 'number') {\n"
    "  if (mem >= 90) { escalate('critical'); parts.push('Memory ' + pct(mem)); }\n"
    "  else if (mem >= 75) { escalate('warning'); parts.push('Memory ' + pct(mem)); }\n"
    "}\n"
    "if (tTot > 0 && tUp < tTot) {\n"
    "  escalate(tUp === 0 ? 'critical' : 'warning');\n"
    "  parts.push('Targets ' + tUp + '/' + tTot);\n"
    "}\n"
    "if (pTot > 0 && pOk < pTot) {\n"
    "  escalate(pOk === 0 ? 'critical' : 'warning');\n"
    "  parts.push('Probes ' + pOk + '/' + pTot);\n"
    "}\n"
    "if (sev === 'ok') { parts.push('All monitored systems healthy'); }\n"
    "}\n"
    + _ALERT_STATUS +
    "msg.payload = {severity: sev, message: parts.join(' | ')};\n"
    "return msg;"
)


_theme_css = load_theme_css()
T = nid("tab-homelab")
add({"id": nid("uitab-theme"), "type": "ui_tab", "z": T, "name": "Theme",
     "icon": "paint-brush", "order": 99, "disabled": False, "hidden": True})
_TG = nid("grp-theme")
add({"id": _TG, "type": "ui_group", "z": T, "name": "Theme",
     "tab": nid("uitab-theme"), "order": 1, "disp": True, "width": "12",
     "collapse": False})
add({"id": nid("tpl-theme"), "type": "ui_template", "z": T, "name": "Mobile theme",
     "group": _TG, "order": 1, "width": "0", "height": "0",
     "format": "<style>\n" + _theme_css + "\n" + THEME_OVERRIDE + "</style>"
               + SHD_COLLAPSE_DEFAULTS,
     "storeOutMessages": False, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "global", "x": 130, "y": 900, "wires": [[]]})

# ---- Theme Manager: palette definitions + boot (task t_2fd8fb10) -----------
# js/themes.js is inlined VERBATIM into a second global-scope template. The
# dashboard appends global templates to <head> (jQuery .append -> the inline
# script executes synchronously), so the stored palette is applied to the
# document root BEFORE the tab content first paints -- no flash of the wrong
# theme. Every (re)connect and every ui-controls replay tears the head block
# down and re-appends it, which re-defines the (idempotent) manager and
# re-runs init(); that is the dashboard's own lifecycle, not ours to fight.
# The live 3.6.6 client (dist/js/app.min.js, function O) was read before
# choosing this delivery route.
_theme_manager_js = load_theme_manager_js()
_background_js = load_background_js()
add({"id": nid("tpl-theme-manager"), "type": "ui_template", "z": T,
     "name": "Theme manager", "group": _TG, "order": 2, "width": "0", "height": "0",
     "format": ("<script>\n" + _theme_manager_js + "\nSHDThemeManager.init();\n"
                # The background engine is a SEPARATE IIFE with its own public
                # API (window.SHDBackground). It runs right after the theme
                # manager so --shd-bg already exists when it derives
                # --shd-bg-effective on first paint (no flash, no reflow).
                + _background_js + "\n</script>"),
     "storeOutMessages": False, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "global", "x": 130, "y": 960, "wires": [[]]})
# Palette ids/labels are PARSED out of js/themes.js -- the Settings picker
# buttons and the "Set theme" validator are both generated from this, so the
# UI can never drift from the palettes actually shipped to the browser.
PALETTES = parse_themes_js()

# --- UI Settings (ui_base) --------------------------------------------------
# This is what tells the dashboard it is on a DARK theme. Without it the
# dashboard assumes light and derives every foreground colour from a boolean:
#   @widgetTextColor = isDark ? '#FFFFFF' : '#000000'
# Verified in the 3.6.6 bundle: `isDark` is only set when the theme declares
#   theme.angularTheme.palette === 'dark'
# and the chart engine then paints axis ticks/labels BLACK on our dark card
# (measured: the faintest text on the page). A `ui_template` <style> cannot fix
# that -- canvas text is drawn from JS, not CSS. The palette flag can.
# `palette` is also what generates the Material palettes, so this fixes the
# chart text AND any Material chrome we have not overridden by hand.
add({"id": nid("uibase"), "type": "ui_base", "z": T, "name": "",
     "theme": {
        "name": "theme-custom",
        "baseColor": "#fa6f63",
        "page": {"name": "Page", "style": "dark", "light": False,
                 "palette": "dark"},
        "angularTheme": {"primary": "indigo", "accents": "blue",
                         "warn": "red", "background": "grey",
                         "palette": "dark"}
     },
     "site": {"title": "Smart Home", "dateFormat": "DD/MM/YYYY",
              "sizes": {"sx": 48, "sy": 48, "gx": 6, "gy": 6, "cx": 6, "cy": 6,
                        "px": 12, "py": 12},
              "options": {"showPath": False}},
     "x": 330, "y": 900, "wires": []})


# ---------------------------------------------------------------- Tab 1: Home Lab
T = nid("tab-homelab")
add({"id": T, "type": "tab", "label": "Home Lab", "disabled": False, "info": ""})
add({"id": nid("uitab-h"), "type": "ui_tab", "z": T, "name": "Home Lab",
     "icon": "dashboard", "order": 1, "disabled": False, "hidden": False})

# ---- Alerts (order 1): most prominent element, NEVER collapsible ----------
# The banner evaluates CPU/mem pressure from the same message that feeds the
# CPU gauge, so it updates on the same 30s cadence.
G_ALERT = _alert_group("homelab", nid("uitab-h"), T, "Alerts")
add(G_ALERT)
add(_alert_template("homelab", G_ALERT["id"], T, 1150, 40))
add({"id": nid("fn-alert-h"), "type": "function", "z": T, "name": "Evaluate alerts",
     "func": ALERT_EVAL_HOMELAB,
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 1150, "y": 120, "wires": [[nid("tpl-alert-homelab")]]})
# Every unhandled node error in this tab (http failures, thrown
# exceptions) reaches the same evaluator, so a broken integration
# shows a CRITICAL banner instead of silently keeping its default.
add(_catch_node("homelab", T, nid("fn-alert-h"), 1200, 200))

G = nid("grp-pve")
add({"id": G, "type": "ui_group", "z": T, "name": "Proxmox Host",
     "tab": nid("uitab-h"), "order": 2, "disp": True, "width": "12", "collapse": False})

add({"id": nid("gg-cpu"), "type": "ui_gauge", "z": T, "name": "Proxmox CPU",
     "group": G, "order": 1, "width": "5", "height": "5", "gtype": "gage",
     "title": "CPU", "label": "%", "format": "{{value}}", "min": 0, "max": "100",
     "colors": ["#00b500", "#e6e600", "#ca3838"], "seg1": "", "seg2": "",
     "x": 640, "y": 120, "wires": []})
add({"id": nid("gg-mem"), "type": "ui_gauge", "z": T, "name": "Proxmox Memory",
     "group": G, "order": 2, "width": "5", "height": "5", "gtype": "gage",
     "title": "Memory", "label": "%", "format": "{{value}}", "min": 0, "max": "100",
     "colors": ["#00b500", "#e6e600", "#ca3838"], "seg1": "", "seg2": "",
     "x": 640, "y": 220, "wires": []})
add({"id": nid("txt-status"), "type": "ui_text", "z": T, "name": "Host Status",
     "group": G, "order": 3, "width": "6", "height": "2",
     "label": "Status", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 320, "wires": []})
add({"id": nid("ch-cpu"), "type": "ui_chart", "z": T, "name": "CPU History",
     "group": G, "order": 4, "width": "7", "height": "6", "label": "CPU %",
     "chartType": "line", "legend": "false", "xformat": "HH:mm:ss",
     "interpolate": "linear", "nodata": "", "dot": False, "ymin": "0", "ymax": "100",
     "removeOlder": "5", "removeOlderPoints": "", "removeOlderUnit": "60",
     "cutout": 0, "useOneColor": False, "colors": ["#1f77b4", "#aec7e8"],
     "x": 650, "y": 420, "wires": []})

# ---- Host detail widgets -------------------------------------------------
# Field names below are NOT guessed: tools/probe_proxmox_status.py read the live
# /nodes/<node>/status response and reported these top-level keys --
#   boot-info, cpu, cpuinfo, current-kernel, idle, ksm, kversion, loadavg,
#   memory, pveversion, rootfs, swap, uptime, wait
# with the nested shapes:
#   memory   -> used|free|available|total      rootfs -> used|total|free|avail
#   swap     -> used|total|free                loadavg -> 0|1|2
#   cpuinfo  -> cores|cpus|model|mhz|sockets|... current-kernel -> release
# Every value below comes from one of those, so nothing renders as undefined.
TEMPLATE_HOST = (
    "<table class='table' style='width:100%'>\n"
    "  <tbody>\n"
    "    <tr><td class='shd-muted'>Proxmox</td><td>{{msg.payload.pveversion}}</td></tr>\n"
    "    <tr><td class='shd-muted'>Kernel</td><td>{{msg.payload.kversion}}</td></tr>\n"
    "    <tr><td class='shd-muted'>CPU model</td><td>{{msg.payload.model}}</td></tr>\n"
    "    <tr><td class='shd-muted'>Cores</td><td>{{msg.payload.cores}} @ {{msg.payload.mhz}} MHz</td></tr>\n"
    "    <tr><td class='shd-muted'>Load avg</td><td>{{msg.payload.load1}} / {{msg.payload.load5}} / {{msg.payload.load15}}</td></tr>\n"
    "    <tr><td class='shd-muted'>Uptime</td><td>{{msg.payload.uptime}}</td></tr>\n"
    "  </tbody>\n"
    "</table>"
)
# ---- Host details: secondary, collapsed by default ------------------------
# The detail table + swap/disk/memory rows are reference material, not the
# at-a-glance state -- progressive disclosure keeps the default view lean.
G2 = nid("grp-hdet")
add({"id": G2, "type": "ui_group", "z": T, "name": "Host Details",
     "tab": nid("uitab-h"), "order": 3, "disp": True, "width": "12",
     "collapse": True, "className": "shd-collapsible"})
add({"id": nid("tpl-host"), "type": "ui_template", "z": T, "name": "Host Detail",
     "group": G2, "order": 1, "width": "7", "height": "5",
     "format": TEMPLATE_HOST, "storeOutMessages": True, "fwdInMessages": True,
     "resendOnRefresh": True, "templateScope": "local",
     "x": 650, "y": 520, "wires": [[]]})
add({"id": nid("txt-swap"), "type": "ui_text", "z": T, "name": "Swap",
     "group": G2, "order": 2, "width": "4", "height": "2",
     "label": "Swap", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 620, "wires": []})
add({"id": nid("txt-disk"), "type": "ui_text", "z": T, "name": "Disk (rootfs)",
     "group": G2, "order": 3, "width": "4", "height": "2",
     "label": "Disk", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 700, "wires": []})
add({"id": nid("txt-mem"), "type": "ui_text", "z": T, "name": "Memory Detail",
     "group": G2, "order": 4, "width": "4", "height": "2",
     "label": "Memory", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 780, "wires": []})

add({"id": nid("inj-h"), "type": "inject", "z": T, "name": "Every 30s",
     "props": [{"p": "payload"}], "repeat": "30", "crontab": "", "once": True,
     "onceDelay": 0.5, "topic": "", "payload": "", "payloadType": "date",
     "x": 150, "y": 120, "wires": [[nid("fn-h-build")]]})
add({"id": nid("fn-h-build"), "type": "function", "z": T, "name": "Build Proxmox request",
     "func": (
        "// Credentials come from env vars -- never hardcoded.\n"
        "var base = env.get('PROXMOX_URL');\n"
        "var tok  = env.get('PROXMOX_TOKEN');\n"
        "if (!base || !tok) {\n"
        "  node.status({fill:'red',shape:'ring',text:'missing config'});\n"
        "  return null;\n"
        "}\n"
        "var node = env.get('PROXMOX_NODE') || 'pve';\n"
        "msg.method = 'GET';\n"
        "msg.url = base.replace(/\\/+$/, '') + '/api2/json/nodes/' + node + '/status';\n"
        "msg.headers = {};\n"
        "msg.headers['Authorization'] = 'PVEAPIToken=' + tok;\n"
        "msg.rejectUnauthorized = false;\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 360, "y": 120, "wires": [[nid("http-h")]]})
add({"id": nid("http-h"), "type": "http request", "z": T, "name": "Proxmox API",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 570, "y": 120,
     "wires": [[nid("json-h")]]})
add({"id": nid("json-h"), "type": "json", "z": T, "name": "Parse",
     "property": "payload", "action": "obj", "pretty": False,
     "x": 730, "y": 120, "wires": [[nid("fn-h-parse")]]})
add({"id": nid("fn-h-parse"), "type": "function", "z": T, "name": "Split metrics",
     "func": (
        "var d = (msg.payload && msg.payload.data) ? msg.payload.data : null;\n"
        "if (!d) {\n"
        "  node.status({fill:'red',shape:'ring',text:'no data'});\n"
        "  // out0 feeds the alert evaluator: payload -1 is its 'data\n"
        "  // unavailable' marker -> a CRITICAL banner instead of a blank one.\n"
        "  // The gauge clamps -1 to its 0 floor (cosmetic; the banner is the\n"
        "  // authoritative alert element).\n"
        "  return [{payload: -1, mem: -1, uptime: ''}, null, null, null, null, null, null, null];\n"
        "}\n"
        "var cpu = Math.round((d.cpu || 0) * 1000) / 10;\n"
        "var memUsed = (d.memory && d.memory.used) || 0;\n"
        "var memTot = (d.memory && d.memory.total) || 1;\n"
        "var mem = Math.round(memUsed / memTot * 1000) / 10;\n"
        "var up = d.uptime || 0;\n"
        "var days = Math.floor(up / 86400), hrs = Math.floor((up % 86400) / 3600);\n"
        "node.status({fill:'green',shape:'dot',text:cpu + '% cpu'});\n"
        "// Human-readable byte formatting for the disk/swap/memory rows.\n"
        "function gb(v) { return (Math.round(v / 1073741824 * 10) / 10) + ' GB'; }\n"
        "function pct(u, t) { return t ? Math.round(u / t * 1000) / 10 + '%' : 'n/a'; }\n"
        "// Nested sub-objects are flattened onto the payload so the Host Detail\n"
        "// template can reach them with plain dotted paths -- confirmed present in\n"
        "// the live response by tools/probe_proxmox_status.py.\n"
        "var rootfs = d.rootfs || {}, swap = d.swap || {};\n"
        "var mem2 = d.memory || {};\n"
        "var ci = d.cpuinfo || {}, kd = d['current-kernel'] || {}, la = d.loadavg || [];\n"
        "var detail = {\n"
        "  payload: {\n"
        "    pveversion: d.pveversion || 'unknown',\n"
        "    kversion: d.kversion || kd.release || 'unknown',\n"
        "    model: ci.model || 'unknown',\n"
        "    cores: ci.cores || ci.cpus || '?',\n"
        "    mhz: ci.mhz || '?',\n"
        "    load1: (la[0] != null ? Math.round(la[0] * 100) / 100 : '?'),\n"
        "    load5: (la[1] != null ? Math.round(la[1] * 100) / 100 : '?'),\n"
        "    load15: (la[2] != null ? Math.round(la[2] * 100) / 100 : '?'),\n"
        "    uptime: days + 'd ' + hrs + 'h'\n"
        "  }\n"
        "};\n"
        "var mSwap = {payload: pct(swap.used, swap.total) + ' of ' + gb(swap.total || 0)};\n"
        "var mDisk = {payload: pct(rootfs.used, rootfs.total) + ' of ' + gb(rootfs.total || 0)\n"
        "  + '  (' + gb(rootfs.avail || 0) + ' free)'};\n"
        "var mMem  = {payload: gb(mem2.used || 0) + ' of ' + gb(mem2.total || 0)\n"
        "  + '  (' + gb(mem2.available || 0) + ' avail)'};\n"
        "var mCpu = {payload: cpu, mem: mem, uptime: days + 'd ' + hrs + 'h'};\n"
        "var mMemG = {payload: mem};\n"
        "var mStat = {payload: 'Up ' + days + 'd ' + hrs + 'h' + "
        "(d.loadavg ? ' | load ' + (Math.round(d.loadavg[0]*100)/100) : '')};\n"
        "var mChart = {payload: cpu, topic: 'cpu'};\n"
        "return [mCpu, mMemG, mStat, mChart, detail, mSwap, mDisk, mMem];"
     ),
     "outputs": 8, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 900, "y": 120,
     "wires": [[nid("gg-cpu"), nid("fn-alert-h")], [nid("gg-mem")], [nid("txt-status")],
               [nid("ch-cpu")], [nid("tpl-host")], [nid("txt-swap")],
               [nid("txt-disk")], [nid("txt-mem")]]})
add({"id": nid("dbg-h"), "type": "debug", "z": T, "name": "Proxmox raw",
     "active": True, "tosidebar": True, "console": False, "tostatus": False,
     "complete": "payload", "targetType": "msg", "statusVal": "", "statusType": "auto",
     "x": 740, "y": 200, "wires": []})

# ---------------------------------------------------------------- Tab 7: Home Assistant
T = nid("tab-ha")
add({"id": T, "type": "tab", "label": "Home Assistant", "disabled": False, "info": "Integration with Home Assistant"})
add({"id": nid("uitab-ha"), "type": "ui_tab", "z": T, "name": "Home Assistant",
     "icon": "home", "order": 7, "disabled": False, "hidden": False})
G = nid("grp-ha")
add({"id": G, "type": "ui_group", "z": T, "name": "Home Assistant Control",
     "tab": nid("uitab-ha"), "order": 1, "disp": True, "width": "12", "collapse": False})

# -- HA WebSocket client: state sync + control ------------------------------
# CLASSIC function-node style: the body runs once per incoming message and its
# RETURN value is what gets emitted. Constraints measured on node-red 5.0.7 --
# do not "simplify" these away:
#   * bare `on` is undefined                       -> "ReferenceError: on is not defined"
#   * node.on('input', ...) throws                -> "Cannot add listener to 'input' event within Function"
#   * `send` / `done` are not provided
#   * vars declared in the `initialize` tab are NOT in scope in the body
#   * `context` DOES persist across messages      -> that is where the socket lives
# `ws` is injected as a function parameter by this node's `libs` config; a bare
# `require` is not available in the sandbox.
# out0 = control request -> HA REST Controller;  out1 = state -> dashboard.
HA_WS_FUNC = r"""// Home Assistant WebSocket client.
// STATE PATH  : connect once, authenticate, pull all states, then re-emit
//               state_changed events as {entityId, domain, state, friendlyName, isOn}.
// CONTROL PATH: a boolean from the dashboard switch, or an explicit
//               {domain, service, entityId} on topic 'ha/control', becomes a
//               REST service call.
var WS_PATH = '/api/websocket';
var READ_ONLY = ['sensor', 'binary_sensor', 'input_datetime', 'weather', 'zone', 'device_tracker'];

function normalise(eid, st) {
  var a = st.attributes || {};
  return {
    entityId: eid,
    domain: eid.split('.')[0],
    state: st.state,
    friendlyName: a.friendly_name || eid,
    isOn: st.state === 'on',
    brightnessPct: (a.brightness_pct === undefined ? null : a.brightness_pct)
  };
}

function startWS() {
  var baseUrl = env.get('HA_URL') || 'http://homeassistant.local:8123';
  var token = env.get('HA_TOKEN');
  if (!token) { node.status({fill:'red', shape:'ring', text:'no HA_TOKEN'}); return; }
  var wsUrl = baseUrl.replace(/^http/, 'ws').replace(/\/+$/, '') + WS_PATH;
  var states = {};
  var s = new ws(wsUrl);
  context.set('ha_socket', s);
  node.status({fill:'yellow', shape:'ring', text:'connecting'});
  s.on('open', function () {
    s.send(JSON.stringify({type: 'auth', access_token: token}));
  });
  s.on('message', function (data) {
    var m;
    try { m = JSON.parse(data); } catch (e) { return; }
    if (m.type === 'auth_required') {
      s.send(JSON.stringify({type: 'auth', access_token: token}));
    } else if (m.type === 'auth_ok') {
      node.status({fill:'green', shape:'dot', text:'connected'});
      s.send(JSON.stringify({type: 'get_states'}));
      s.send(JSON.stringify({type: 'subscribe_events', event_type: 'state_changed'}));
    } else if (m.type === 'auth_invalid') {
      node.status({fill:'red', shape:'ring', text:'auth failed'});
      context.set('ha_socket', null);
      try { s.close(); } catch (e) {}
    } else if (m.type === 'result' && m.success && Array.isArray(m.result)) {
      var n = 0;
      m.result.forEach(function (x) { if (x.entity_id) { states[x.entity_id] = x; n++; } });
      node.status({fill:'green', shape:'dot', text:n + ' entities'});
      node.send([null, {payload: n, topic: 'ha/state_count'}]);
    } else if (m.type === 'event' && m.event && m.event.data) {
      var eid = m.event.data.entity_id;
      var ns = m.event.data.new_state;
      if (eid && ns) {
        states[eid] = ns;
        node.send([null, {payload: normalise(eid, ns), topic: 'ha/entity/' + eid + '/state'}]);
      }
    }
  });
  s.on('close', function () { context.set('ha_socket', null); node.status({fill:'grey', shape:'ring', text:'closed'}); });
  s.on('error', function () { node.status({fill:'red', shape:'ring', text:'WS error'}); });
}

// --- per message ------------------------------------------------------------
// Any input -- including the 60s Sync States tick -- makes sure we are connected.
if (!context.get('ha_socket')) { startWS(); }

var req = null;
if (msg.topic === 'ha/control' && msg.payload && typeof msg.payload === 'object') {
  req = msg.payload;                                    // explicit request
} else if (typeof msg.payload === 'boolean') {         // dashboard ui_switch
  // CAVEAT: ui_switch may emit its initial value when the page loads, which
  // actuates once. Harmless for an already-off light; revisit if it matters.
  req = { entityId: env.get('HA_ENTITY_ID'), domain: 'light',
          service: msg.payload ? 'turn_on' : 'turn_off' };
}
if (!req) { return null; }                             // tick only: connect, never actuate
if (!req.entityId) { node.status({fill:'red', shape:'ring', text:'no HA_ENTITY_ID'}); return null; }
if (!req.service)  { node.status({fill:'red', shape:'ring', text:'no service'}); return null; }
if (READ_ONLY.indexOf(req.domain) >= 0) {
  node.status({fill:'red', shape:'ring', text:'read-only'}); return null;
}
var base = (env.get('HA_URL') || '').replace(/\/+$/, '');
if (!base) { node.status({fill:'red', shape:'ring', text:'no HA_URL'}); return null; }
var body = {entity_id: req.entityId};
if (req.serviceData) { for (var k in req.serviceData) { body[k] = req.serviceData[k]; } }
node.status({fill:'blue', shape:'dot', text:req.service});
return [{payload: {url: base + '/api/services/' + req.domain + '/' + req.service,
                   method: 'POST', body: body},
         topic: 'ha/control'}, null];
"""

HA_REST_FUNC = r"""// Format a Home Assistant service call for the HTTP request node.
// Classic function node: the body runs per message and returns what to emit.
// Guard the url so a stray state message cannot throw on msg.url.replace().
if (!msg.url) { node.status({fill:'grey', shape:'ring', text:'no url'}); return null; }
msg.headers = {
  'Authorization': 'Bearer ' + (env.get('HA_TOKEN') || ''),
  'Content-Type': 'application/json'
};
msg.method = msg.method || 'POST';
msg.url = String(msg.url).replace(/\/+$/, '');
msg.payload = msg.body || {};
msg.rejectUnauthorized = false;
node.status({fill:'green', shape:'dot', text:'sending to HA'});
return msg;
"""

# -- HA WebSocket client: out0 control -> REST, out1 state -> debug ---------
add({"id": nid("fn-ha-ws"), "type": "function", "z": T, "name": "HA WebSocket Client",
     "func": HA_WS_FUNC,
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [{"var": "ws", "module": "ws"}],
     "x": 150, "y": 120, "wires": [[nid("fn-ha-rest")], [nid("debug-ha")]]})

# -- HA REST controller (control path) -------------------------------------
add({"id": nid("fn-ha-rest"), "type": "function", "z": T, "name": "HA REST Controller",
     "func": HA_REST_FUNC,
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 400, "y": 120, "wires": [[nid("http-ha")]]})

# -- HTTP request node -----------------------------------------------------
add({"id": nid("http-ha"), "type": "http request", "z": T, "name": "HA REST API",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 620, "y": 120,
     "wires": [[nid("debug-ha")]]})

# -- Debug node ------------------------------------------------------------
add({"id": nid("debug-ha"), "type": "debug", "z": T, "name": "HA Response",
     "active": True, "tosidebar": True, "console": True, "tostatus": False,
     "complete": "payload", "targetType": "msg", "statusVal": "", "statusType": "auto",
     "x": 820, "y": 120, "wires": []})

# -- State sync trigger (re-connects if the socket dropped) ---------------
add({"id": nid("inj-ha"), "type": "inject", "z": T, "name": "Sync States",
     "props": [{"p": "payload"}], "repeat": "60", "crontab": "", "once": True,
     "onceDelay": 2, "topic": "", "payload": "", "payloadType": "date",
     "x": 130, "y": 260, "wires": [[nid("fn-ha-ws")]]})

TEMPLATE_HA_DEVICES = (
    "<table class='table' style='width:100%'>\n"
    "  <thead><tr><th>Device</th><th>Type</th><th>State</th><th></th></tr></thead>\n"
    "  <tbody>\n"
    "    <tr ng-repeat='d in msg.payload track by d.entityId'>\n"
    "      <td>{{d.name}}</td>\n"
    "      <td>{{d.domain}}</td>\n"
    "      <td><span class='status-dot' ng-class=\"d.state === 'on' ? 'ok' : 'warning'\"></span>\n"
    "          {{d.state}}</td>\n"
    "      <td><button ng-if='d.controllable' class='shd-row-btn'"
    " ng-click='haToggle(d)'>{{d.isOn ? 'Turn off' : 'Turn on'}}</button></td>\n"
    "    </tr>\n"
    "    <tr ng-if='!msg.payload || !msg.payload.length'>\n"
    "      <td colspan='4'>{{msg.emptyText || 'No controllable entities yet'}}</td>\n"
    "    </tr>\n"
    "  </tbody>\n"
    "</table>\n"
    # The template's own scope gets `send()`, which is how a tap turns into a
    # flow message. Row data carries domain+service so the shared HA control
    # path (HA WebSocket Client out0 -> HA REST Controller) needs no per-domain
    # branching here.
    "<script>\n"
    "(function (scope) {\n"
    "  scope.haToggle = function (d) {\n"
    "    scope.send({topic: 'ha/control', payload: {\n"
    "      entityId: d.entityId, domain: d.domain, service: d.isOn ? 'turn_off' : 'turn_on'\n"
    "    }});\n"
    "  };\n"
    "})(scope);\n"
    "</script>"
)

# /api/states returns EVERY entity (sensors, automations, zones...). Only these
# domains are user-facing controls; the rest are noise in a device table.
HA_CONTROL_DOMAINS = "['light','switch','fan','cover','climate','media_player','scene','script','lock','input_boolean']"

HA_STATES_BUILD = (
    "// Build GET /api/states. One call returns every entity, so a single\n"
    "// message feeds the table, the summary and the alert evaluator.\n"
    "var base = (env.get('HA_URL') || '').replace(/\\/+$/, '');\n"
    "var token = env.get('HA_TOKEN');\n"
    "if (!base || !token) {\n"
    "  node.status({fill:'red',shape:'ring',text:'missing HA_URL/HA_TOKEN'});\n"
    "  var miss = [];\n"
    "  if (!base) { miss.push('HA_URL'); }\n"
    "  if (!token) { miss.push('HA_TOKEN'); }\n"
    "  msg._error = 'missing ' + miss.join(', ') + ' in /root/.node-red/.env';\n"
    "  msg.topic = 'ha/error';\n"
    "  return [null, null, msg];\n"
    "}\n"
    "msg.method = 'GET';\n"
    "msg.ret = 'obj';\n"
    "msg.url = base + '/api/states';\n"
    "msg.headers = {Authorization: 'Bearer ' + token};\n"
    "msg.rejectUnauthorized = false;\n"
    "node.status({fill:'blue',shape:'dot',text:'polling'});\n"
    "return [msg, null];"
)

HA_STATES_FORMAT = (
    "// Shape /api/states into table rows + alert stats.\n"
    "if (msg.error || !msg.statusCode || msg.statusCode >= 400) {\n"
    "  node.status({fill:'red',shape:'ring',text:'unreachable'});\n"
    "  msg._error = msg.error ? String(msg.error.message || msg.error)\n"
    "    : ('HTTP ' + (msg.statusCode || '?'));\n"
    "  msg.topic = 'ha/error';\n"
    "  return [null, null, msg];\n"
    "}\n"
    "var all = Array.isArray(msg.payload) ? msg.payload : [];\n"
    "var DOMAINS = " + HA_CONTROL_DOMAINS + ";\n"
    "var rows = [];\n"
    "var unavailable = 0;\n"
    "all.forEach(function (e) {\n"
    "  if (!e || !e.entity_id) { return; }\n"
    "  var dom = e.entity_id.split('.')[0];\n"
    "  if (DOMAINS.indexOf(dom) < 0) { return; }\n"
    "  var a = e.attributes || {};\n"
    "  var state = String(e.state || 'unknown');\n"
    "  if (state === 'unavailable' || state === 'unknown') { unavailable++; }\n"
    "  rows.push({\n"
    "    entityId: e.entity_id,\n"
    "    name: a.friendly_name || e.entity_id,\n"
    "    domain: dom,\n"
    "    state: state,\n"
    "    isOn: state === 'on' || state === 'open' || state === 'playing',\n"
    "    controllable: state !== 'unavailable'\n"
    "  });\n"
    "});\n"
    "rows.sort(function (x, y) { return x.name.localeCompare(y.name); });\n"
    "node.status({fill:'green',shape:'dot',text:rows.length + ' devices'});\n"
    "var stats = {total: rows.length, unavailable: unavailable,\n"
    "             controllable: rows.length - unavailable};\n"
    "// out0 = table rows, out1 = summary STRING (a ui_text prints whatever it\n"
    "// is given -- passing it the rows array rendered raw JSON), out2 = alert.\n"
    "return [{payload: rows, emptyText:\n"
    "          all.length ? 'No controllable entities (only sensors/reports)'\n"
    "                     : 'Home Assistant returned no entities'},\n"
    "        {payload: stats.controllable + ' of ' + stats.total + ' ready', _stats: stats},\n"
    "        null];"
)

# -- HA entity control widget ----------------------------------------------
add({"id": nid("sw-ha"), "type": "ui_switch", "z": T, "name": "Light Control",
     "group": G, "order": 1, "width": "6", "height": "4",
     "label": "Primary Light", "tooltip": "Bound to HA_ENTITY_ID (see .env)",
     "x": 130, "y": 340, "wires": [[nid("fn-ha-ws")]]})

# ---- Alerts (order 1): HA unreachable / entities unavailable --------------
G_ALERT = _alert_group("ha", nid("uitab-ha"), T, "Alerts")
add(G_ALERT)
add(_alert_template("ha", G_ALERT["id"], T, 1150, 40))
add({"id": nid("fn-alert-ha"), "type": "function", "z": T, "name": "Evaluate alerts",
     "func": ALERT_EVAL_HA, "outputs": 1, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [], "x": 1080, "y": 300, "wires": [[nid("tpl-alert-ha")]]})
# Unhandled node errors (REST failures, thrown exceptions) become CRITICAL.
add(_catch_node("ha", T, nid("fn-alert-ha"), 1250, 300))

# ---- Device list: REST /api/states -> searchable, tappable table ----------
# WHY REST AND NOT THE WEBSOCKET CLIENT: the WS client maintains its own state
# map inside `context`, which no template can read. /api/states is one GET that
# returns every entity, so the table can render from a single message on a
# timer -- and it works even if the socket is down.
G_DEV = nid("grp-ha-dev")
add({"id": G_DEV, "type": "ui_group", "z": T, "name": "Devices",
     "tab": nid("uitab-ha"), "order": 2, "disp": True, "width": "12", "collapse": False})

add({"id": nid("txt-ha-count"), "type": "ui_text", "z": T, "name": "Device Summary",
     "group": G_DEV, "order": 1, "width": "6", "height": "2",
     "label": "Devices", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 520, "wires": []})
add({"id": nid("tbl-ha-devices"), "type": "ui_template", "z": T, "name": "HA Device List",
     "group": G_DEV, "order": 2, "width": "12", "height": "14",
     "format": TEMPLATE_HA_DEVICES, "storeOutMessages": True, "fwdInMessages": True,
     "resendOnRefresh": True, "templateScope": "local",
     "x": 650, "y": 600, "wires": [[]]})

add({"id": nid("inj-ha-list"), "type": "inject", "z": T, "name": "Refresh devices",
     "props": [{"p": "payload"}], "repeat": "30", "crontab": "", "once": True,
     "onceDelay": 2.5, "topic": "", "payload": "", "payloadType": "date",
     "x": 150, "y": 520, "wires": [[nid("fn-ha-listbuild")]]})

add({"id": nid("fn-ha-listbuild"), "type": "function", "z": T, "name": "Build HA states call",
     "func": HA_STATES_BUILD, "outputs": 3, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [], "x": 380, "y": 520,
     "wires": [[nid("http-ha-list")], [], [nid("fn-alert-ha")]]})
add({"id": nid("http-ha-list"), "type": "http request", "z": T, "name": "HA states",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 620, "y": 520,
     "wires": [[nid("fn-ha-listfmt")]]})
add({"id": nid("fn-ha-listfmt"), "type": "function", "z": T, "name": "Format HA states",
     "func": HA_STATES_FORMAT, "outputs": 3, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [], "x": 850, "y": 520,
     "wires": [[nid("tbl-ha-devices")], [nid("txt-ha-count"), nid("fn-alert-ha")],
               [nid("fn-alert-ha")]]})

# After a service call, re-poll so the table shows the NEW state (~1 message
# later). The service response doubles as the refresh trigger -- no delay node.
add({"id": nid("fn-ha-after"), "type": "function", "z": T, "name": "Trigger refresh",
     "func": ("// Any completed service call re-polls the entity list.\n"
              "msg.payload = Date.now();\n"
              "return msg;"),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 850, "y": 240, "wires": [[nid("fn-ha-listbuild")]]})

# ---------------------------------------------------------------- Tab 3: UniFi Network
T = nid("tab-network")
add({"id": T, "type": "tab", "label": "Network", "disabled": False, "info": ""})
add({"id": nid("uitab-u"), "type": "ui_tab", "z": T, "name": "Network",
     "icon": "wifi", "order": 3, "disabled": False, "hidden": False})

# ---- Alerts (order 1): controller reachability, never collapsible ---------
G_ALERT = _alert_group("network", nid("uitab-u"), T, "Alerts")
add(G_ALERT)
add(_alert_template("network", G_ALERT["id"], T, 1150, 40))
add({"id": nid("fn-alert-u"), "type": "function", "z": T, "name": "Evaluate alerts",
     "func": ALERT_EVAL_NETWORK,
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 1150, "y": 300, "wires": [[nid("tpl-alert-network")]]})
# Every unhandled node error in this tab (http failures, thrown
# exceptions) reaches the same evaluator, so a broken integration
# shows a CRITICAL banner instead of silently keeping its default.
add(_catch_node("network", T, nid("fn-alert-u"), 1200, 380))

G = nid("grp-net")
add({"id": G, "type": "ui_group", "z": T, "name": "Network Overview",
     "tab": nid("uitab-u"), "order": 2, "disp": True, "width": "12", "collapse": False})

add({"id": nid("txt-clients"), "type": "ui_text", "z": T, "name": "Clients Online",
     "group": G, "order": 1, "width": "6", "height": "2",
     "label": "Clients", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 650, "y": 120, "wires": []})
TEMPLATE_CLIENTS = (
    "<table class='table' style='width:100%'>\n"
    "  <thead><tr><th>Client</th><th>IP</th><th>MAC</th></tr></thead>\n"
    "  <tbody>\n"
    "    <tr ng-repeat='c in msg.payload'>\n"
    "      <td>{{c.hostname}}</td><td>{{c.ip}}</td><td>{{c.mac}}</td>\n"
    "    </tr>\n"
    "  </tbody>\n"
    "</table>"
)
TEMPLATE_CARDS = (
    "<table class='table' style='width:100%'>\n"
    "  <thead><tr><th>Task</th><th>Status</th></tr></thead>\n"
    "  <tbody>\n"
    "    <tr ng-repeat='c in msg.payload'>\n"
    "      <td>{{c.task}}</td><td>{{c.status}}</td>\n"
    "    </tr>\n"    "    <tr ng-if='!msg.payload || !msg.payload.length'>\n"
    "      <td colspan='2'>No cards yet - type a task below and tap Add</td>\n"
    "    </tr>\n"
    "  </tbody>\n"
    "</table>"
)

add({"id": nid("tbl-clients"), "type": "ui_template", "z": T, "name": "Client List",
     "group": nid("grp-cdir"), "order": 1, "width": "12", "height": "8",
     "format": TEMPLATE_CLIENTS, "storeOutMessages": True, "fwdInMessages": True,
     "resendOnRefresh": True, "templateScope": "local",
     "x": 650, "y": 220, "wires": [[]]})

# ---- Client Directory: secondary, collapsed by default ---------------------
add({"id": nid("grp-cdir"), "type": "ui_group", "z": T, "name": "Client Directory",
     "tab": nid("uitab-u"), "order": 3, "disp": True, "width": "12",
     "collapse": True, "className": "shd-collapsible"})

add({"id": nid("inj-u"), "type": "inject", "z": T, "name": "Every 60s",
     "props": [{"p": "payload"}], "repeat": "60", "crontab": "", "once": True,
     "onceDelay": 1.0, "topic": "", "payload": "", "payloadType": "date",
     "x": 130, "y": 120, "wires": [[nid("fn-u-login")]]})

# Decide auth mode: API key (X-API-KEY) if set, else legacy cookie login.
# out0 -> cookie login, out1 -> straight to the stat endpoint.
add({"id": nid("fn-u-login"), "type": "function", "z": T, "name": "Build UniFi auth",
     "func": (
        "// UniFi controllers need auth. Credentials come from env vars.\n"
        "// UNIFI_URL may carry a path prefix: UniFi OS (UDM/Cloud Gateway) serves\n"
        "// the Network app under /proxy/network, self-hosted controllers do not.\n"
        "var base = env.get('UNIFI_URL');\n"
        "var site = env.get('UNIFI_SITE') || 'default';\n"
        "var key  = env.get('UNIFI_API_KEY');\n"
        "var user = env.get('UNIFI_USERNAME');\n"
        "var pass = env.get('UNIFI_PASSWORD');\n"
        "msg.rejectUnauthorized = false;\n"
        "msg.headers = {'Accept': 'application/json'};\n"
        "if (!base) {\n"
        "  node.status({fill:'red',shape:'ring',text:'no UNIFI_URL'});\n"
        "  return [null, null, {payload: [], topic: 'unifi/error', "
        "_error: 'UNIFI_URL is not set. Use https://<host>/proxy/network for a UniFi OS console, or https://<host>:8443 for a self-hosted controller'}];\n"
        "}\n"
        "base = base.replace(/\/+$/, '');\n"
        "msg.url_stat = base + '/api/s/' + site + '/stat/sta';\n"
        "if (key) {\n"
        "  node.status({fill:'green',shape:'dot',text:'api key'});\n"
        "  msg.method = 'GET';\n"
        "  msg.url = msg.url_stat;\n"
        "  msg.headers['X-API-KEY'] = key;\n"
        "  // out1 is the API-key path and MUST still go through the HTTP request\n"
        "  // node. Returning it on out0 (the login path) sent it straight to the\n"
        "  // parser, which then read the inject's Date payload instead of client\n"
        "  // data and always rendered 0 clients. Both auth routes converge on the\n"
        "  // same HTTP node; out0 only differs in that it needs a login first.\n"
        "  return [null, msg, null];\n"
        "}\n"
        "if (!user || !pass) {\n"
        "  node.status({fill:'red',shape:'ring',text:'no credentials'});\n"
        "  return [null, null, {payload: [], topic: 'unifi/error', "
        "_error: 'Set UNIFI_API_KEY, or UNIFI_USERNAME + UNIFI_PASSWORD, in the service environment'}];\n"
        "}\n"
        "// Pick the login endpoint. A UniFi OS console (base carries\n"
        "// /proxy/network) authenticates at the console root via /api/auth/login;\n"
        "// self-hosted controllers use /api/login. UNIFI_LOGIN_URL overrides both.\n"
        "var login = env.get('UNIFI_LOGIN_URL');\n"
        "if (!login) {\n"
        "  login = base + '/api/login';\n"
        "  var m = base.match(/^(https?:\\/\\/[^\\/]+)\\/proxy\\/network/);\n"
        "  if (m) { login = m[1] + '/api/auth/login'; }\n"
        "}\n"
        "node.status({fill:'blue',shape:'dot',text:'logging in'});\n"
        "msg.method = 'POST';\n"
        "msg.url = login;\n"
        "msg.headers['Content-Type'] = 'application/json';\n"
        "msg.payload = JSON.stringify({username: user, password: pass, remember: true});\n"
        "return [msg, null];"
     ),
     "outputs": 3, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     # out0 (login required) -> login HTTP node.
     # out1 (API key, request already built) -> the SAME stat HTTP node the
     # login path reaches after Capture session. It must NOT go to the parser
     # directly -- that skipped the request entirely and always rendered 0
     # clients. `msg.url` is already set on both routes, and the http request
     # node is method:"use", so it honours whatever the function set.
     # out2 (config error) -> the PARSER directly: an http request node with
     # no msg.url silently drops the message, and the banner would never
     # learn the controller is unconfigured. The parser's error branch tags
     # the count with topic 'unifi/error' so the banner goes critical.
     "x": 340, "y": 120,
     "wires": [[nid("http-u-login")], [nid("http-u-stat")], [nid("fn-u-parse")]]})

add({"id": nid("http-u-login"), "type": "http request", "z": T, "name": "UniFi login",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 540, "y": 60,
     "wires": [[nid("fn-u-cookie")]]})
add({"id": nid("fn-u-cookie"), "type": "function", "z": T, "name": "Capture session",
     "func": (
        "// Carry the UniFi session cookie (or X-CSRF-Token on newer builds)\n"
        "// into the stat request.\n"
        "var h = msg.headers || {};\n"
        "var setCookie = h['set-cookie'] || h['Set-Cookie'];\n"
        "var cookie = null;\n"
        "if (Array.isArray(setCookie)) { setCookie = setCookie.join('; '); }\n"
        "if (setCookie) {\n"
        "  var part = String(setCookie).split(';')[0];\n"
        "  if (part) { cookie = part; }\n"
        "}\n"
        "if (!cookie) {\n"
        "  node.status({fill:'red',shape:'ring',text:'login failed'});\n"
        "  msg.payload = [];\n"
        "  msg.topic = 'unifi/error';\n"
        "  msg._error = 'UniFi login returned no session cookie (HTTP ' + (msg.statusCode || '?') + ')';\n"
        "  // Failed login -> the PARSER's error branch, not another stat\n"
        "  // request with the login URL (bogus request, drops the real\n"
        "  // error). The parser tags the count 'unifi/error' so the alert\n"
        "  // banner reports the controller as unreachable (critical).\n"
        "  return [msg, msg];\n"
        "}\n"
        "node.status({fill:'green',shape:'dot',text:'session ok'});\n"
        "msg.method = 'GET';\n"
        "msg.url = msg.url_stat;\n"
        "msg.headers = {'Accept': 'application/json'};\n"
        "if (msg.csrfToken || (h['x-csrf-token'])) {\n"
        "  msg.headers['X-CSRF-Token'] = msg.csrfToken || h['x-csrf-token'];\n"
        "}\n"
        "msg.headers['Cookie'] = cookie;\n"
        "return msg;"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     # out0: stat request (normal path). out1: login failure -> parser's
     # error branch directly (a second stat request with the login URL is
     # bogus and would drop the real error).
     "x": 730, "y": 60, "wires": [[nid("http-u-stat")], [nid("fn-u-parse")]]})

add({"id": nid("http-u-stat"), "type": "http request", "z": T, "name": "UniFi clients",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "", "x": 420, "y": 200,
     "wires": [[nid("fn-u-parse")]]})

add({"id": nid("fn-u-parse"), "type": "function", "z": T, "name": "Split client data",
     "func": (
        "// Handles both the success path and the config-error path.\n"
        "if (msg.topic === 'unifi/error' || msg._error) {\n"
        "  node.status({fill:'red',shape:'ring',text:'error'});\n"
        "  var errMsg = msg._error || String(msg.payload || '');\n"
        "  // out0 feeds Clients Online + the alert evaluator. Keep the\n"
        "  // error topic on the count so the banner says 'controller\n"
        "  // unreachable' (critical), not 'no clients' (warning).\n"
        "  return [ {payload: 0, topic: 'unifi/error', _error: errMsg},\n"
        "           {payload: 'ERROR: ' + errMsg} ];\n"
        "}\n"
        "var data = (msg.payload && msg.payload.data) ? msg.payload.data : [];\n"
        "var rows = [];\n"
        "data.forEach(function (c) {\n"
        "  rows.push({hostname: c.hostname || c.name || c.mac, "
        "ip: (c.ip || (c['ip'] || '')), mac: c.mac || ''});\n"
        "});\n"
        "node.status({fill:'green',shape:'dot',text:rows.length + ' clients'});\n"
        "return [ {payload: rows.length}, {payload: rows} ];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 900, "y": 300, "wires": [[nid("txt-clients"), nid("fn-alert-u")], [nid("tbl-clients")]]})

# ---------------------------------------------------------------- Tab 4: Kanban Board
T = nid("tab-kanban")
add({"id": T, "type": "tab", "label": "Kanban", "disabled": False, "info": ""})
add({"id": nid("uitab-k"), "type": "ui_tab", "z": T, "name": "Kanban",
     "icon": "view_column", "order": 4, "disabled": False, "hidden": False})
G = nid("grp-kan")
add({"id": G, "type": "ui_group", "z": T, "name": "Task Board",
     "tab": nid("uitab-k"), "order": 1, "disp": True, "width": "12", "collapse": False})

add({"id": nid("ti-task"), "type": "ui_text_input", "z": T, "name": "New task",
     "label": "New task", "tooltip": "", "group": G, "order": 1, "width": "6", "height": "3",
     "passthru": True, "mode": "text", "delay": 300, "topic": "kanban/new",
     "sendOnBlur": True, "className": "", "x": 130, "y": 120, "wires": [[nid("fn-k-add")]]})
add({"id": nid("btn-add"), "type": "ui_button", "z": T, "name": "Add",
     "group": G, "order": 2, "width": 0, "height": 0, "passthru": False,
     "label": "Add", "tooltip": "", "color": "", "bgcolor": "", "className": "",
     "icon": "", "payload": "", "payloadType": "str", "topic": "kanban/render",
     "topicType": "str", "x": 130, "y": 200, "wires": [[nid("fn-k-render")]]})
add({"id": nid("tbl-cards"), "type": "ui_template", "z": T, "name": "Cards",
     "group": G, "order": 3, "width": "12", "height": "8",
     "format": TEMPLATE_CARDS, "storeOutMessages": True, "fwdInMessages": True,
     "resendOnRefresh": True, "templateScope": "local",
     "x": 650, "y": 220, "wires": [[]]})

add({"id": nid("fn-k-add"), "type": "function", "z": T, "name": "Add card",
     "func": (
        "var task = (typeof msg.payload === 'string' ? msg.payload : '').trim();\n"
        "if (!task) { node.status({fill:'grey',shape:'ring',text:'empty'}); return null; }\n"
        "var cards = null;\n"
        "// Flow context is IN-MEMORY: every redeploy/restart wiped the board\n"
        "// to an empty table -- that is why this tab always looked unpopulated.\n"
        "// Prefer the file-backed store so cards survive a restart, then memory.\n"
        "try { cards = flow.get('kanban_cards', 'file'); } catch (e) { cards = null; }\n"
        "if (!cards) { cards = flow.get('kanban_cards') || []; }\n"
        "cards.push({task: task, status: 'todo'});\n"
        "flow.set('kanban_cards', cards);\n"
        "try { flow.set('kanban_cards', cards, 'file'); } catch (e) {} \n"
        "node.status({fill:'green',shape:'dot',text:cards.length + ' cards'});\n"
        "msg.payload = cards;\n"
        "return [msg, msg];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "flow.set('kanban_cards', flow.get('kanban_cards') || []);",
     "finalize": "", "libs": [], "x": 350, "y": 120,
     "wires": [[nid("tbl-cards")], [nid("dbg-k")]]})
add({"id": nid("fn-k-render"), "type": "function", "z": T, "name": "Render board",
     "func": (
        "var cards = null;\n"
        "// Flow context is IN-MEMORY: every redeploy/restart wiped the board\n"
        "// to an empty table -- that is why this tab always looked unpopulated.\n"
        "// Prefer the file-backed store so cards survive a restart, then memory.\n"
        "try { cards = flow.get('kanban_cards', 'file'); } catch (e) { cards = null; }\n"
        "if (!cards) { cards = flow.get('kanban_cards') || []; }\n"
        "node.status({fill:'blue',shape:'dot',text:cards.length + ' cards'});\n"
        "msg.payload = cards;\n"
        "return [msg, msg];"
     ),
     "outputs": 2, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 350, "y": 200, "wires": [[nid("tbl-cards")], [nid("dbg-k")]]})
add({"id": nid("inj-k"), "type": "inject", "z": T, "name": "Load board",
     "props": [{"p": "payload"}], "repeat": "60", "crontab": "", "once": True,
     "onceDelay": 1.5, "topic": "", "payload": "", "payloadType": "date",
     "x": 140, "y": 280, "wires": [[nid("fn-k-render")]]})
add({"id": nid("dbg-k"), "type": "debug", "z": T, "name": "Cards",
     "active": True, "tosidebar": True, "console": False, "tostatus": False,
     "complete": "payload", "targetType": "msg", "statusVal": "", "statusType": "auto",
     "x": 570, "y": 320, "wires": []})

# ---------------------------------------------------------------- Tab 5: System Health
# REQUIREMENTS_V2 §2: a "System Health" tab acting as a portal to Grafana.
# Two data paths, deliberately different:
#   1. NATIVE summary (Prometheus instant query -> gauges/text). Renders in
#      milliseconds with zero iframe cost, so the tab is never blank while the
#      Grafana panels stream in. This is the "or API" half of the requirement.
#   2. GRAFANA PANEL EMBEDS (one ui_template per panel; each format's own
#      <script> block registers a scope.$watch on msg.p.<key> and sets the
#      iframe src imperatively -- ng-src does NOT work here, see the comment
#      above GRAFANA_EMBED). loading="lazy" keeps
#      off-screen panels from loading on the A7 Lite (6 panels x a full SPA
#      instance each is real RAM on a 3GB tablet).
# Panel ids map 1:1 to the provisioned Grafana dashboard shd-system-health
# (homelab-monitoring repo, stack/grafana/dashboards/shd-system-health.json):
#   1 CPU / 2 Memory / 3 Disk IO / 4 Service Health / 6 ICMP latency / 7 loss.
# Panels 5 (uptime) and 8 (targets) are stat tiles duplicated by the native
# summary widgets, so they are not embedded (one less SPA instance each).
T = nid("tab-syshealth")
add({"id": T, "type": "tab", "label": "System Health", "disabled": False, "info": ""})
add({"id": nid("uitab-sh"), "type": "ui_tab", "z": T, "name": "System Health",
     "icon": "favorite", "order": 5, "disabled": False, "hidden": False})

# ---- Alerts (order 1): whole-stack severity, never collapsible ------------
# Parse health summary attaches the full stat map to its CPU output, so the
# banner evaluates targets/probes/cpu/mem in one message.
G_ALERT = _alert_group("syshealth", nid("uitab-sh"), T, "Alerts")
add(G_ALERT)
add(_alert_template("syshealth", G_ALERT["id"], T, 1150, 40))
add({"id": nid("fn-alert-sh"), "type": "function", "z": T, "name": "Evaluate alerts",
     "func": ALERT_EVAL_HEALTH,
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 1020, "y": 120, "wires": [[nid("tpl-alert-syshealth")]]})
# Every unhandled node error in this tab (http failures, thrown
# exceptions) reaches the same evaluator, so a broken integration
# shows a CRITICAL banner instead of silently keeping its default.
add(_catch_node("syshealth", T, nid("fn-alert-sh"), 1070, 200))

# ---- Group 1: Health Summary (native widgets, no iframes) ----------------
G = nid("grp-sh-sum")
add({"id": G, "type": "ui_group", "z": T, "name": "Health Summary",
     "tab": nid("uitab-sh"), "order": 2, "disp": True, "width": "12", "collapse": False})
add({"id": nid("gg-sh-cpu"), "type": "ui_gauge", "z": T, "name": "PVE CPU",
     "group": G, "order": 1, "width": "6", "height": "5", "gtype": "gage",
     "title": "PVE CPU", "label": "%", "format": "{{value}}", "min": 0, "max": "100",
     "colors": ["#00b500", "#e6e600", "#ca3838"], "seg1": "", "seg2": "",
     "x": 990, "y": 120, "wires": []})
add({"id": nid("gg-sh-mem"), "type": "ui_gauge", "z": T, "name": "PVE Memory",
     "group": G, "order": 2, "width": "6", "height": "5", "gtype": "gage",
     "title": "PVE Memory", "label": "%", "format": "{{value}}", "min": 0, "max": "100",
     "colors": ["#00b500", "#e6e600", "#ca3838"], "seg1": "", "seg2": "",
     "x": 990, "y": 180, "wires": []})
add({"id": nid("txt-sh-targets"), "type": "ui_text", "z": T, "name": "Targets Up",
     "group": G, "order": 3, "width": "6", "height": "2",
     "label": "Prometheus Targets", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 990, "y": 240, "wires": []})
add({"id": nid("txt-sh-probes"), "type": "ui_text", "z": T, "name": "Probes OK",
     "group": G, "order": 4, "width": "6", "height": "2",
     "label": "Blackbox Probes", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 990, "y": 300, "wires": []})
add({"id": nid("txt-sh-uptime"), "type": "ui_text", "z": T, "name": "PVE Uptime",
     "group": G, "order": 5, "width": "12", "height": "2",
     "label": "Uptime", "format": "{{msg.payload}}", "layout": "row-spread",
     "className": "", "x": 990, "y": 360, "wires": []})

add({"id": nid("inj-sh-sum"), "type": "inject", "z": T, "name": "Every 30s",
     "props": [{"p": "payload"}], "repeat": "30", "crontab": "", "once": True,
     "onceDelay": 1.0, "topic": "", "payload": "", "payloadType": "date",
     "x": 150, "y": 120, "wires": [[nid("fn-sh-pq")]]})
add({"id": nid("fn-sh-pq"), "type": "function", "z": T, "name": "Build health query",
     "func": (
        "// One instant query returns every summary stat, tagged with a `stat`\n"
        "// label so a single HTTP round trip feeds all five widgets. Every\n"
        "// expression was verified live against the co-located stack.\n"
        "var base = (env.get('PROMETHEUS_URL') || 'http://192.168.4.145:9090').replace(/\\/+$/, '');\n"
        "var q = 'label_replace(count(up == 1), \"stat\", \"targets_up\", \"\", \"\")'\n"
        "  + ' or label_replace(count(up), \"stat\", \"targets_total\", \"\", \"\")'\n"
        "  + ' or label_replace(100 - (avg(rate(node_cpu_seconds_total{mode=\"idle\"}[5m])) * 100), \"stat\", \"pve_cpu\", \"\", \"\")'\n"
        "  + ' or label_replace(100 * (1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)), \"stat\", \"pve_mem\", \"\", \"\")'\n"
        "  + ' or label_replace(count(probe_success == 1), \"stat\", \"probes_ok\", \"\", \"\")'\n"
        "  + ' or label_replace(count(probe_success), \"stat\", \"probes_total\", \"\", \"\")'\n"
        "  + ' or label_replace((time() - node_boot_time_seconds) / 86400, \"stat\", \"pve_uptime_days\", \"\", \"\")';\n"
        "msg.method = 'GET';\n"
        "msg.url = base + '/api/v1/query?query=' + encodeURIComponent(q);\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 350, "y": 120, "wires": [[nid("http-sh")]]})
add({"id": nid("http-sh"), "type": "http request", "z": T, "name": "Prometheus API",
     "method": "use", "ret": "obj", "paytoqs": "ignore", "url": "", "tls": "",
     "persist": False, "proxy": "", "authType": "",
     "x": 560, "y": 120, "wires": [[nid("fn-sh-parse")]]})
add({"id": nid("fn-sh-parse"), "type": "function", "z": T, "name": "Parse health summary",
     "func": (
        "// Map the stat-labelled instant query onto one message per widget.\n"
        "// Missing stats degrade to 0 rather than 'undefined' text.\n"
        "var r = msg.payload;\n"
        "if (!r || r.status !== 'success' || !r.data || !Array.isArray(r.data.result)) {\n"
        "  node.status({fill:'red',shape:'ring',text:'no data'});\n"
        "  // out0 feeds the alert evaluator. An empty stat map would read as\n"
        "  // 'everything healthy' there -- send stats: null so the banner\n"
        "  // reports 'monitoring unavailable' (critical) instead of lying.\n"
        "  var mFail = { payload: -1, stats: null };\n"
        "  return [mFail, null, null, null, null];\n"
        "}\n"
        "var m = {};\n"
        "r.data.result.forEach(function (s) {\n"
        "  if (s.metric && s.metric.stat && s.value) { m[s.metric.stat] = parseFloat(s.value[1]); }\n"
        "});\n"
        "// Prometheus reachable but zero stats scraped: same as down for\n"
        "// alerting purposes -- the banner must not read it as 'healthy'.\n"
        "if (!m.targets_total && !m.probes_total && !m.pve_cpu && !m.pve_mem) {\n"
        "  var mNone = { payload: -1, stats: {} };\n"
        "  return [mNone, null, null, null, null];\n"
        "}\n"
        "function pct(v) { return isFinite(v) ? Math.round(v * 10) / 10 : 0; }\n"
        "var mCpu = { payload: pct(m.pve_cpu), stats: m };\n"
        "var mMem = { payload: pct(m.pve_mem) };\n"
        "var mTgt = { payload: Math.round(m.targets_up || 0) + ' / ' + Math.round(m.targets_total || 0) + ' up' };\n"
        "var mPrb = { payload: Math.round(m.probes_ok || 0) + ' / ' + Math.round(m.probes_total || 0) + ' ok' };\n"
        "var mUp  = { payload: pct(m.pve_uptime_days) + ' days' };\n"
        "node.status({fill:'green',shape:'dot',text:'ok'});\n"
        "return [mCpu, mMem, mTgt, mPrb, mUp];"
     ),
     "outputs": 5, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 770, "y": 120, "wires": [[nid("gg-sh-cpu"), nid("fn-alert-sh")], [nid("gg-sh-mem")],
                                   [nid("txt-sh-targets")], [nid("txt-sh-probes")],
                                   [nid("txt-sh-uptime")]]})

# ---- Group 2: Proxmox Node Resources (Grafana embeds) ---------------------
G = nid("grp-sh-pve")
add({"id": G, "type": "ui_group", "z": T, "name": "Proxmox Node Resources",
     "tab": nid("uitab-sh"), "order": 3, "disp": True, "width": "12",
     "collapse": True, "className": "shd-collapsible"})

# WHY THE IFRAME src IS SET FROM THE <script> BLOCK, NOT ng-src (live-verified):
# In Angular 1.8 (bundled in node-red-dashboard 3.6.6) an <iframe> src is a
# $sce RESOURCE_URL context. The uiTemplate directive compiles the format
# BEFORE any message has arrived (scope.$watch(attrs.uiTemplate) fires on
# link, when innerScope.msg is still undefined), so {{msg.p.cpu}} evaluates
# to undefined; the ngSrc directive then strips the src/ng-src attributes
# from the DOM entirely and the interpolation never re-runs. Measured live:
# all six iframes rendered with NO src and NO ng-src attribute. $sce would
# also reject the interpolated string as an untrusted RESOURCE_URL anyway.
#
# The dashboard-1.x fix (the pattern documented in ui_template's own help):
# the directive sets window.scope = innerScope around `element.html(value)`
# (bundled dist, uiTemplate directive), and jQuery's .html() (v3.7.1 ships
# with the dashboard; verified live) executes inline <script> blocks
# synchronously inside that call. So `(function(scope){...})(scope)` (bare
# `scope` resolves to window.scope at script time) receives the live scope.
# NOTE: the script runs via jQuery's DOMEval -- a TEMP script appended to
# <head> -- so document.currentScript/previousElementSibling CANNOT be used
# to find the iframe. Instead each iframe gets a STATIC, per-panel id
# (`shd-frame-<key>`; the key is unique across the six templates) and the
# watcher callback looks it up lazily with getElementById -- by the time a
# message arrives the card is fully linked and interpolated, so the lookup
# cannot miss. The watcher only assigns src when the URL string actually
# changes, so the repeating 60s inject re-pushing the same URL never
# reloads the frame -- Grafana's own refresh=30s keeps the data moving.
GRAFANA_EMBED = (
    '<div class="shd-embed">\n'
    '<iframe class="shd-grafana-frame" id="shd-frame-__KEY__" title="__TITLE__" '
    'loading="lazy"></iframe>\n'
    '</div>\n'
    '<script>\n'
    '(function(scope) {\n'
    '  var key = \'__KEY__\';\n'
    '  var frame = null;\n'
    '  scope.$watch(\n'
    '    function() { return scope.msg && scope.msg.p && scope.msg.p[key]; },\n'
    '    function(url) {\n'
    '      if (!url || typeof url !== \'string\') { return; }\n'
    '      if (!frame) { frame = document.getElementById(\'shd-frame-__KEY__\'); }\n'
    '      if (!frame) { return; }\n'
    '      // Reload-storm guard: the repeating inject re-pushes the SAME URL\n'
    '      // string, so only the first assignment hits the DOM and the Grafana\n'
    '      // SPA is never torn down. getAttribute returns the exact assigned\n'
    '      // string, so browser URL-normalisation cannot re-trigger it.\n'
    '      if (frame.getAttribute(\'src\') !== url) { frame.src = url; }\n'
    '    });\n'
    '})(scope);\n'
    '</script>'
)

def grafana_embed(key, title):
    return GRAFANA_EMBED.replace("__KEY__", key).replace("__TITLE__", title)

add({"id": nid("tpl-sh-cpu"), "type": "ui_template", "z": T, "name": "Grafana: PVE CPU",
     "group": G, "order": 1, "width": "12", "height": "8",
     "format": grafana_embed("cpu", "Proxmox Node CPU"),
     "storeOutMessages": True, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "local", "x": 620, "y": 480, "wires": [[]]})
add({"id": nid("tpl-sh-mem"), "type": "ui_template", "z": T, "name": "Grafana: PVE Memory",
     "group": G, "order": 2, "width": "12", "height": "8",
     "format": grafana_embed("mem", "Proxmox Node Memory"),
     "storeOutMessages": True, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "local", "x": 620, "y": 540, "wires": [[]]})
add({"id": nid("tpl-sh-io"), "type": "ui_template", "z": T, "name": "Grafana: PVE Disk IO",
     "group": G, "order": 3, "width": "12", "height": "8",
     "format": grafana_embed("io", "Proxmox Disk I/O Utilization"),
     "storeOutMessages": True, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "local", "x": 620, "y": 600, "wires": [[]]})

# ---- Group 3: LXC / VM Health (Grafana embed) ------------------------------
G = nid("grp-sh-lxc")
add({"id": G, "type": "ui_group", "z": T, "name": "LXC / VM Health",
     "tab": nid("uitab-sh"), "order": 4, "disp": True, "width": "12",
     "collapse": True, "className": "shd-collapsible"})
add({"id": nid("tpl-sh-health"), "type": "ui_template", "z": T, "name": "Grafana: Service Health",
     "group": G, "order": 1, "width": "12", "height": "8",
     "format": grafana_embed("health", "Service Health (LXC / VM / hosts)"),
     "storeOutMessages": True, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "local", "x": 620, "y": 660, "wires": [[]]})

# ---- Group 4: Network Latency (Grafana embeds) ----------------------------
G = nid("grp-sh-net")
add({"id": G, "type": "ui_group", "z": T, "name": "Network Latency",
     "tab": nid("uitab-sh"), "order": 4, "disp": True, "width": "12", "collapse": False})
add({"id": nid("tpl-sh-latency"), "type": "ui_template", "z": T, "name": "Grafana: ICMP Latency",
     "group": G, "order": 1, "width": "12", "height": "8",
     "format": grafana_embed("latency", "Network Latency (blackbox ICMP)"),
     "storeOutMessages": True, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "local", "x": 620, "y": 720, "wires": [[]]})
add({"id": nid("tpl-sh-loss"), "type": "ui_template", "z": T, "name": "Grafana: Packet Loss",
     "group": G, "order": 2, "width": "12", "height": "8",
     "format": grafana_embed("loss", "Packet Loss (blackbox ICMP)"),
     "storeOutMessages": True, "fwdInMessages": False, "resendOnRefresh": True,
     "templateScope": "local", "x": 620, "y": 780, "wires": [[]]})

# ---- Embed URL builder: ONE function, one output wired to every template ----
add({"id": nid("inj-sh-embed"), "type": "inject", "z": T, "name": "Every 60s",
     "props": [{"p": "payload"}], "repeat": "60", "crontab": "", "once": True,
     "onceDelay": 0.5, "topic": "", "payload": "", "payloadType": "date",
     "x": 150, "y": 480, "wires": [[nid("fn-sh-embeds")]]})
add({"id": nid("fn-sh-embeds"), "type": "function", "z": T, "name": "Build Grafana embeds",
     "func": (
        "// d-solo renders ONE panel without the Grafana chrome -- the correct\n"
        "// route for iframes. kiosk strips the remaining nav, theme=dark avoids\n"
        "// a light flash against the dashboard's dark theme, and refresh=30s\n"
        "// lets the panel refresh itself WITHOUT the iframe being reloaded\n"
        "// (each template's <script> only touches src when the URL changes,\n"
        "// so the repeating inject re-pushes the SAME string and the SPA is\n"
        "// never torn down).\n"
        "// The Grafana server must run with allow_embedding=true and anonymous\n"
        "// Viewer access -- see docs/GRAFANA_INTEGRATION.md.\n"
        "var base = (env.get('GRAFANA_URL') || 'http://192.168.4.145:3001').replace(/\\/+$/, '');\n"
        "var uid  = env.get('GRAFANA_DASH_UID') || 'shd-system-health';\n"
        "function solo(panelId) {\n"
        "  return base + '/d-solo/' + uid + '/system-health?orgId=1&panelId=' + panelId\n"
        "       + '&kiosk&theme=dark&from=now-3h&to=now&refresh=30s';\n"
        "}\n"
        "msg.p = {\n"
        "  cpu: solo(1), mem: solo(2), io: solo(3),\n"
        "  health: solo(4), latency: solo(6), loss: solo(7)\n"
        "};\n"
        "node.status({fill:'green',shape:'dot',text:'embeds ready'});\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 370, "y": 480, "wires": [[nid("tpl-sh-cpu"), nid("tpl-sh-mem"), nid("tpl-sh-io"),
                                   nid("tpl-sh-health"), nid("tpl-sh-latency"),
                                   nid("tpl-sh-loss")]]})

# ---------------------------------------------------------------- Tab 6: Settings
T = nid("tab-settings")
add({"id": T, "type": "tab", "label": "Settings", "disabled": False, "info": ""})
add({"id": nid("uitab-s"), "type": "ui_tab", "z": T, "name": "Settings",
     "icon": "settings", "order": 6, "disabled": False, "hidden": False})
G = nid("grp-set")
add({"id": G, "type": "ui_group", "z": T, "name": "System Info",
     "tab": nid("uitab-s"), "order": 1, "disp": True, "width": "6", "collapse": False})
add({"id": nid("txt-info"), "type": "ui_text", "z": T, "name": "Deployment Info",
     "group": G, "order": 1, "width": "6", "height": "4",
     "label": "Info", "format": "{{msg.payload}}", "layout": "row-left",
     "className": "", "x": 640, "y": 120, "wires": []})
add({"id": nid("inj-s"), "type": "inject", "z": T, "name": "Load info",
     # Inject property schema is {"p":<property>,"v":<value>,"vt":<type>} --
     # NOT {"name":...,"value":...}. The wrong keys are silently ignored, the
     # node falls back to payloadType, and the widget renders a timestamp (or
     # nothing) instead of the intended string.
     "props": [{"p": "payload", "v": "Smart Home Dashboard\nNode-RED flows deployed.\n\nSet credentials in the LXC env:\nPROXMOX_URL, PROXMOX_TOKEN, HUBITAT_APP_ID, HUBITAT_ACCESS_TOKEN, HUBITAT_DEVICE_ID, UNIFI_URL", "vt": "str"}],
     # repeat is REQUIRED, not cosmetic: a one-shot inject fires once at DEPLOY
     # time, so any browser that connects afterwards finds the widget empty. A
     # widget only shows data pushed after it subscribed, so every inject that
     # feeds a display must re-fire on an interval.
     "repeat": "300", "crontab": "", "once": True, "onceDelay": 2.0, "topic": "",
     "payload": "", "payloadType": "date", "x": 150, "y": 120, "wires": [[nid("txt-info")]]})

# ---- Theme picker (task t_2fd8fb10) ----------------------------------------
# One ui_button per palette, generated from js/themes.js via PALETTES (parsed
# above): the Settings tab can never offer a palette the browser does not
# ship, and a palette added to js/themes.js shows up here on regeneration.
# ui_dropdown is NOT in the live palette (tools/data/nr-types.txt), so the
# picker is a button row -- one tap per theme, which is also the better touch
# target on the A7 Lite (no dropdown reflow).
G = nid("grp-theme-picker")
add({"id": G, "type": "ui_group", "z": T, "name": "Theme",
     "tab": nid("uitab-s"), "order": 2, "disp": True, "width": "6", "collapse": False})

_THEME_BUTTON_XS = [130, 330, 530, 730, 930]   # one column per button, deterministic
for _i, _pal in enumerate(PALETTES):
    add({"id": nid("btn-theme-" + _pal["id"]), "type": "ui_button", "z": T,
         "name": "Theme: " + _pal["label"], "group": G, "order": 1 + _i,
         "width": 0, "height": 0, "passthru": False,
         "label": _pal["label"], "tooltip": "Switch to " + _pal["label"],
         "color": "", "bgcolor": "", "className": "",
         "icon": "palette", "payload": _pal["id"], "payloadType": "str",
         "topic": "shd/theme", "topicType": "str",
         "x": _THEME_BUTTON_XS[_i % len(_THEME_BUTTON_XS)], "y": 220,
         "wires": [[nid("fn-theme-set")]]})

# "Set theme" (function): the single programmatic entry point.
#   * Accepts msg.payload = palette id from the picker buttons OR any wired
#     Node-RED msg (acceptance criterion: a msg can trigger the change).
#   * msg.socketid is DELETED before passing on: the dashboard's ui.js
#     emitSocket() targets that id when set, and a button click carries it --
#     without the delete, the theme change would reach ONLY the browser that
#     clicked and every other client would stay on the old palette.
#   * msg.enabled / res / req are stripped too (ui.js treats msg.enabled as a
#     widget-disable flag, and res/req are circular and dropped server-side
#     anyway -- keep the payload clean).
#   * Persists the palette id in flow context, and the inject below re-pushes
#     it to all clients on deploy so a Node-RED restart re-syncs browsers
#     whose localStorage holds a different palette.
add({"id": nid("fn-theme-set"), "type": "function", "z": T, "name": "Set theme",
     "func": (
        "var KNOWN = " + json.dumps([p["id"] for p in PALETTES]) + ";\n"
        "var id = (typeof msg.payload === 'string') ? msg.payload.trim().toLowerCase() : '';\n"
        "if (KNOWN.indexOf(id) === -1) {\n"
        "  node.status({fill:'red', shape:'ring', text:'unknown theme: ' + String(msg.payload).slice(0, 20)});\n"
        "  return null;\n"
        "}\n"
        "delete msg.socketid;\n"
        "delete msg.enabled;\n"
        "delete msg.res;\n"
        "delete msg.req;\n"
        "msg.payload = id;\n"
        "flow.set('shd_theme', id);\n"
        "node.status({fill:'green', shape:'dot', text: id});\n"
        "return msg;"
     ),
     "outputs": 1, "noerr": 0, "initialize": "", "finalize": "", "libs": [],
     "x": 350, "y": 220,
     "wires": [[nid("tpl-theme-status")]]})

# Current-theme display + the browser-side bridge (local ui_template):
# The "Set theme" node's output is broadcast by the dashboard to every client
# (socketid was stripped). A LOCAL template's msg arrives on its scope -- the
# same $watch channel the Grafana embeds use -- so the watcher calls
# SHDThemeManager.apply(msg.payload) and writes localStorage. No reload: the
# CSS custom properties flip, the browser repaints, done.
add({"id": nid("tpl-theme-status"), "type": "ui_template", "z": T,
     "name": "Theme status", "group": G, "order": 1 + len(PALETTES),
     "width": 0, "height": 0,
     "format": (
        "<div class=\"shd-muted\">Theme: {{msg.payload || 'default'}}</div>\n"
        "<script>\n"
        "(function(scope) {\n"
        "  scope.$watch(\n"
        "    function() { return scope.msg && scope.msg.payload; },\n"
        "    function(id) {\n"
        "      if (!id || typeof id !== 'string') { return; }\n"
        "      if (window.SHDThemeManager) { window.SHDThemeManager.apply(id); }\n"
        "    });\n"
        "})(scope);\n"
        "</script>"
     ),
     "storeOutMessages": True, "fwdInMessages": True, "resendOnRefresh": True,
     "templateScope": "local", "x": 570, "y": 220, "wires": [[]]})

# On deploy, re-push the persisted palette id so all clients re-sync after a
# Node-RED restart (a client whose localStorage disagrees adopts the
# server-selected palette). repeat=0: one shot, exactly once, at startup.
add({"id": nid("inj-theme-sync"), "type": "inject", "z": T,
     "name": "Re-push theme on deploy",
     "props": [{"p": "payload", "v": "shd_theme", "vt": "flow"}],
     "repeat": "", "crontab": "", "once": True, "onceDelay": 1.0, "topic": "",
     "payload": "", "payloadType": "date", "x": 150, "y": 280,
     "wires": [[nid("fn-theme-set")]]})

# ---------------------------------------------------------------- Tab 8: Kiosk (MQTT)
# Task t_57dfd219 -- WallPanel PRO remote control over MQTT.
#
# The topic contract below is taken from the WallPanel docs (fetched 2026-10-19,
# wallpanel.xyz/docs/remote-control/{mqtt-setup,commands,sensors}, which mirror
# TheTimeWalker/wallpanel-android). Do not invent topic names or payload keys --
# the tablet is the consumer and it only speaks this contract:
#
#   IN   <base>/command                 {"wake":true,"wakeTime":180}
#                                       {"brightness":1-255}      <- 1-255, NOT %
#                                       {"eval":"<javascript>"}
#   OUT  <base>/state                   {"currentUrl":..,"screenOn":bool,"brightness":N}
#   OUT  <base>/sensor/motion           {"value":true|false}      <- immediate on detect
#   OUT  <base>/sensor/<kind>           {"unit":..,"value":..}
#
# base = wallpanel/a7lite (WallPanel's "base topic" setting; must be unique per
# device, so it is pinned here rather than left at the default mywallpanel).
#
# Broker: no MQTT broker existed anywhere on the LAN before this task, so the
# Host: the HAOS Mosquitto add-on, chosen over standing up a second broker.
# Pinned as the tailnet IP rather than the MagicDNS name so the flow does not
# depend on the LXC's resolver: reachability of 100.104.204.118:1883 FROM THE
# DASHBOARD LXC was measured (reversible probe -> "CONNACK code=5"), and that
# also proved the broker speaks MQTT and is reachable on the tailnet.
#
# Pinned in the flow rather than read from env on purpose: env is read only at
# Node-RED process start, and there is no shell on the dashboard LXC to restart
# it -- an env-sourced host would sit on "undefined" forever. Same reason the
# Grafana/Prometheus URLs are literals.
#
# Credentials are NOT in this file. They are written to the runtime's credential
# store with POST /flows using the v2 API object form:
#   {"flows": [...], "credentials": {"<broker-node-id>": {"user": .., "password": ..}}}
# Verified accepted (HTTP 200). The v1 array form cannot carry credentials.
MQTT_BROKER_HOST = "100.104.204.118"
MQTT_BROKER_PORT = 1883
WP_BASE = "wallpanel/a7lite"
WP_CMD_TOPIC = WP_BASE + "/command"
WP_STATE_TOPIC = WP_BASE + "/state"
WP_MOTION_TOPIC = WP_BASE + "/sensor/motion"

# WallPanel brightness is 1-255 (documented range). Buckets are keyed on the
# local hour; the retained publish makes a reconnecting tablet pick up the
# current brightness immediately instead of waiting for the next tick.
WP_BRIGHTNESS = {"night": 40, "dawn": 120, "day": 200, "dusk": 110}

# View indices come from the ui_tab `order` fields above, sorted, hidden tabs
# excluded -- NOT from file order. Measured live 2026-10-19: the nav reads
# 0=Home Lab, 1=Network, 2=Kanban, 3=System Health, 4=Settings, 5=Home Assistant,
# and setting location.hash='#!/2' really does land on Kanban with no reload.
#
# The dashboard routes tabs by URL hash (live hash: '#!/0?socketid=...'), so
# switching a view is a hash write -- no reload, no re-navigation, no flicker.
# That is what makes WallPanel's {"eval":...} command a view switcher here.
WP_VIEWS = [
    ("homelab",  "Home Lab",       1),
    ("network",  "Network",        3),
    ("kanban",   "Kanban",         4),
    ("health",   "System Health",  5),
    ("settings", "Settings",       6),
    ("ha",       "Home Assistant", 7),
]
WP_VIEW_INDEX = {key: i for i, (key, _label, _order) in enumerate(
    sorted(WP_VIEWS, key=lambda v: v[2]))}

T = nid("tab-kiosk")
add({"id": T, "type": "tab", "label": "Kiosk", "disabled": False,
     "info": "WallPanel PRO tablet control over MQTT"})
add({"id": nid("uitab-kiosk"), "type": "ui_tab", "z": T, "name": "Kiosk",
     "icon": "tablet", "order": 8, "disabled": False, "hidden": False})

# ---- Broker config ---------------------------------------------------------
add({"id": nid("mqtt-broker"), "type": "mqtt-broker", "name": "SHD MQTT",
     "broker": MQTT_BROKER_HOST, "port": str(MQTT_BROKER_PORT), "clientid": "",
     "autoConnect": True, "usetls": False, "protocolVersion": "4",
     "keepalive": "60", "cleansession": True, "autoUnsubscribe": True,
     "birthTopic": "", "birthQos": "0", "birthRetain": "false", "birthPayload": "",
     "closeTopic": "", "closeQos": "0", "closeRetain": "false", "closePayload": "",
     "willTopic": "", "willQos": "0", "willRetain": "false", "willPayload": ""})

# ---- Group 1: tablet status ------------------------------------------------
G = nid("grp-kiosk-status")
add({"id": G, "type": "ui_group", "z": T, "name": "Tablet",
     "tab": nid("uitab-kiosk"), "order": 1, "disp": True, "width": "6",
     "collapse": False})

add({"id": nid("tpl-kiosk-status"), "type": "ui_template", "z": T,
     "name": "Tablet Status", "group": G, "order": 1, "width": "6",
     "height": "3", "format": """<div class="shd-kiosk">
  <!-- Before the first <base>/state message arrives msg.payload is undefined.
       Angular renders the false branch of a ternary for undefined, so a bare
       {{x ? 'ON' : 'screensaver'}} reported a confident "screensaver" for a
       tablet that had never checked in. Guard on the payload itself. -->
  <div class="shd-kiosk-row"><span>Screen</span><b>{{msg.payload ? (msg.payload.screenOn ? 'ON' : 'screensaver') : 'no data'}}</b></div>
  <div class="shd-kiosk-row"><span>Brightness</span><b>{{msg.payload ? msg.payload.brightness : '--'}}</b>/255</div>
  <div class="shd-kiosk-row"><span>View</span><b>{{msg.payload ? msg.payload.currentUrl : '--'}}</b></div>
  <div class="shd-kiosk-row"><span>Last seen</span><b>{{msg.payload ? msg.payload.age : 'never'}}</b></div>
</div>""", "storeOutMessages": True, "fwdInMessages": True,
     "templateScope": "local", "x": 640, "y": 120, "wires": []})

# ---- Group 2: manual controls ---------------------------------------------
G2 = nid("grp-kiosk-control")
add({"id": G2, "type": "ui_group", "z": T, "name": "Remote control",
     "tab": nid("uitab-kiosk"), "order": 2, "disp": True, "width": "6",
     "collapse": False})

add({"id": nid("btn-kiosk-wake"), "type": "ui_button", "z": T,
     "name": "Wake", "group": G2, "order": 1, "width": 6, "height": 1,
     "passthru": False, "label": "Wake tablet", "tooltip": "Wake the tablet screen",
     # NO icon. Two Font Awesome names (sun-o, lightbulb-o) both rendered as a
     # literal "?" glyph on the live A7-lite view -- this dashboard build ships a
     # reduced icon set. The button label carries the meaning; a "?" does not.
     "color": "", "bgcolor": "", "className": "", "icon": "",
     "payload": "wake", "payloadType": "str", "topic": "kiosk/wake",
     "topicType": "str", "x": 130, "y": 260, "wires": [[nid("fn-kiosk-cmd")]]})

for _i, (_key, _label, _order) in enumerate(sorted(WP_VIEWS, key=lambda v: v[2])):
    add({"id": nid("btn-kiosk-view-" + _key), "type": "ui_button", "z": T,
         "name": "View: " + _label, "group": G2, "order": 10 + _i,
         "width": 3, "height": 1, "passthru": False, "label": _label,
         "tooltip": "Switch tablet to " + _label, "color": "", "bgcolor": "",
         # No icon: the six view labels are the touch targets and long names
         # ("System Health", "Home Assistant") need the full button width.
         "className": "", "icon": "",
         "payload": _key, "payloadType": "str", "topic": "kiosk/view",
         "topicType": "str", "x": 130, "y": 300 + 40 * _i,
         "wires": [[nid("fn-kiosk-cmd")]]})

# ---- Command builder + output ---------------------------------------------
# ONE function builds every outbound payload and ONE mqtt out publishes it, so
# there is a single place where a malformed command can exist. Payloads are
# JSON.stringify'd strings: WallPanel parses the payload as JSON, and handing
# it a JS object through MQTT would serialise to "[object Object]".
_view_map_js = ", ".join(
    "'%s': %d" % (k, WP_VIEW_INDEX[k])
    for k in sorted(WP_VIEW_INDEX, key=lambda k: WP_VIEW_INDEX[k])
)
add({"id": nid("fn-kiosk-cmd"), "type": "function", "z": T,
     "name": "Build kiosk command", "func": (
"""// Classic function style: runs per message, `return` is what gets emitted.
// Turns a UI action (or the motion path) into a WallPanel command payload.
// Keys and ranges are the documented WallPanel contract:
//   wake/brightness/eval -- see tools/gen_flows.py Tab 8 header.
var VIEWS = {""" + _view_map_js + """};

var t = String(msg.topic || '');
var p = msg.payload;

if (t === 'kiosk/wake') {
    // wakeTime keeps the screen on for 180s, then the app returns to its
    // screensaver on user inactivity (documented wake behaviour).
    msg.payload = JSON.stringify({ wake: true, wakeTime: 180 });
} else if (t === 'kiosk/view') {
    var key = String(p || '').trim().toLowerCase();
    var idx = VIEWS.hasOwnProperty(key) ? VIEWS[key] : parseInt(key, 10);
    if (!isFinite(idx)) { return null; }
    // Hash routing verified live: this switches the visible tab with no reload.
    msg.payload = JSON.stringify({ eval: "location.hash='#!/" + idx + "'" });
} else if (typeof p === 'object' && p !== null &&
           (p.hasOwnProperty('wake') || p.hasOwnProperty('eval'))) {
    // Already a command (motion path reuses this node) -- pass through.
    msg.payload = JSON.stringify(p);
} else {
    // Unknown action: emit nothing rather than an empty command the tablet
    // would log as a parse error.
    return null;
}

msg.topic = '""" + WP_CMD_TOPIC + """';
return msg;"""),
     "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "",
     "finalize": "", "libs": [], "x": 430, "y": 260,
     "wires": [[nid("mqtt-out-cmd")]]})

add({"id": nid("mqtt-out-cmd"), "type": "mqtt out", "z": T,
     "name": "Kiosk command", "topic": WP_CMD_TOPIC, "qos": "1",
     "retain": "false", "respTopic": "", "contentType": "",
     "userProps": "", "correl": "", "expiry": "", "broker": nid("mqtt-broker"),
     "x": 680, "y": 260, "wires": []})

# ---- Motion -> wake --------------------------------------------------------
# WallPanel publishes {"value":true} to <base>/sensor/motion the moment its
# camera sees motion. That is a screen-wake trigger already on the network, so
# no separate PIR/sensor integration is needed for the "wake on approach" path.
add({"id": nid("fn-kiosk-motion"), "type": "function", "z": T,
     "name": "Motion -> wake", "func": (
"""// WallPanel motion payload is {"value": true|false}. Only a real rising
// edge should wake the screen: the false edge is published too, and waking on
// it would defeat the screensaver.
var v = msg.payload;
var on = (v === true) ||
         (v && typeof v === 'object' && v.value === true) ||
         (typeof v === 'string' && v.trim().toLowerCase() === 'true');
if (!on) { return null; }

// wakeTime 180s: long enough to read the dashboard after walking up to it,
// after which the app falls back to its screensaver on inactivity.
//
// Emit an OBJECT, not a JSON string: this feeds `Build kiosk command`, which is
// the single place that stringifies. Handing it an already-stringified payload
// meant its hasOwnProperty('wake') pass-through branch never matched (a string
// has no own properties) and the wake command was silently dropped -- measured
// 2026-10-19: the retained brightness publish worked, the motion wake did not.
msg.payload = { wake: true, wakeTime: 180 };
return msg;"""),
     "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [], "x": 430, "y": 400, "wires": [[nid("fn-kiosk-cmd")]]})

add({"id": nid("mqtt-in-motion"), "type": "mqtt in", "z": T,
     "name": "Tablet motion", "topic": WP_MOTION_TOPIC, "qos": "0",
     "datatype": "json", "broker": nid("mqtt-broker"), "nl": False,
     "rap": True, "rh": 0, "inputs": 0, "x": 150, "y": 400,
     "wires": [[nid("fn-kiosk-motion")]]})

# ---- Time of day -> brightness --------------------------------------------
# Retained on purpose: a tablet that reboots or reconnects gets the current
# brightness replayed by the broker instead of sitting at whatever the previous
# bucket was. Wake/eval are NOT retained -- a retained wake would re-wake the
# screen on every reconnect.
add({"id": nid("fn-kiosk-brightness"), "type": "function", "z": T,
     "name": "Schedule -> brightness", "func": (
"""// WallPanel brightness range is 1-255 (documented), NOT a percentage.
var B = { night: """ + str(WP_BRIGHTNESS["night"]) + """, dawn: """ + str(WP_BRIGHTNESS["dawn"]) + """,
          day: """ + str(WP_BRIGHTNESS["day"]) + """, dusk: """ + str(WP_BRIGHTNESS["dusk"]) + """ };

var h = new Date().getHours();
var bucket;
if (h >= 22 || h < 7)      { bucket = 'night'; }
else if (h < 9)            { bucket = 'dawn';  }
else if (h < 18)           { bucket = 'day';   }
else                       { bucket = 'dusk';  }

var level = B[bucket];
// Re-publish when the bucket changes OR when we have not published in 30 min.
// The periodic re-publish is deliberate self-healing: a retained message can be
// dropped by a broker restart, and the tablet has no way to ask for it again.
var prev = context.get('bucket');
var last = context.get('lastPublish') || 0;
var due = prev !== bucket || (Date.now() - last) > 30 * 60 * 1000;
if (!due) { return null; }
context.set('bucket', bucket);
context.set('lastPublish', Date.now());

msg.payload = JSON.stringify({ brightness: level });
msg.topic = '""" + WP_CMD_TOPIC + """';
return msg;"""),
     "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [], "x": 450, "y": 520, "wires": [[nid("mqtt-out-brightness")]]})

add({"id": nid("mqtt-out-brightness"), "type": "mqtt out", "z": T,
     "name": "Brightness (retained)", "topic": WP_CMD_TOPIC, "qos": "1",
     "retain": "true", "respTopic": "", "contentType": "",
     "userProps": "", "correl": "", "expiry": "", "broker": nid("mqtt-broker"),
     "x": 700, "y": 520, "wires": []})

# repeat is REQUIRED for the schedule tick (see the Settings-tab note): a
# one-shot inject fires only at deploy time and would leave the tablet at
# whatever brightness it last held.
add({"id": nid("inj-kiosk-sched"), "type": "inject", "z": T,
     "name": "Schedule tick", "props": [{"p": "payload", "v": "", "vt": "str"}],
     "repeat": "300", "crontab": "", "once": True, "onceDelay": 5.0,
     "topic": "", "payload": "", "payloadType": "date",
     "x": 160, "y": 520, "wires": [[nid("fn-kiosk-brightness")]]})

# ---- Tablet state -> status widget ----------------------------------------
add({"id": nid("fn-kiosk-state"), "type": "function", "z": T,
     "name": "Tablet state", "func": (
"""// WallPanel publishes application state to <base>/state as
// {"currentUrl":..,"screenOn":bool,"brightness":N}.
var p = msg.payload;
if (typeof p === 'string') {
    try { p = JSON.parse(p); } catch (e) { return null; }
}
if (!p || typeof p !== 'object') { return null; }

var url = String(p.currentUrl || '');
// Send only the tab portion: the full URL is long and wraps the widget.
var m = url.match(/#!\\/(\\d+)/);
var tab = m ? '#' + m[1] : (url ? url.slice(-28) : 'unknown');

msg.payload = {
    screenOn: p.screenOn === true,
    brightness: (p.brightness === 0 || p.brightness) ? p.brightness : '?',
    currentUrl: tab,
    age: 'just now'
};
context.set('lastSeen', Date.now());
return msg;"""),
     "outputs": 1, "timeout": 0, "noerr": 0, "initialize": "", "finalize": "",
     "libs": [], "x": 420, "y": 640, "wires": [[nid("tpl-kiosk-status")]]})

add({"id": nid("mqtt-in-state"), "type": "mqtt in", "z": T,
     "name": "Tablet state", "topic": WP_STATE_TOPIC, "qos": "0",
     "datatype": "json", "broker": nid("mqtt-broker"), "nl": False,
     "rap": True, "rh": 0, "inputs": 0, "x": 150, "y": 640,
     "wires": [[nid("fn-kiosk-state")]]})

# ---------------------------------------------------------------- write files
os.makedirs(OUT, exist_ok=True)
files = {
    "01-home-lab-monitor.flow.json":   flows_all[:len([n for n in flows_all])],
}
# Split by tab for readability: group nodes by their tab id
by_tab = {}
for node in flows_all:
    if node["type"] == "tab":
        key = node["id"]
    else:
        key = node.get("z", "orphan")
    by_tab.setdefault(key, []).append(node)

labels = {
    nid("tab-homelab"): "01-home-lab-monitor.flow.json",
    nid("tab-network"): "03-unifi-network.flow.json",
    nid("tab-kanban"):  "04-kanban-board.flow.json",
    nid("tab-syshealth"): "05-system-health.flow.json",
    nid("tab-settings"):"06-settings.flow.json",
    nid("tab-ha"):"07-home-assistant.flow.json",
    nid("tab-kiosk"):"08-kiosk.flow.json",
}
written = []
by_file = {}
for tab_id, nodes in by_tab.items():
    # Config nodes (mqtt-broker, tls-config, ...) are global and carry no `z`,
    # so they all collide on the "orphan" bucket. Give them a predictable file
    # instead of letting them land in 99-other, which is meant for unexpected
    # nodes only. A stale 99-other.flow.json used to sit in the repo carrying an
    # old copy of the HA tab; a test asserted against that dead file and passed
    # while describing the wrong location. Regenerating 99-other with the broker
    # exposed it.
    if tab_id == "orphan":
        fname = "00-config.flow.json"
    else:
        fname = labels.get(tab_id, "99-other.flow.json")
    by_file.setdefault(fname, []).extend(nodes)  # accumulate -- multiple
    # unlabeled tabs (e.g. Home Assistant, ui_base config) must all survive,
    # not clobber each other in a last-write-wins loop.
for fname, nodes in by_file.items():
    with open(os.path.join(OUT, fname), "w") as fh:
        json.dump(nodes, fh, indent=2)
    written.append((fname, len(nodes)))

# Also write one combined file for single-shot import
with open(os.path.join(OUT, "all-flows.flow.json"), "w") as fh:
    json.dump(flows_all, fh, indent=2)

print("Generated files in", OUT)
for fname, count in written:
    print(f"  {fname}: {count} nodes")
print(f"  all-flows.flow.json: {len(flows_all)} nodes total")

# validation against live palette
palette_path = os.path.join(_ROOT, "tools", "data", "nr-types.txt")
palette = set()
with open(palette_path) as fh:
    for line in fh:
        if line.strip():
            palette.add(line.strip())
used = sorted({n["type"] for n in flows_all})
missing = [t for t in used if t not in palette and t not in ("tab",)]
print("\nNode types used:", ", ".join(used))
if missing:
    print("MISSING FROM PALETTE:", ", ".join(missing))
else:
    print("OK: every node type used exists in the live palette")
