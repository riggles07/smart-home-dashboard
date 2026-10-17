// Theme Manager runtime harness (task t_2fd8fb10).
//
// Drives the REAL js/themes.js -- the same bytes the dashboard inlines into
// <head> -- inside a stub DOM, so the acceptance criteria (apply/init/list/
// current behaviour, localStorage persistence, no layout tokens touched)
// are exercised rather than grepped. Used by tests/test_theme_manager.py.
//
// Run:  node tools/_theme_manager_driver.js '<json-args>'
//   args: {"op":"apply"|"init"|"current"|"list"|"apply-then-init",
//          "id":"nord", "storage":{"shd_theme":"nord"}}
// Prints one JSON object: {applied, props, removed, storage, current, list}
const fs = require('fs');
const path = require('path');

const src = fs.readFileSync(
  path.join(__dirname, '..', 'js', 'themes.js'), 'utf8');
const args = JSON.parse(process.argv[2] || '{}');

class FakeStyle {
  constructor() { this.props = {}; this.removed = []; }
  setProperty(n, v) { this.props[n] = v; }
  removeProperty(n) { this.removed.push(n); delete this.props[n]; }
}
const root = { style: new FakeStyle() };
const doc = { documentElement: root };

class FakeLS {
  constructor(seed) { this.store = seed || {}; }
  getItem(k) {
    return Object.prototype.hasOwnProperty.call(this.store, k) ? this.store[k] : null;
  }
  setItem(k, v) { this.store[k] = String(v); }
  removeItem(k) { delete this.store[k]; }
}
const ls = new FakeLS(args.storage || {});

const win = { document: doc, localStorage: ls };
// themes.js closes with })(typeof window !== 'undefined' ? window : globalThis);
// so a local `window` binding routes the IIFE at our stub, and the manager is
// exported as window.SHDThemeManager (the IIFE assigns onto its `global` arg).
const run = new Function('window', 'globalThis', 'self', src + '\n;return window.SHDThemeManager;');
const mgr = run(win, win, win);
if (!mgr) { console.error('themes.js did not export SHDThemeManager'); process.exit(2); }

const out = { props: root.style.props, removed: root.style.removed, storage: ls.store };
switch (args.op) {
  case 'apply': out.applied = mgr.apply(args.id); break;
  case 'init': out.applied = mgr.init(); break;
  case 'current': out.current = mgr.current(); break;
  case 'list': out.list = mgr.list().map(p => p.id); break;
  case 'apply-then-init':
    out.first = mgr.apply(args.id);
    out.second = mgr.init();
    break;
  default:
    console.error('unknown op: ' + args.op);
    process.exit(2);
}
console.log(JSON.stringify(out));