/* ==========================================================================
   Dynamic Background Engine  (card t_8b8679a9)
   --------------------------------------------------------------------------
   Ambient background that follows BOTH the time of day and system state.

   WHY IT WRITES ONE DERIVED TOKEN INSTEAD OF --shd-bg
   ---------------------------------------------------
   The Theme Manager (js/themes.js) owns --shd-bg: it is the palette's base
   colour, and applyTheme() rewrites it on every switch. If this engine also
   wrote --shd-bg the two would fight, and whichever ran last would win -- a
   theme switch would silently cancel the night state (or vice versa).

   So this engine computes  --shd-bg-effective  = palette --shd-bg COMPOSITED
   with the current state tint, and CSS paints `body` from that with --shd-bg
   as the fallback:

       body.nr-dashboard-theme {
         background-color: var(--shd-bg-effective, var(--shd-bg));
       }

   Consequences: switching palette immediately re-derives the effective colour
   (no cancellation), and the state tint survives theme changes. Only ONE
   custom property changes per transition -- no layout, no reflow, no FOUC.
   The smoothness comes from a background-color transition in CSS, which the
   compositor handles; @media (prefers-reduced-motion: reduce) turns it off.

   TWO INDEPENDENT TRIGGERS (both required by the card)
   ---------------------------------------------------
   1. TIME   -- setInterval every 30s recomputes the period. Cheap: a Date
                read plus at most one style write when the period changed.
   2. STATE  -- SHDBackground.setSeverity('critical'|'warning'|'ok') from the
                alert banners. A state override holds for OVERRIDE_MS, then
                decays back to the time-of-day state on the next tick, so one
                bad reading cannot tint the screen forever.

   Deliberately dependency-free and idempotent: the dashboard tears down and
   re-appends global head templates on every (re)connect, so init() may run
   many times. Only one interval is ever kept.
   ========================================================================== */
(function (global) {
  'use strict';

  /* Ambient tints, composited OVER the palette background. Alpha is the whole
     point: 0 means "hand the palette colour back untouched" (daytime). */
  var PERIOD_TINTS = {
    night: 'rgba(2, 4, 14, 0.55)',      /* 22:00-06:00  deep, low-glare      */
    dawn:  'rgba(60, 32, 12, 0.30)',    /* 06:00-08:00  warm, waking         */
    day:   'rgba(0, 0, 0, 0)',          /* 08:00-17:00  palette as authored  */
    dusk:  'rgba(56, 20, 44, 0.35)'     /* 17:00-22:00  warm, winding down   */
  };

  /* State overrides. Critical is a red wash strong enough to be noticed on a
     wall panel without making card text unreadable. */
  var SEVERITY_TINTS = {
    critical: 'rgba(120, 10, 10, 0.45)',
    warning:  'rgba(120, 80, 0, 0.28)',
    ok:       ''
  };

  var OVERRIDE_MS = 60000;   /* a state override decays after 60s */
  var TICK_MS = 30000;       /* time-based recompute cadence */

  var state = { period: null, severity: 'ok', overrideUntil: 0, timer: null };

  function periodForHour(h) {
    if (h >= 22 || h < 6) { return 'night'; }
    if (h < 8) { return 'dawn'; }
    if (h < 17) { return 'day'; }
    return 'dusk';
  }

  function parseColor(str) {
    if (!str) { return null; }
    var s = String(str).trim();
    var m = s.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
    if (m) {
      var h = m[1];
      if (h.length === 3) { h = h[0] + h[0] + h[1] + h[1] + h[2] + h[2]; }
      return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16),
              parseInt(h.slice(4, 6), 16), 1];
    }
    var r = s.match(/^rgba?\(([^)]+)\)$/i);
    if (r) {
      var p = r[1].split(',').map(function (v) { return parseFloat(v); });
      return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
    }
    return null;
  }

  /* Composite `over` (with its alpha) onto `base`. Returns rgb()/rgba(). */
  function composite(base, over) {
    var b = parseColor(base);
    var o = parseColor(over);
    if (!o || !o[3]) { return base; }            /* nothing to apply */
    if (!b) { return over; }                     /* no palette: tint alone */
    var a = o[3];
    var mix = [
      Math.round(o[0] * a + b[0] * (1 - a)),
      Math.round(o[1] * a + b[1] * (1 - a)),
      Math.round(o[2] * a + b[2] * (1 - a))
    ];
    return 'rgb(' + mix[0] + ', ' + mix[1] + ', ' + mix[2] + ')';
  }

  function paletteBg() {
    var v = getComputedStyle(document.documentElement)
      .getPropertyValue('--shd-bg');
    return (v || '').trim() || '#1a1a2e';
  }

  function activeSeverity() {
    if (state.severity !== 'ok' && Date.now() > state.overrideUntil) {
      return 'ok';                                /* override expired */
    }
    return state.severity;
  }

  /* The single writer. One custom property, only when the value changes. */
  function apply(force) {
    var sev = activeSeverity();
    var period = periodForHour(new Date().getHours());
    var tint = SEVERITY_TINTS[sev] || PERIOD_TINTS[period] || '';

    /* A severity tint wins while it is active; otherwise time of day rules. */
    if (!tint) { tint = PERIOD_TINTS[period] || ''; }

    var effective = tint ? composite(paletteBg(), tint) : paletteBg();
    var root = document.documentElement;
    if (force || root.style.getPropertyValue('--shd-bg-effective') !== effective) {
      root.style.setProperty('--shd-bg-effective', effective);
    }
    state.period = period;
    return { period: period, severity: sev, effective: effective };
  }

  function tick() { apply(false); }

  function start() {
    apply(true);
    if (state.timer) { clearInterval(state.timer); }  /* idempotent re-init */
    state.timer = setInterval(tick, TICK_MS);
  }

  /* PUBLIC API ------------------------------------------------------------ */
  global.SHDBackground = {
    /* Called by every tab's alert banner with its computed severity. */
    setSeverity: function (sev) {
      var s = String(sev || 'ok');
      if (!SEVERITY_TINTS.hasOwnProperty(s)) { s = 'ok'; }
      state.severity = s;
      state.overrideUntil = Date.now() + OVERRIDE_MS;
      return apply(false);
    },
    /* Force a recompute (tests, theme switches, manual refresh). */
    refreshNow: function () { return apply(true); },
    getState: function () {
      return { period: state.period, severity: activeSeverity(),
               effective: getComputedStyle(document.documentElement)
                 .getPropertyValue('--shd-bg-effective').trim() };
    },
    periods: Object.keys(PERIOD_TINTS),
    init: start
  };

  start();
})(window);
