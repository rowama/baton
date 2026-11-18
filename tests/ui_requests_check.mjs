// Runs the pure parts of ui/requests.js (no DOM, no fetch) and prints each call's result as JSON (tests/test_ui_requests_js.py).
import fs from "node:fs";
globalThis.window = {};
new Function(fs.readFileSync(process.argv[2], "utf8"))();
const calls = JSON.parse(fs.readFileSync(0, "utf8"));
const R = window.BatonRequests;
const strip = (x) => JSON.parse(JSON.stringify(x, (k, v) => (v instanceof Set ? [...v].sort() : v)));
console.log(JSON.stringify(calls.map(([fn, ...args]) => strip(R[fn](...args)))));
