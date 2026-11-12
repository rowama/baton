"use strict";
// Renders the manual's Markdown subset (§13.10) into DOM nodes. It builds nodes, never HTML strings,
// so nothing in a topic can inject markup. The subset is enforced by the checks in baton/manual.py.
(function () {
  function el(tag, attrs, ...kids) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) e.setAttribute(k, v === true ? "" : v);
    for (const k of kids.flat()) e.append(k instanceof Node ? k : document.createTextNode(String(k)));
    return e;
  }

  // A topic id (user.connect-an-account) is its address: /manual/user/connect-an-account
  function topicUrl(id, anchor) {
    const i = id.indexOf(".");
    return "/manual/" + id.slice(0, i) + "/" + id.slice(i + 1) + (anchor ? "#" + anchor : "");
  }

  function link(text, target, parent) {
    let a;
    if (/^https:\/\//.test(target)) {
      a = el("a", { href: target, target: "_blank", rel: "noopener noreferrer", class: "ext" });
    } else if (target.startsWith("#")) {
      a = el("a", { href: target });
    } else {
      const [id, anchor] = target.split("#");
      a = el("a", { href: topicUrl(id, anchor), "data-topic": "1" });
    }
    inline(text, a);
    parent.append(a);
  }

  const INLINE = /`([^`]+)`|\*\*(.+?)\*\*|\*([^*\s][^*]*)\*|\[([^\]]*)\]\(([^)\s]*)\)/;

  function inline(text, parent) {
    let last = 0, m;
    const re = new RegExp(INLINE.source, "g");  // its own lastIndex: bold and links call inline again
    while ((m = re.exec(text))) {
      if (m.index > last) parent.append(text.slice(last, m.index));
      if (m[1] !== undefined) parent.append(el("code", {}, m[1]));
      else if (m[2] !== undefined) { const b = el("strong"); inline(m[2], b); parent.append(b); }
      else if (m[3] !== undefined) { const b = el("em"); inline(m[3], b); parent.append(b); }
      else link(m[4], m[5], parent);
      last = re.lastIndex;
    }
    if (last < text.length) parent.append(text.slice(last));
  }

  const LIST = /^(\s*)([-*]|\d+\.)\s+(.*)$/;

  function parse(md) {
    const lines = md.split("\n"), out = [];
    let i = 0;
    const blockStart = (l) => l.startsWith("```") || /^#{2,3}\s/.test(l) || l.startsWith("|") || l.startsWith(">") || LIST.test(l);
    while (i < lines.length) {
      const l = lines[i];
      if (!l.trim()) { i++; continue; }
      let m;
      if (l.startsWith("```")) {
        const lang = l.slice(3).trim(), body = [];
        for (i++; i < lines.length && !lines[i].startsWith("```"); i++) body.push(lines[i]);
        i++;
        out.push({ t: "code", lang, text: body.join("\n") });
      } else if ((m = /^(#{2,3})\s+(.*?)\s*\{#([a-z0-9-]+)\}\s*$/.exec(l))) {
        out.push({ t: "h", level: m[1].length, text: m[2], id: m[3] }); i++;
      } else if (l.startsWith("|")) {
        const rows = [];
        for (; i < lines.length && lines[i].startsWith("|"); i++) rows.push(lines[i].trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim()));
        out.push({ t: "table", head: rows[0], rows: rows.slice(2) });
      } else if (l.startsWith(">")) {
        const body = [];
        for (; i < lines.length && lines[i].startsWith(">"); i++) body.push(lines[i].replace(/^>\s?/, ""));
        const text = body.join(" "), k = /^\*\*(Note|Warning):\*\*\s*/.exec(text);
        out.push({ t: "note", kind: k ? k[1].toLowerCase() : "note", text: k ? text.slice(k[0].length) : text });
      } else if ((m = LIST.exec(l))) {
        const ordered = /\d/.test(m[2]), items = [];
        while (i < lines.length && lines[i].trim() !== "---") {
          const li = LIST.exec(lines[i]);
          if (li && /\d/.test(li[2]) === ordered) { items.push(li[3]); i++; }
          else if (items.length && /^\s{2,}\S/.test(lines[i])) { items[items.length - 1] += " " + lines[i].trim(); i++; }
          else if (!lines[i].trim() && LIST.test(lines[i + 1] || "") && /\d/.test(LIST.exec(lines[i + 1])[2]) === ordered) i++;
          else break;
        }
        out.push({ t: "list", ordered, items });
      } else {
        const body = [];
        for (; i < lines.length && lines[i].trim() && (body.length === 0 || !blockStart(lines[i])); i++) body.push(lines[i].trim());
        out.push({ t: "p", text: body.join(" ") });
      }
    }
    return out;
  }

  function copyButton(text) {
    const b = el("button", { type: "button", class: "copy" }, "Copy");
    b.addEventListener("click", () => {
      const done = (t) => { b.textContent = t; setTimeout(() => { b.textContent = "Copy"; }, 1600); };
      if (navigator.clipboard) navigator.clipboard.writeText(text).then(() => done("Copied"), () => done("Select and copy"));
      else done("Select and copy");
    });
    return b;
  }

  function node(b) {
    switch (b.t) {
      case "p": { const p = el("p"); inline(b.text, p); return p; }
      case "list": {
        const l = el(b.ordered ? "ol" : "ul");
        for (const it of b.items) { const li = el("li"); inline(it, li); l.append(li); }
        return l;
      }
      case "table": {
        const tr = (cells, tag) => el("tr", {}, cells.map((c) => { const x = el(tag); inline(c, x); return x; }));
        return el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, tr(b.head, "th")), el("tbody", {}, b.rows.map((r) => tr(r, "td")))));
      }
      case "note": {
        const p = el("p"); inline(b.text, p);
        return el("div", { class: "callout " + b.kind, role: "note" }, el("div", { class: "callout-label" }, b.kind === "warning" ? "Warning" : "Note"), p);
      }
      case "code": {
        const label = b.lang === "baton" ? "Terminal" : b.lang;
        return el("div", { class: "code" }, el("div", { class: "code-bar" }, el("span", {}, label || ""), copyButton(b.text)), el("pre", {}, el("code", {}, b.text)));
      }
    }
  }

  // Each ## starts a <section id=anchor>, so "Here, now" can be styled and linked as a unit.
  function render(md) {
    const frag = document.createDocumentFragment();
    let sec = null;
    for (const b of parse(md)) {
      if (b.t === "h") {
        const a = el("a", { class: "anchor", href: "#" + b.id, "aria-label": "Link to this section" }, "#");
        const h = el("h" + b.level, { id: b.id }, b.text, a);
        if (b.level === 2) { sec = el("section", { class: "sec" + (b.id === "here-now" ? " here-now" : ""), "aria-labelledby": b.id }); frag.append(sec); }
        (sec || frag).append(h);
      } else (sec || frag).append(node(b));
    }
    return frag;
  }

  window.BatonRender = { render, topicUrl, parse, el };
})();
