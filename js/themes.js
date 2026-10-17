/* ============================================================================
   Smart Home Dashboard -- Theme Manager (task t_2fd8fb10)
   ----------------------------------------------------------------------------
   Palettes map EVERY colour token declared in css/dashboard.css :root to a
   concrete value. The runtime manager applies a palette by setting the CSS
   custom properties on document.documentElement -- no stylesheet swap, no
   page reload, no layout shift (only colour properties are touched; the
   non-colour tokens --shd-touch-target / --shd-radius are never overridden).

   HOW THIS FILE IS DEPLOYED (important for anyone editing it):
   The dashboard serves no static assets (httpStatic is unset), so js/themes.js
   is NOT loaded by the browser as a file. tools/gen_flows.py INLINES this file
   into a global-scope ui_template ("Theme manager", hidden Theme tab) that the
   dashboard appends to <head>; its inline script executes on load -- the same
   mechanism the mobile theme's <style> block already uses. The generator also
   parses the palette ids/labels out of THIS file to build the Settings-tab
   picker buttons and the "Set theme" validator, so the UI can never drift from
   the palettes actually shipped. Regenerate flows after editing:
       python3 tools/gen_flows.py     (CI re-runs it and diffs flows/)

   SWITCHING CHANNELS (both verified against the node-red-dashboard 3.6.6
   server/client sources):
   - Pick a palette: Settings tab buttons -> "Set theme" function -> this
     module's apply(), broadcast over the dashboard socket to every client.
   - Programmatic: any Node-RED msg with msg.payload = palette id wired into
     the "Set theme" function node switches the theme the same way.
   The "Set theme" node deletes msg.socketid before emitting -- ui.js
   emitSocket() would otherwise deliver the change only to the browser that
   clicked the button.

   PERSISTENCE: apply() writes localStorage, so a refresh re-applies the
   chosen palette during boot (below) with no flash of the wrong theme. The
   "Set theme" function ALSO records the palette id in flow context, and an
   inject re-pushes it on deploy so every connected client re-syncs after a
   Node-RED restart.

   COLOUR SOURCES: the only colour definitions in this repository are (a) the
   :root block in css/dashboard.css -- the default palette -- and (b) the
   palettes in this module. Applying 'default' REMOVES the inline overrides so
   the stylesheet wins again, which makes stale-default drift structurally
   impossible; tests/test_theme_manager.py additionally asserts the 'default'
   palette mirrors :root exactly and that every palette clears the WCAG floors.
   ============================================================================ */
(function (global) {
  'use strict';

  /* ---------------------------------------------------------------- palettes */

  /* Token order mirrors css/dashboard.css :root. Colour values were checked
     against WCAG AA (>= 4.5:1 for body text on bg/surface/card, >= 3:1 for
     status/accent text); tests/test_theme_manager.py recomputes the ratios
     from these definitions, so a below-floor palette fails CI. */
  var THEMES = {
    'default': {
      label: 'Midnight (default)',
      tokens: {
        '--shd-bg':        '#1a1a2e',
        '--shd-surface':   '#16213e',
        '--shd-card':      '#1f2b47',
        '--shd-accent':    '#667eea',
        '--shd-accent-2':  '#764ba2',
        '--shd-text':      '#eeeeee',
        '--shd-muted':     '#b8c4de',
        '--shd-text-dim':  '#aaaabb',
        '--shd-ok':        '#2ecc71',
        '--shd-warn':      '#f1c40f',
        '--shd-err':       '#ff7676'
      }
    },
    'nord': {
      label: 'Nord',
      tokens: {
        '--shd-bg':        '#2e3440',
        '--shd-surface':   '#3b4252',
        '--shd-card':      '#434c5e',
        '--shd-accent':    '#88c0d0',
        '--shd-accent-2':  '#5e81ac',
        '--shd-text':      '#eceff4',
        '--shd-muted':     '#d8dee9',
        '--shd-text-dim':  '#b8c2d0',
        '--shd-ok':        '#b9d49e',
        '--shd-warn':      '#ebcb8b',
        '--shd-err':       '#f7b1bd'
      }
    },
    'cyberpunk': {
      label: 'Cyberpunk',
      tokens: {
        '--shd-bg':        '#0d0221',
        '--shd-surface':   '#190b33',
        '--shd-card':      '#26123f',
        '--shd-accent':    '#00f0ff',
        '--shd-accent-2':  '#ff2a6d',
        '--shd-text':      '#f0eaff',
        '--shd-muted':     '#c9b8ff',
        '--shd-text-dim':  '#b8a8e0',
        '--shd-ok':        '#05ffa1',
        '--shd-warn':      '#fcee0a',
        '--shd-err':       '#ff2a6d'
      }
    }
  };

  var STORAGE_KEY = 'shd_theme';

  /* ---------------------------------------------------------------- runtime */

  function normaliseId(id) {
    if (typeof id !== 'string') { return null; }
    var key = id.trim().toLowerCase();
    return THEMES.hasOwnProperty(key) ? key : null;
  }

  /* Apply every token of a palette onto the document root. Returns the
     applied palette id, or null for an unknown palette.

     'default' REMOVES the inline overrides instead of writing values, so the
     :root block in css/dashboard.css is the single source of the default
     colours and the shipped stylesheet always wins when "default" is active. */
  function applyTheme(id) {
    var key = normaliseId(id);
    if (!key) { return null; }
    var root = global.document && global.document.documentElement;
    if (!root) { return null; }
    var tokens = THEMES[key].tokens;
    for (var name in tokens) {
      if (tokens.hasOwnProperty(name)) {
        if (key === 'default') {
          root.style.removeProperty(name);
        } else {
          root.style.setProperty(name, tokens[name]);
        }
      }
    }
    try { global.localStorage.setItem(STORAGE_KEY, key); } catch (e) { /* private mode */ }
    return key;
  }

  /* Apply the stored (or default) palette at boot. The generator places this
     call in the global head template, which the dashboard appends to <head>
     during connect -- before the tab content renders -- so the correct palette
     is already active at first paint: no flash of the wrong theme. */
  function initTheme() {
    var stored = null;
    try { stored = global.localStorage.getItem(STORAGE_KEY); } catch (e) { /* private mode */ }
    return applyTheme(stored || 'default');
  }

  global.SHD_THEMES = THEMES;
  global.SHDThemeManager = {
    apply: applyTheme,
    init: initTheme,
    list: function () {
      var out = [];
      for (var k in THEMES) {
        if (THEMES.hasOwnProperty(k)) { out.push({ id: k, label: THEMES[k].label }); }
      }
      return out;
    },
    current: function () {
      try { return global.localStorage.getItem(STORAGE_KEY) || 'default'; }
      catch (e) { return 'default'; }
    }
  };
})(typeof window !== 'undefined' ? window : globalThis);