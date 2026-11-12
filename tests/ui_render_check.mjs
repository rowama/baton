// Runs ui/render.js against a tiny DOM stand-in and prints the result as JSON (tests/test_ui_render.py).
import fs from "node:fs";
class N { constructor(tag) { this.tag = tag; this.attrs = {}; this.kids = []; }
  setAttribute(k, v) { this.attrs[k] = v; } addEventListener() {} append(...k) { this.kids.push(...k); }
  get textContent() { return this.kids.map((k) => (typeof k === "string" ? k : k.textContent)).join(""); } }
class Frag extends N { constructor() { super("#frag"); } }
globalThis.Node = N;
globalThis.window = {};
globalThis.document = { createElement: (t) => new N(t), createTextNode: (t) => String(t), createDocumentFragment: () => new Frag() };
new Function(fs.readFileSync(process.argv[2], "utf8"))();
const dump = (n) => (typeof n === "string" ? n : { t: n.tag, a: n.attrs, k: n.kids.map(dump) });
const md = fs.readFileSync(0, "utf8");
console.log(JSON.stringify(dump(window.BatonRender.render(md))));
