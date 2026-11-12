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
  for (const kid of kids.flat()) { if (kid == null || kid === false) continue; el.append(kid instanceof Node ? kid : document.createTextNode(String(kid))); }
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

function copy(text, btn) {
  const done = () => { btn.textContent = "Copied"; setTimeout(() => { btn.textContent = "Copy"; }, 1500); };
  if (navigator.clipboard) navigator.clipboard.writeText(text).then(done, () => notice("Select the command and copy it by hand.", true));
  else notice("Select the command and copy it by hand.", true);
}

function stepBox(step) {
  if (!step || step.kind === "ready") return "";
  const btn = h("button", { class: "quiet" }, "Copy");
  btn.addEventListener("click", () => copy(step.command, btn));
  return h("div", {}, h("div", { class: "muted" }, step.text), h("div", { class: "row" }, h("code", {}, step.command), btn),
    step.docs ? h("a", { href: step.docs, target: "_blank", rel: "noopener noreferrer" }, "More about installing") : "");
}

function renderHarnesses() {
  const list = $("harness-list"); list.replaceChildren();
  for (const d of state.detected) {
    const ready = d.usable;
    const again = h("button", { class: "quiet" }, "Check again");
    again.addEventListener("click", () => act(again, () => load(), () => ""));
    list.append(h("div", { class: "card" }, h("div", { class: "row" },
      h("span", { class: "name" }, d.provider), h("span", { class: ready ? "ok" : "warn" }, ready ? "connected" : (d.problem || "not ready")),
      h("span", { class: "muted" }, d.version ? "version " + d.version : ""), ready ? "" : again), stepBox(d.step)));
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

const filter = { free: false, maxPrice: "", capability: "", tier: "", provider: "", off: false };

function cost(m) { return m.subscription || !m.price ? null : (m.price.free ? 0 : Number(m.price.input || 0) + Number(m.price.output || 0)); }

function passes(m) {
  if (filter.free && !(m.price && m.price.free)) return false;
  if (filter.maxPrice !== "") { const c = cost(m); if (c === null || c > Number(filter.maxPrice)) return false; }
  if (filter.capability && !(filter.capability in m.capabilities)) return false;
  if (filter.tier && m.tier !== filter.tier) return false;
  if (filter.provider && m.provider !== filter.provider) return false;
  if (filter.off && m.enabled) return false;
  return true;
}

function select(label, key, options) {
  const sel = h("select", { "aria-label": label }, h("option", { value: "" }, label), options.map((o) => h("option", { value: o }, o)));
  sel.value = filter[key];
  sel.addEventListener("change", () => { filter[key] = sel.value; renderModels(); });
  return sel;
}

function renderFilters() {
  const f = $("filters"); f.replaceChildren();
  const uniq = (get) => [...new Set(state.models.flatMap(get).filter(Boolean))].sort();
  const free = h("input", { type: "checkbox", id: "f-free" }); free.checked = filter.free;
  free.addEventListener("change", () => { filter.free = free.checked; renderModels(); });
  const max = h("input", { type: "number", min: "0", step: "any", placeholder: "Max $ per million", "aria-label": "Maximum price", value: filter.maxPrice });
  max.addEventListener("input", () => { filter.maxPrice = max.value; renderModels(); });
  const off = h("input", { type: "checkbox", id: "f-off" }); off.checked = filter.off;
  off.addEventListener("change", () => { filter.off = off.checked; renderModels(); });
  const cheap = h("input", { type: "checkbox", id: "p-cheap" }); cheap.checked = state.preferences.cheapest_first;
  cheap.addEventListener("change", () => act(cheap, () => api("PUT", "/api/preferences", { cheapest_first: cheap.checked }),
    () => cheap.checked ? "Baton will pick the cheapest capable model first." : "Baton will pick the most proven model first."));
  f.append(h("span", {}, free, h("label", { for: "f-free" }, " free only")), max,
    select("Any capability", "capability", uniq((m) => Object.keys(m.capabilities))), select("Any tier", "tier", uniq((m) => [m.tier])),
    select("Any provider", "provider", uniq((m) => [m.provider])), h("span", {}, off, h("label", { for: "f-off" }, " turned off")),
    h("span", {}, cheap, h("label", { for: "p-cheap" }, " cheapest first (otherwise most proven first)")));
}

function preferBox() {
  const caps = [...new Set(state.models.flatMap((m) => Object.keys(m.capabilities)))].sort();
  const cap = h("select", { "aria-label": "Capability" }, h("option", { value: "" }, "Prefer a model for…"), caps.map((c) => h("option", { value: c }, c)));
  const model = h("select", { "aria-label": "Preferred model" }, h("option", { value: "" }, "(no preference)"),
    state.models.map((m) => h("option", { value: m.profile }, m.model_id || m.profile)));
  const set = h("button", { class: "quiet" }, "Save");
  cap.addEventListener("change", () => { model.value = (state.preferences.prefer_by_capability[cap.value] || [""])[0]; });
  set.addEventListener("click", () => cap.value && act(set,
    () => api("PUT", "/api/preferences", { prefer_by_capability: { [cap.value]: model.value ? [model.value] : [] } }),
    () => model.value ? "Baton will try " + model.value + " first for " + cap.value + "." : "Cleared the preference for " + cap.value + "."));
  const now = Object.entries(state.preferences.prefer_by_capability).map(([c, n]) => c + ": " + n.join(", ")).join(" · ");
  return h("div", { class: "row" }, cap, model, set, h("span", { class: "muted" }, now));
}

function modelRow(m) {
  const on = h("input", { type: "checkbox", "aria-label": "Use " + (m.model_id || m.profile) }); on.checked = m.enabled;
  on.addEventListener("change", () => act(on, () => api("POST", "/api/models/" + encodeURIComponent(m.profile) + "/enabled", { enabled: on.checked }),
    () => (on.checked ? "Turned on: " : "Turned off: ") + (m.model_id || m.profile)));
  const check = h("button", { class: "quiet" }, "Check it works");
  check.addEventListener("click", () => act(check, () => api("POST", "/api/models/" + encodeURIComponent(m.profile) + "/verify"),
    (o) => o.verified.length ? (m.model_id || m.profile) + " works." : (o.failed[0] ? o.failed[0].reason : "Nothing was checked.")));
  return h("tr", {},
    h("td", {}, on), h("td", {}, h("span", { class: "name" }, m.model_id || m.profile), h("div", { class: "muted" }, m.profile + (m.flag ? " · " + m.flag : ""))),
    h("td", {}, m.provider || ""), h("td", {}, price(m)), h("td", {}, m.context_tokens ? m.context_tokens.toLocaleString() : ""),
    h("td", {}, m.tier || ""), h("td", {}, Object.entries(m.capabilities).map(([c, st]) => c + " (" + st + ")").join(", ")),
    h("td", {}, m.verified ? m.verified.date : "not yet", h("div", {}, check)));
}

function renderModels() {
  const box = $("model-table"); box.replaceChildren();
  const shown = state.models.filter(passes);
  box.append(preferBox());
  box.append(h("div", { class: "scroll" }, h("table", {}, h("thead", {}, h("tr", {},
    ...["Use", "Model", "Provider", "Price", "Context", "Tier", "Capabilities", "Checked"].map((t) => h("th", {}, t)))), h("tbody", {}, shown.map(modelRow)))));
  box.append(h("p", { class: "muted" }, shown.length + " of " + state.models.length + " models shown."));
}

function render() { renderHarnesses(); renderProviders(); renderFilters(); renderModels(); }

$("quit").addEventListener("click", async () => {
  try { await api("POST", "/api/quit"); } catch (e) { /* the page is closing either way */ }
  document.body.replaceChildren(h("p", { class: "muted" }, "Closed. You can close this tab."));
});
document.addEventListener("visibilitychange", () => { if (!document.hidden && state) load(); });
if (!window.BatonManual.inManual()) load();
