"use strict";
// The page is a client of the local API only; it keeps no state beyond what it last fetched (§13.9).
const $ = (id) => document.getElementById(id);
let state = null;

function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return el;
}

async function api(method, path, body) {
  const init = { method, headers: {} };
  if (method !== "GET") { init.headers["X-Baton-UI"] = "1"; init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body || {}); }
  const res = await fetch(path, init);
  const out = await res.json().catch(() => ({ ok: false, message: "Unreadable answer." }));
  if (!res.ok) throw new Error(out.message || "Refused.");
  return out;
}

function notice(text, bad) {
  const n = $("notice");
  n.textContent = text || ""; n.hidden = !text; n.className = bad ? "bad" : "";
}

async function load() {
  try { state = await api("GET", "/api/state"); notice(""); }
  catch (e) { notice(e.message, true); return; }
  render();
}

function price(m) {
  if (m.subscription) return "subscription";
  if (!m.price) return "unknown";
  if (m.price.free) return "free";
  return "$" + m.price.input + " in / $" + m.price.output + " out per million";
}

function renderHarnesses() {
  const list = $("harness-list"); list.replaceChildren();
  for (const d of state.detected) {
    const ready = d.usable;
    list.append(h("div", { class: "card" }, h("div", { class: "row" },
      h("span", { class: "name" }, d.provider), h("span", { class: ready ? "ok" : "warn" }, ready ? "connected" : (d.problem || "not ready")),
      h("span", { class: "muted" }, d.version ? "version " + d.version : ""))));
  }
  if (!state.detected.length) list.append(h("p", { class: "muted" }, "No supported command-line tools were found."));
}

function renderProviders() {
  const list = $("provider-list"); list.replaceChildren();
  for (const [name, r] of Object.entries(state.declared)) {
    const p = (state.providers || {})[name];
    list.append(h("div", { class: "card" }, h("div", { class: "row" }, h("span", { class: "name" }, name),
      h("span", { class: "muted" }, r.provider + (p ? " · " + p.profiles + " models" + (p.free ? ", " + p.free + " free" : "") : "")),
      h("span", { class: "muted" }, p && p.quota_line ? p.quota_line : ""))));
  }
  const known = Object.entries(state.directory).filter(([n]) => !Object.values(state.declared).some((r) => r.provider === n));
  if (known.length) list.append(h("p", { class: "muted" }, "Available to add: " + known.map(([, p]) => p.display_name).join(", ")));
}

function renderModels() {
  const box = $("model-table"); box.replaceChildren();
  const rows = state.models.map((m) => h("tr", {},
    h("td", {}, h("span", { class: "name" }, m.model_id || m.profile), h("div", { class: "muted" }, m.profile)),
    h("td", {}, m.provider || ""), h("td", {}, price(m)), h("td", {}, m.context_tokens ? m.context_tokens.toLocaleString() : ""),
    h("td", {}, m.tier || ""), h("td", {}, Object.entries(m.capabilities).map(([c, s]) => c + " (" + s + ")").join(", ")),
    h("td", {}, m.verified ? m.verified.date : "not yet")));
  box.append(h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {},
    ...["Model", "Provider", "Price", "Context", "Tier", "Capabilities", "Checked"].map((t) => h("th", {}, t)))), h("tbody", {}, rows))));
  if (!rows.length) box.append(h("p", { class: "muted" }, "No models yet."));
}

function render() { renderHarnesses(); renderProviders(); renderModels(); }

$("quit").addEventListener("click", async () => {
  try { await api("POST", "/api/quit"); } catch (e) { /* the page is closing either way */ }
  document.body.replaceChildren(h("p", { class: "muted" }, "Closed. You can close this tab."));
});
document.addEventListener("visibilitychange", () => { if (!document.hidden && state) load(); });
load();
