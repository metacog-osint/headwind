// Runs site_src/app.js against a snapshot (argv[2]) with a stub DOM and prints the #anomalies rows, #reading and tiles.
const fs = require("fs"), vm = require("vm");
const snap = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const els = {};
function el(id) {
  if (!els[id]) {
    els[id] = new Proxy({ innerHTML: "", textContent: "", id, style: {}, dataset: {}, classList: { add() {}, remove() {}, toggle() {} },
      hasAttribute() { return true; }, setAttribute() {}, getAttribute() { return null; }, addEventListener() {},
      querySelector() { return null; }, querySelectorAll() { return []; }, closest() { return null; },
      appendChild() {}, insertAdjacentHTML() {} }, { get(t, k) { return k in t ? t[k] : (() => null); }, set(t, k, v) { t[k] = v; return true; } });
  }
  return els[id];
}
const doc = { getElementById: el, querySelector: () => null, querySelectorAll: () => [], addEventListener() {},
  createElement: () => el("_x"), body: el("_b"), documentElement: el("_d"), title: "" };
const win = { TicTime: null, TicRelated: null, document: doc, addEventListener() {}, location: { hash: "", search: "" } };
const ctx = { window: win, document: doc, console, Intl, Date, Math, Number, String, Array, Object, JSON, RegExp, Promise,
  setTimeout, clearTimeout, URLSearchParams, fetch: () => Promise.resolve({ ok: true, json: () => Promise.resolve(snap) }) };
win.window = win;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[2], "utf8"), ctx);
setTimeout(() => {
  console.log(JSON.stringify({ anomalies: els.anomalies && els.anomalies.innerHTML, reading: els.reading && els.reading.innerHTML,
    tiles: els.tiles && els.tiles.innerHTML, fx: els["fx-table"] && els["fx-table"].innerHTML }));
}, 200);
