#!/usr/bin/env node
/* Behaviour harness for js/background.js.
 *
 * The engine is an IIFE that expects a browser. Load it into a stub global so
 * the PURE logic (period mapping, colour compositing, severity override) can be
 * asserted without a browser or jsdom. Node's setInterval would keep the
 * process alive forever, so it is stubbed to a no-op that records the cadence.
 *
 * Run: node tests/background_engine_harness.js   (exit 0 = pass) */
'use strict';
const fs = require('fs');
const path = require('path');

const SRC = fs.readFileSync(path.join(__dirname, '..', 'js', 'background.js'), 'utf8');

let failures = 0;
const ok = (cond, msg) => { if (!cond) { console.log('FAIL: ' + msg); failures++; } };

function makeEnv(paletteHex) {
  const written = {};
  const intervals = [];
  const root = {
    style: {
      _v: {},
      getPropertyValue(k) { return this._v[k] || ''; },
      setProperty(k, v) { this._v[k] = v; written[k] = (written[k] || []).concat([v]); }
    }
  };
  return {
    written, intervals,
    document: { documentElement: root },
    /* Computed style must REFLECT what the engine wrote on root.style --
       otherwise getState() reads an empty string and the assertions become
       vacuous NaN comparisons (this stub bug produced 4 false failures). */
    getComputedStyle: () => ({
      getPropertyValue: (k) => (root.style._v[k] !== undefined
        ? root.style._v[k]
        : (k === '--shd-bg' ? paletteHex : ''))
    }),
    setInterval: (fn, ms) => { intervals.push(ms); return intervals.length; },
    clearInterval: () => {},
    Date, Math, String, Object, Array, parseInt, parseFloat, isNaN, console
  };
}

function load(env, atHour) {
  // freeze the clock so the period is deterministic
  const RealDate = Date;
  function FrozenDate(...a) { return a.length ? new RealDate(...a) : new RealDate(2026, 9, 19, atHour, 0, 0); }
  FrozenDate.now = () => new RealDate(2026, 9, 19, atHour, 0, 0).getTime();
  env.Date = FrozenDate;
  env.window = env;
  const fn = new Function(...Object.keys(env), SRC);
  fn(...Object.values(env));
  return env.window.SHDBackground;
}

/* ---- 1. period mapping ---------------------------------------------------- */
const expectPeriod = { 23: 'night', 3: 'night', 7: 'dawn', 12: 'day', 18: 'dusk', 21: 'dusk' };
for (const [h, want] of Object.entries(expectPeriod)) {
  const env = makeEnv('#1a1a2e');
  const api = load(env, Number(h));
  const st = api.getState();
  ok(st.period === want, `hour ${h} -> period ${st.period}, expected ${want}`);
}

/* ---- 2. daytime hands the palette colour back untouched ------------------- */
{
  const env = makeEnv('#1a1a2e');
  const api = load(env, 12);
  const st = api.getState();
  ok(st.effective === '#1a1a2e' || st.effective === 'rgb(26, 26, 46)',
     `daytime should preserve palette colour, got ${st.effective}`);
}

/* ---- 3. night is measurably darker than the palette ---------------------- */
function rgbOf(str) {
  const m = String(str).match(/rgba?\(([^)]+)\)/);
  if (m) { return m[1].split(',').map(Number); }
  const h = String(str).replace('#', '');
  return [0, 2, 4].map(i => parseInt(h.slice(i, i + 2), 16));
}
{
  const env = makeEnv('#1a1a2e');
  const api = load(env, 23);
  const night = rgbOf(api.getState().effective);
  const base = [26, 26, 46];
  ok(night[0] < base[0] && night[1] < base[1] && night[2] < base[2],
     `night tint must darken the palette (got ${night} vs ${base})`);
}

/* ---- 4. state trigger: critical reddens, ok falls back to time of day ---- */
{
  const env = makeEnv('#1a1a2e');
  const api = load(env, 12);              // daytime, no tint
  const before = rgbOf(api.getState().effective);
  api.setSeverity('critical');
  const crit = rgbOf(api.getState().effective);
  ok(crit[0] > before[0] && crit[1] <= before[1],
     `critical must push the background red (got ${crit} vs ${before})`);
  api.setSeverity('ok');
  const after = rgbOf(api.getState().effective);
  ok(Math.abs(after[0] - before[0]) <= 2 && Math.abs(after[2] - before[2]) <= 2,
     `severity ok must release the tint (got ${after} vs ${before})`);
}

/* ---- 5. cadence + single writer ----------------------------------------- */
{
  const env = makeEnv('#1a1a2e');
  const api = load(env, 12);
  ok(env.intervals.length === 1 && env.intervals[0] === 30000,
     `expected one 30s timer, got ${JSON.stringify(env.intervals)}`);
  const keys = Object.keys(env.written);
  ok(keys.length > 0 && keys.every(k => k === '--shd-bg-effective'),
     `engine must write ONLY --shd-bg-effective (never the palette token), wrote ${keys}`);
  ok(api.periods.length >= 2, `expected >=2 background states, got ${api.periods.length}`);
}

/* ---- 6. re-init is idempotent (dashboard re-appends head templates) ------ */
{
  const env = makeEnv('#1a1a2e');
  const api = load(env, 12);
  api.init(); api.init();
  ok(env.intervals.length === 3, 'init() should reset the timer, not stack extras');
}

console.log(failures ? `${failures} background-engine assertion(s) failed` : 'background engine behaviour OK');
process.exit(failures ? 1 : 0);
