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

function busy(btn, on) { btn.disabled = on; }

async function act(btn, fn, done) {
  busy(btn, true);
  try { const out = await fn(); notice(done(out)); await load(); }
  catch (e) { notice(e.message, true); }
  finally { busy(btn, false); }
}

function keptIn(name) {
  const where = ((state.accounts || {})[name] || {}).kept_in || [];
  return where.length ? "key kept in: " + where.join(", ") : "no stored key";
}

function connectForm(provider, info) {
  const key = h("input", { type: "password", autocomplete: "off", placeholder: info.kind === "openai_compatible" ? "API key (blank if none)" : "API key", "aria-label": "API key for " + info.display_name });
  const url = info.kind === "openai_compatible" && !info.base_url ? h("input", { type: "url", placeholder: "https://…/v1", "aria-label": "Address" }) : null;
  const go = h("button", {}, "Connect");
  go.addEventListener("click", () => act(go,
    () => { const body = { provider, key: key.value }; if (url) body.base_url = url.value; const p = api("POST", "/api/accounts", body); key.value = ""; return p; },
    (o) => "Connected " + o.account + (o.stored_in ? "; its key is kept in the " + o.stored_in : "") + ". " + o.setup.written.length + " models added."));
  return h("div", { class: "row" }, key, url, go, info.signup_url ? h("a", { href: info.signup_url, target: "_blank", rel: "noopener noreferrer" }, "Get a key") : "");
}

function accountCard(name, r) {
  const p = (state.providers || {})[name];
  const key = h("input", { type: "password", autocomplete: "off", placeholder: "New key", "aria-label": "New key for " + name });
  const replace = h("button", { class: "quiet" }, "Replace key");
  replace.addEventListener("click", () => act(replace,
    () => { const q = api("POST", "/api/accounts/" + encodeURIComponent(name) + "/key", { key: key.value }); key.value = ""; return q; },
    () => "The new key works and replaced the old one."));
  const forget = h("input", { type: "checkbox", id: "forget-" + name });
  const off = h("button", { class: "quiet" }, "Disconnect");
  off.addEventListener("click", () => act(off,
    () => api("DELETE", "/api/accounts/" + encodeURIComponent(name), { forget_key: forget.checked }),
    () => "Disconnected " + name + ". Its models stay listed but are no longer used."));
  return h("div", { class: "card" },
    h("div", { class: "row" }, h("span", { class: "name" }, name),
      h("span", { class: "muted" }, r.provider + (p ? " · " + p.profiles + " models" + (p.free ? ", " + p.free + " free" : "") : "")),
      h("span", { class: "muted" }, keptIn(name)), h("span", { class: "muted" }, p && p.quota_line ? p.quota_line : "")),
    h("div", { class: "row" }, key, replace, h("span", {}, forget, h("label", { for: "forget-" + name }, " also delete the stored key")), off));
}

function renderProviders() {
  const list = $("provider-list"); list.replaceChildren();
  for (const [name, r] of Object.entries(state.declared)) list.append(accountCard(name, r));
  const connected = new Set(Object.values(state.declared).map((r) => r.provider));
  for (const [prov, info] of Object.entries(state.directory)) {
    if (connected.has(prov)) continue;
    list.append(h("div", { class: "card" }, h("div", { class: "name" }, info.display_name), connectForm(prov, info)));
  }
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
