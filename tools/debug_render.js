// Debug script for Render board function
const fs = require('fs');
const path = require('path');
// Resolve relative to this file -- a hardcoded dev path passes on the author's
// machine and fails everywhere else.
const flowPath = process.argv[2] ||
  path.join(__dirname, '..', 'flows', 'all-flows.flow.json');
const nodes = JSON.parse(fs.readFileSync(flowPath, 'utf8'));
const byName = {};
for (const n of nodes) if (n.type === 'function') byName[n.name] = n.func;

const code = byName['Render board'];
console.log('Render board code:', code);

const makeEnv = (vars) => ({ get: (k) => (k in vars ? vars[k] : undefined), set: () => {} });
const makeNode = (statusCalls) => ({ status: (s) => { console.log('  status called:', s); statusCalls.push(s); } });
const flowStore = () => {
  const s = {};
  return { get: (k) => s[k], set: (k, v) => { console.log('  store.set:', k, '=', v); s[k] = v; } };
};

const store = flowStore();
store.set('kanban_cards', [
  { task: 'Buy milk', status: 'todo' },
  { task: 'Walk dog', status: 'doing' },
  { task: 'Review PR', status: 'todo' }
]);

console.log('Store before:', store.get('kanban_cards'));

const fn = new Function('msg', 'env', 'node', 'flow', 'context', 'global', code);
const st = [];

const flow = {
  get: (k) => store.get(k),
  set: (k, v) => store.set(k, v)
};

console.log('Invoking function...');
const result = fn({ topic: 'kanban/refresh' }, makeEnv({}), makeNode(st), flow, {}, {});
console.log('Result:', result);
console.log('Result type:', typeof result);
console.log('Is array:', Array.isArray(result));
if (Array.isArray(result)) {
  console.log('Array length:', result.length);
  console.log('result[0]:', result[0]);
  console.log('result[1]:', result[1]);
}
