"use strict";
// Interaction requests on the local page (§13.9; Decisions 0169, 0170, 0171): one generic renderer of
// baton-interaction/1's answer subset, written once. It builds DOM nodes, never HTML strings, keeps nothing but the
// request it last fetched, and records only through POST .../answer, after the owner confirms.
(function () {
  // ---- pure parts (tests/test_ui_requests_js.py runs them under node) ------------------------------------------

  const isEmpty = (v) => v === undefined || v === null || v === "" || (Array.isArray(v) && v.length === 0)
    || (typeof v === "object" && !Array.isArray(v) && Object.keys(v).length === 0);
  const humanize = (name) => { const s = String(name).replace(/[_-]+/g, " ").trim(); return s.charAt(0).toUpperCase() + s.slice(1); };

  /** A field's choices as [{value, label}], from enum or labelled oneOf consts; null when it has none. */
  function choicesOf(schema) {
    if (!schema) return null;
    if (Array.isArray(schema.oneOf)) return schema.oneOf.map((o) => ({ value: o.const, label: o.title != null ? String(o.title) : String(o.const) }));
    if (Array.isArray(schema.enum)) return schema.enum.map((v) => ({ value: v, label: String(v) }));
    return null;
  }

  /** What control a field is: group, table, multi, list, boolean, number, choice, date, time, datetime, textarea, text. */
  function kindOf(schema, hint) {
    const t = schema && schema.type, w = hint && hint.widget;
    if (t === "object") return "group";
    if (t === "array") {
      const it = schema.items || {};
      if (it.type === "object") return "table";
      return choicesOf(it) ? "multi" : "list";
    }
    if (t === "boolean") return "boolean";
    if (t === "number" || t === "integer") return choicesOf(schema) ? "choice" : "number";
    if (choicesOf(schema)) return "choice";
    if (schema.format === "date") return "date";
    if (schema.format === "time") return "time";
    if (schema.format === "date-time") return "datetime";
    if (w === "textarea" || (schema.maxLength || 0) > 200) return "textarea";
    return "text";
  }

  /** An object's fields in the hints' order (named ones first, the rest as the schema lists them), with labels and help. */
  function fieldsOf(schema, hints, prefix) {
    hints = hints || {}; prefix = prefix || "";
    const props = (schema && schema.properties) || {};
    const required = new Set((schema && schema.required) || []);
    const names = Object.keys(props);
    const ordered = [];
    for (const full of hints.order || []) {
      if (!full.startsWith(prefix)) continue;
      const rest = full.slice(prefix.length);
      if (!rest.includes(".") && names.includes(rest) && !ordered.includes(rest)) ordered.push(rest);
    }
    for (const n of names) if (!ordered.includes(n)) ordered.push(n);
    return ordered.map((name) => {
      const path = prefix + name, s = props[name], fh = (hints.fields || {})[path] || {};
      return { name, path, schema: s, required: required.has(name), hint: fh, kind: kindOf(s, fh),
               label: fh.label || s.title || humanize(name), help: fh.help || s.description || "" };
    });
  }

  /** Top-level fields arranged as the hints group them: [{title|null, fields}], each group where its first field falls. */
  function layout(fields, hints) {
    const groups = ((hints || {}).groups || []).map((g) => ({ title: g.title, names: g.fields.filter((n) => !n.includes(".")) }));
    const out = [], placed = new Set();
    for (const f of fields) {
      if (placed.has(f.name)) continue;
      const g = groups.find((x) => x.names.includes(f.name));
      if (g) {
        const members = fields.filter((x) => g.names.includes(x.name) && !placed.has(x.name));
        members.forEach((x) => placed.add(x.name));
        out.push({ title: g.title, fields: members });
      } else {
        placed.add(f.name);
        if (out.length && out[out.length - 1].title === null) out[out.length - 1].fields.push(f);
        else out.push({ title: null, fields: [f] });
      }
    }
    return out;
  }

  /** Values without the empty ones: an empty field is a field not given (as in the answer file). */
  function clean(v) {
    if (Array.isArray(v)) return v.map(clean);
    if (v && typeof v === "object") {
      const o = {};
      for (const [k, x] of Object.entries(v)) { const c = clean(x); if (!isEmpty(c)) o[k] = c; }
      return o;
    }
    return v;
  }

  /** Where the values break the schema, as [{path, message}] in plain words; the runtime checks again on answer. */
  function validate(schema, value, path, required, label, hints) {
    const out = [], where = label || path || "The answer", put = (m) => out.push({ path: path || "", message: where + " " + m });
    const top = path === "" && schema.type === "object" && value && typeof value === "object";  // the form itself: check its fields
    if (isEmpty(value) && !top) { if (required) put("is needed."); return out; }
    const t = schema.type;
    if (t === "object") {
      const prefix = path ? path.replace(/\[\d+\]/g, "") + "." : "";
      const row = /\[(\d+)\]$/.exec(path || "");  // a table's row: its cells say which row
      for (const f of fieldsOf(schema, hints, prefix)) {
        out.push(...validate(f.schema, value[f.name], (path ? path + "." : "") + f.name, f.required, f.label + (row ? " in row " + (Number(row[1]) + 1) : ""), hints));
      }
      return out;
    }
    if (t === "array") {
      if (!Array.isArray(value)) { put("must be a list."); return out; }
      if (schema.minItems != null && value.length < schema.minItems) put("needs at least " + schema.minItems + ".");
      if (schema.maxItems != null && value.length > schema.maxItems) put("takes at most " + schema.maxItems + ".");
      if (schema.uniqueItems && new Set(value.map((x) => JSON.stringify(x))).size !== value.length) put("has the same entry twice.");
      value.forEach((x, i) => out.push(...validate(schema.items || {}, x, path + "[" + i + "]", true, where + " (" + (i + 1) + ")", hints)));
      return out;
    }
    const ch = choicesOf(schema);
    if (ch && !ch.some((c) => c.value === value)) { put("must be one of the choices."); return out; }
    if (t === "string") {
      if (typeof value !== "string") { put("must be text."); return out; }
      if (schema.minLength != null && value.length < schema.minLength) put("is too short.");
      if (schema.maxLength != null && value.length > schema.maxLength) put("is too long (at most " + schema.maxLength + " characters).");
      if (schema.pattern) { try { if (!new RegExp(schema.pattern, "u").test(value)) put("is not in the expected form."); } catch (e) { /* the runtime checks it */ } }
      if (schema.format === "date" && !/^\d{4}-\d{2}-\d{2}$/.test(value)) put("must be a date.");
      if (schema.format === "email" && !/^[^@\s]+@[^@\s]+$/.test(value)) put("must be an email address.");
    } else if (t === "number" || t === "integer") {
      if (typeof value !== "number" || !Number.isFinite(value)) { put("must be a number."); return out; }
      if (t === "integer" && !Number.isInteger(value)) put("must be a whole number.");
      if (schema.minimum != null && value < schema.minimum) put("must be at least " + schema.minimum + ".");
      if (schema.maximum != null && value > schema.maximum) put("must be at most " + schema.maximum + ".");
      if (schema.exclusiveMinimum != null && value <= schema.exclusiveMinimum) put("must be more than " + schema.exclusiveMinimum + ".");
      if (schema.exclusiveMaximum != null && value >= schema.exclusiveMaximum) put("must be less than " + schema.exclusiveMaximum + ".");
    } else if (t === "boolean" && typeof value !== "boolean") put("must be yes or no.");
    return out;
  }

  /** A value as the owner reads it: a choice's label, a list joined, yes or no. */
  function display(schema, v) {
    if (isEmpty(v)) return "—";
    if (schema.type === "boolean") return v ? "Yes" : "No";
    if (schema.type === "array" && (schema.items || {}).type !== "object") return v.map((x) => display(schema.items || {}, x)).join(", ");
    const ch = choicesOf(schema);
    if (ch) { const c = ch.find((x) => x.value === v); return c ? c.label : String(v); }
    return String(v);
  }

  /** The confirmation's rows: the summary hint's fields, or every top-level field: [{label, schema, value}]. */
  function summaryRows(schema, hints, values) {
    const fields = fieldsOf(schema, hints, "");
    const named = (hints || {}).summary;
    const shown = named && named.length ? named.filter((n) => !n.includes(".")).map((n) => fields.find((f) => f.name === n)).filter(Boolean) : fields;
    return shown.map((f) => ({ label: f.label, schema: f.schema, value: (values || {})[f.name], hint: f.hint }));
  }

  /** A table's rows are fixed when the prefill gives them; the cells it gives name the row and are not edited. */
  function tableRows(schema, prefill) {
    const given = Array.isArray(prefill) ? prefill : [];
    return { fixed: given.length > 0, rows: given.map((r) => ({ ...(r || {}) })), givenKeys: given.map((r) => new Set(Object.keys(r || {}))) };
  }

  const pure = { choicesOf, kindOf, fieldsOf, layout, clean, validate, display, summaryRows, tableRows };

  // ---- the page ---------------------------------------------------------------------------------------------------

  if (typeof location === "undefined") { window.BatonRequests = { ...pure }; return; }

  const $ = (id) => document.getElementById(id);
  const m = /^\/p\/([^/]+)\/requests(?:\/([^/]+))?\/?$/.exec(location.pathname);
  const inRequests = () => m !== null;
  window.BatonRequests = { ...pure, inRequests };

  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (v !== false && v != null) el.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat(Infinity)) { if (kid == null || kid === false) continue; el.append(kid instanceof Node ? kid : document.createTextNode(String(kid))); }
    return el;
  }
  let uid = 0;
  const nextId = () => "f" + (++uid);

  async function call(method, path, body) {
    const init = { method, headers: {} };
    if (method !== "GET") { init.headers["X-Baton-UI"] = "1"; init.headers["Content-Type"] = "application/json"; init.body = JSON.stringify(body || {}); }
    const res = await fetch(path, init);
    const out = await res.json().catch(() => ({ ok: false, message: "Unreadable answer." }));
    if (!res.ok) { const err = new Error(out.message || "Refused."); err.code = out.error; err.status = res.status; throw err; }
    return out;
  }

  // -- controls: each returns {node, get()} -------------------------------------------------------------------------

  function control(f, value) {
    const s = f.schema, id = nextId(), w = f.hint.widget;
    const describedBy = f.help ? id + "-help" : null;
    const common = { id, "aria-describedby": describedBy, required: f.required || null };
    let node, get;
    switch (f.kind) {
      case "group": {
        const inner = form(s, null, value || {}, f.path + ".", f.hintsRoot);
        return { node: h("fieldset", { class: "group" }, h("legend", {}, f.label), f.help ? h("p", { class: "muted", id: describedBy }, f.help) : null, inner.node), get: inner.get, bare: true };
      }
      case "table": return table(f, value);
      case "boolean": {
        const box = h("input", { type: "checkbox", ...common });
        box.checked = value === true;
        node = h("label", { class: "check" }, box, " ", f.label);
        return { node: h("div", { class: "field" }, node, f.help ? h("p", { class: "muted", id: describedBy }, f.help) : null), get: () => box.checked, bare: true };
      }
      case "multi": {
        const ch = choicesOf(s.items), chosen = new Set(Array.isArray(value) ? value.map(String) : []);
        const boxes = ch.map((c) => { const b = h("input", { type: "checkbox", value: String(c.value) }); b.checked = chosen.has(String(c.value)); return [b, c]; });
        node = h("div", { class: "choices", role: "group", "aria-labelledby": id + "-l" }, boxes.map(([b, c]) => h("label", { class: "check" }, b, " ", c.label)));
        return { node, get: () => boxes.filter(([b]) => b.checked).map(([, c]) => c.value), labelId: id + "-l" };
      }
      case "list": {
        const ta = h("textarea", { ...common, rows: 4 });
        ta.value = Array.isArray(value) ? value.join("\n") : "";
        const numeric = ["number", "integer"].includes((s.items || {}).type);
        const sugg = (s.items || {}).examples;
        node = h("div", {}, ta, h("p", { class: "muted" }, "One per line." + (sugg && sugg.length ? " For example: " + sugg.join("; ") : "")));
        return { node, get: () => ta.value.split("\n").map((x) => x.trim()).filter(Boolean).map((x) => (numeric ? Number(x) : x)), forId: id };
      }
      case "choice": {
        const ch = choicesOf(s);
        if (w === "dropdown" || (w !== "radio" && ch.length > 5)) {
          const sel = h("select", common, h("option", { value: "" }, "Choose…"), ch.map((c, i) => h("option", { value: String(i) }, c.label)));
          const at = ch.findIndex((c) => c.value === value);
          sel.value = at >= 0 ? String(at) : "";
          return { node: sel, get: () => (sel.value === "" ? undefined : ch[Number(sel.value)].value), forId: id };
        }
        const name = id + "-r";
        const radios = ch.map((c) => { const r = h("input", { type: "radio", name, required: f.required || null }); r.checked = c.value === value; return [r, c]; });
        node = h("div", { class: "choices", role: "radiogroup", "aria-labelledby": id + "-l" }, radios.map(([r, c]) => h("label", { class: "check" }, r, " ", c.label)));
        return { node, get: () => { const hit = radios.find(([r]) => r.checked); return hit ? hit[1].value : undefined; }, labelId: id + "-l" };
      }
      case "number": {
        const inp = h("input", { type: "number", ...common, min: s.minimum, max: s.maximum, step: s.type === "integer" ? "1" : "any" });
        if (typeof value === "number") inp.value = String(value);
        if (w === "slider" && s.minimum != null && s.maximum != null) {
          inp.type = "range";
          const out = h("output", { for: id }, inp.value || "");
          inp.addEventListener("input", () => { out.textContent = inp.value; });
          node = h("div", { class: "slider" }, inp, out);
        } else node = inp;
        return { node, get: () => (inp.value === "" ? undefined : Number(inp.value)), forId: id };
      }
      case "textarea": {
        const ta = h("textarea", { ...common, rows: 5, maxlength: s.maxLength });
        ta.value = typeof value === "string" ? value : "";
        return { node: ta, get: () => ta.value, forId: id };
      }
      default: {
        const type = { date: "date", time: "time", datetime: "datetime-local" }[f.kind] || (s.format === "email" ? "email" : s.format === "uri" ? "url" : "text");
        const inp = h("input", { type, ...common, maxlength: s.maxLength });
        if (value != null) inp.value = String(value);
        let list = null;
        if (Array.isArray(s.examples) && s.examples.length) {
          list = h("datalist", { id: id + "-s" }, s.examples.map((x) => h("option", { value: String(x) })));
          inp.setAttribute("list", id + "-s");
        }
        return { node: list ? h("div", {}, inp, list) : inp, get: () => inp.value, forId: id };
      }
    }
  }

  function wrapField(f, c) {
    if (c.bare) return c.node;
    const label = c.forId ? h("label", { for: c.forId, class: "label" }, f.label) : h("div", { class: "label", id: c.labelId }, f.label);
    if (f.required) label.append(h("span", { class: "req", "aria-hidden": "true" }, " *"));
    const base = c.forId || (c.labelId || "").replace(/-l$/, "");
    return h("div", { class: "field" }, label, f.help ? h("p", { class: "muted", id: base + "-help" }, f.help) : null, c.node);
  }

  /** An object's fields as a form: {node, get()}. ``hints`` are the request's (field names are dotted from the top). */
  function form(schema, hints, values, prefix, hintsRoot) {
    hintsRoot = hintsRoot || hints || {};
    const fields = fieldsOf(schema, hintsRoot, prefix || "");
    for (const f of fields) f.hintsRoot = hintsRoot;
    const controls = new Map(fields.map((f) => [f.name, control(f, (values || {})[f.name])]));
    const parts = prefix ? [{ title: null, fields }] : layout(fields, hintsRoot);
    const node = h("div", { class: "form" }, parts.map((p) => {
      const inner = p.fields.map((f) => wrapField(f, controls.get(f.name)));
      return p.title ? h("fieldset", { class: "group" }, h("legend", {}, p.title), inner) : inner;
    }));
    return { node, get: () => { const o = {}; for (const [n, c] of controls) o[n] = c.get(); return o; } };
  }

  /** A list of objects as a table: a row per item, fixed when the prefill gives the rows, else rows the owner adds. */
  function table(f, value) {
    const s = f.schema, item = s.items || {};
    const cols = fieldsOf(item, f.hintsRoot, f.path + ".");
    const { fixed, rows, givenKeys } = tableRows(s, value);
    const body = h("tbody", {});
    const live = [];
    function addRow(row, given) {
      const cells = cols.map((c) => {
        if (given && given.has(c.name)) return { td: h("td", {}, display(c.schema, row[c.name])), get: () => row[c.name] };
        const ctl = control({ ...c, kind: c.kind, hint: c.hint, hintsRoot: f.hintsRoot }, row[c.name]);
        const el = ctl.node;
        if (el.setAttribute && !ctl.labelId) el.setAttribute("aria-label", c.label);
        if (ctl.labelId && el.setAttribute) el.setAttribute("aria-label", c.label);
        return { td: h("td", {}, el), get: ctl.get };
      });
      const entry = { cells };
      const tr = h("tr", {}, cells.map((x) => x.td));
      if (!fixed) tr.append(h("td", {}, h("button", { type: "button", class: "quiet small", "aria-label": "Remove this row", onclick: () => {
        live.splice(live.indexOf(entry), 1); tr.remove(); sync(); } }, "Remove")));
      entry.tr = tr;
      live.push(entry);
      body.append(tr);
    }
    const add = fixed ? null : h("button", { type: "button", class: "quiet small", onclick: () => { addRow({}, null); sync(); } }, "Add a row");
    function sync() { if (add) add.disabled = s.maxItems != null && live.length >= s.maxItems; }
    rows.forEach((r, i) => addRow(r, givenKeys[i]));
    if (!fixed) for (let i = live.length; i < (s.minItems || 0); i++) addRow({}, null);
    sync();
    const node = h("div", { class: "field" }, h("div", { class: "label" }, f.label),
      f.help ? h("p", { class: "muted" }, f.help) : null,
      h("div", { class: "table-wrap" }, h("table", { class: "answer-table" },
        h("thead", {}, h("tr", {}, cols.map((c) => h("th", { scope: "col", title: c.help || null }, c.label)), fixed ? null : h("th", {}, h("span", { class: "sr" }, "Actions")))),
        body)),
      add);
    return { node, get: () => live.map((e) => { const o = {}; e.cells.forEach((c, i) => { o[cols[i].name] = c.get(); }); return o; }), bare: true };
  }

  // -- context ------------------------------------------------------------------------------------------------------

  function contextItem(req, c) {
    const head = h("div", { class: "label" }, c.label || humanize(c.id));
    if (c.kind === "table") {
      return h("div", { class: "card context" }, head, h("div", { class: "table-wrap" }, h("table", {},
        h("thead", {}, h("tr", {}, (c.columns || []).map((x) => h("th", { scope: "col" }, x)))),
        h("tbody", {}, (c.rows || []).map((r) => h("tr", {}, r.map((x) => h("td", {}, x == null ? "" : String(x)))))))));
    }
    if (c.ref === undefined) return h("div", { class: "card context" }, head, h("div", { class: "text" }, c.text || ""));
    const box = h("div", { class: "text" });
    const show = h("button", { type: "button", class: "quiet small", onclick: async () => {
      show.disabled = true;
      try {
        const got = await call("GET", api(req.id) + "/context/" + encodeURIComponent(c.id));
        box.replaceChildren(got.text != null ? got.text : "This item cannot be shown as text here (" + (got.media_type || "a file") + ", " + got.size + " bytes).");
        show.remove();
      } catch (e) { box.textContent = e.message; show.disabled = false; }
    } }, "Show");
    return h("div", { class: "card context" }, head, show, box);
  }

  // -- one request --------------------------------------------------------------------------------------------------

  const project = m && decodeURIComponent(m[1]);
  const api = (id) => "/api/p/" + encodeURIComponent(project) + "/interactions" + (id ? "/" + encodeURIComponent(id) : "");
  const listUrl = () => "/p/" + encodeURIComponent(project) + "/requests";
  const main = () => $("req");

  function say(text, bad) {
    const n = $("req-notice");
    n.textContent = text || ""; n.hidden = !text; n.className = bad ? "bad" : "";
  }

  function fallback(req, why) {
    const file = "answer-" + req.id + ".yaml";
    return h("div", { class: "card" },
      h("p", {}, why || "This question cannot be answered on this page. Ask your assistant, or fill in an answer file:"),
      h("pre", { class: "cmd" }, "baton answer " + req.id + " --template\nbaton answer " + req.id + " --file " + file + " --via answer_file"));
  }

  function confirmView(req, choice, values, schema) {
    const box = $("req-step");
    const rows = schema ? summaryRows(schema, req.hints, values) : [];
    const note = h("textarea", { id: "req-note", rows: 3, placeholder: "Optional" });
    const confirm = h("button", { type: "button" }, "Confirm");
    const back = h("button", { type: "button", class: "quiet" }, "Change my answer");
    box.replaceChildren(h("div", { class: "card confirm" },
      h("h2", {}, "Check before it is recorded"),
      choice ? h("p", {}, h("strong", {}, choice.label), choice.effect ? " — " + choice.effect : "") : null,
      rows.length ? h("dl", { class: "summary" }, rows.map((r) => [h("dt", {}, r.label), h("dd", {}, summaryValue(r))])) : null,
      h("label", { for: "req-note", class: "label" }, "Anything to add? (recorded with your answer)"), note,
      h("div", { class: "actions" }, confirm, back)));
    back.addEventListener("click", () => showRequest(req, choice, values));
    confirm.addEventListener("click", async () => {
      confirm.disabled = back.disabled = true;
      const body = { note: note.value.trim() };
      if (choice) body.choice = choice.decision;
      if (schema) body.values = clean(values);
      try {
        await call("POST", api(req.id) + "/answer", body);
        box.replaceChildren(h("div", { class: "card done" }, h("h2", {}, "Recorded"),
          h("p", {}, "Your answer is recorded. Your assistant carries on from here."), h("p", {}, h("a", { href: listUrl() }, "See what else is waiting"))));
        $("req-choices").replaceChildren();
        say("");
      } catch (e) {
        if (e.status === 409) {
          box.replaceChildren(h("div", { class: "card" }, h("p", {}, "This question was answered already, or it changed while it was open. Nothing was recorded."),
            h("p", {}, h("a", { href: listUrl() }, "See the questions waiting now"))));
        } else { say(e.message, true); confirm.disabled = back.disabled = false; }
      }
    });
    note.focus();
  }

  function summaryValue(r) {
    if (r.schema.type === "array" && (r.schema.items || {}).type === "object") {
      const cols = fieldsOf(r.schema.items, {}, "");
      const v = Array.isArray(r.value) ? r.value : [];
      return h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, cols.map((c) => h("th", {}, c.label)))),
        h("tbody", {}, v.map((row) => h("tr", {}, cols.map((c) => h("td", {}, display(c.schema, (row || {})[c.name]))))))));
    }
    if (r.schema.type === "object") {
      const cols = fieldsOf(r.schema, {}, "");
      return h("dl", { class: "summary" }, cols.map((c) => [h("dt", {}, c.label), h("dd", {}, display(c.schema, (r.value || {})[c.name]))]));
    }
    return display(r.schema, r.value);
  }

  function answerForm(req, choice, spec, values) {
    const box = $("req-step");
    if (!spec.renderable) { box.replaceChildren(fallback(req)); return; }
    const f = form(spec.schema, req.hints || {}, values !== undefined ? values : spec.prefill || {});
    const next = h("button", { type: "submit" }, "Review");
    const el = h("form", { class: "card", novalidate: true }, choice ? h("h2", {}, choice.label) : null, f.node, h("div", { class: "actions" }, next));
    el.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const v = f.get();
      const problems = validate(spec.schema, clean(v), "", true, null, req.hints || {});
      if (problems.length) { say(problems.map((p) => p.message).join(" "), true); return; }
      say("");
      confirmView(req, choice, v, spec.schema);
    });
    box.replaceChildren(el);
  }

  function showRequest(req, chosen, values) {
    $("req-step").replaceChildren();
    const choices = $("req-choices");
    choices.replaceChildren();
    if (req.choices && req.choices.length) {
      choices.append(h("h2", {}, "Your choice"), h("div", { class: "choice-list" }, req.choices.map((c) => {
        const b = h("button", { type: "button", class: chosen && chosen.decision === c.decision ? "" : "quiet", "aria-pressed": chosen && chosen.decision === c.decision ? "true" : "false" },
          h("span", { class: "choice-label" }, c.label), c.effect ? h("span", { class: "choice-effect" }, c.effect) : null);
        b.addEventListener("click", () => showRequest(req, c));
        return b;
      })));
      if (chosen) {
        if (chosen.answer) answerForm(req, chosen, chosen.answer, values);
        else confirmView(req, chosen, null, null);
      }
    } else if (req.answer) {
      if ((req.files || []).length) { $("req-step").replaceChildren(fallback(req, "This step also asks for files. Until the page takes files, answer it with an answer file:")); return; }
      answerForm(req, null, req.answer, values);
    } else $("req-step").replaceChildren(fallback(req));
  }

  async function openRequest(id) {
    let req;
    try { req = await call("GET", api(id)); }
    catch (e) {
      main().replaceChildren(h("div", { class: "page-head" }, h("h1", {}, "Not waiting any more")),
        h("p", {}, e.status === 409 ? "This question was answered already, or it changed. Nothing more is needed here." : e.message),
        h("p", {}, h("a", { href: listUrl() }, "See the questions waiting now")));
      return;
    }
    document.title = req.title + " · Baton";
    main().replaceChildren(
      h("p", { class: "crumbs" }, h("a", { href: listUrl() }, "Waiting for you"), " / ", project),
      h("div", { class: "page-head" }, h("h1", {}, req.title)),
      h("p", { id: "req-notice", role: "status", hidden: true }),
      h("div", { class: "message" }, req.message),
      (req.context || []).length ? h("section", { "aria-label": "What to look at" }, req.context.map((c) => contextItem(req, c))) : null,
      h("section", { id: "req-choices" }),
      h("section", { id: "req-step" }));
    showRequest(req, null);
  }

  async function openList() {
    document.title = "Waiting for you · Baton";
    let out;
    try { out = await call("GET", api(null)); }
    catch (e) { main().replaceChildren(h("h1", {}, "Waiting for you"), h("p", { class: "bad" }, e.message)); return; }
    const reqs = out.requests || [];
    main().replaceChildren(
      h("div", { class: "page-head" }, h("h1", {}, "Waiting for you"), h("p", { class: "sub" }, project)),
      reqs.length ? h("ul", { class: "req-list" }, reqs.map((r) => h("li", { class: "card" },
        h("a", { href: listUrl() + "/" + encodeURIComponent(r.id) }, r.title), h("p", { class: "muted" }, r.message))))
        : h("p", { class: "muted" }, "Nothing is waiting for you in this project."));
  }

  if (inRequests()) {
    $("view-setup").hidden = true; $("view-requests").hidden = false;
    const tab = document.querySelector('[data-tab="requests"]');
    if (tab) { tab.hidden = false; tab.setAttribute("href", listUrl()); }
    if (m[2]) openRequest(decodeURIComponent(m[2])); else openList();
  }
})();
