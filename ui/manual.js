"use strict";
// The manual reader and the search box (§13.10). Read-only: it only GETs /api/manual/*.
(function () {
  const { render, topicUrl, el } = window.BatonRender;
  const $ = (id) => document.getElementById(id);
  // The same script reads the local API (baton ui) or, in the static site (tools/build_site.py), JSON files beside the pages.
  const BASE = window.BATON_BASE || "", STATIC = !!window.BATON_STATIC;
  const here = () => location.pathname.slice(BASE.length) || "/";
  const inManual = () => here() === "/manual" || here().startsWith("/manual/");
  let tree = null, current = null, spy = null;

  let corpus = null;
  async function get(path) {
    if (STATIC) {
      const m = /^\/api\/manual\/(tree|topic\/(.+))$/.exec(path);
      if (m) path = "/api/manual/" + (m[2] ? "topic/" + m[2] : "tree") + ".json";
      path = BASE + path;
    }
    const res = await fetch(path);
    const out = await res.json().catch(() => ({ ok: false, message: "Unreadable answer." }));
    if (!res.ok) throw new Error(out.message || "Not available.");
    return out;
  }

  // ---- navigation tree ---------------------------------------------------
  function buildNav() {
    const nav = $("nav"); nav.replaceChildren();
    nav.append(el("a", { href: BASE + "/manual", class: "nav-home", "data-topic": "1" }, "Manual home"));
    for (const part of tree) {
      nav.append(el("details", { class: "nav-group", "data-part": part.part },
        el("summary", { class: "nav-part" }, part.title),
        el("ul", {}, part.topics.map((t) => el("li", {}, el("a", { href: topicUrl(t.id), "data-topic": "1", "data-id": t.id }, t.title))))));
    }
  }

  function markNav(id) {
    for (const a of $("nav").querySelectorAll("a[data-id]")) {
      if (a.dataset.id === id) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
    // The part you are reading is open; at the manual's home, the user guide is.
    for (const d of $("nav").querySelectorAll("details.nav-group")) d.open = id ? d.querySelector("[aria-current]") !== null : d.dataset.part === "user";
  }

  // ---- pages ------------------------------------------------------------------
  function landing() {
    current = null; markNav("");
    document.title = "Manual · Baton";
    const doc = $("doc"); doc.replaceChildren();
    doc.append(el("h1", {}, "Baton manual"),
      el("p", { class: "lead" }, "Everything about using and running Baton, from one place. Each page opens with the short answer; read on for the detail."),
      el("div", { class: "cards" }, tree.map((p) => el("section", { class: "card topic-card" },
        el("h2", {}, p.title), el("p", { class: "muted" }, p.blurb),
        el("ul", { class: "plain" }, p.topics.map((t) => el("li", {}, el("a", { href: topicUrl(t.id), "data-topic": "1" }, t.title))))))));
    $("toc").replaceChildren();
    window.scrollTo(0, 0);
  }

  function neighbour(label, t) {
    return t ? el("a", { class: "pager-" + label.toLowerCase(), href: topicUrl(t.id), "data-topic": "1" },
      el("span", { class: "muted" }, label), el("strong", {}, t.title)) : el("span");
  }

  async function show(id, anchor) {
    let page;
    try { page = await get("/api/manual/topic/" + encodeURIComponent(id)); }
    catch (e) { $("doc").replaceChildren(el("h1", {}, "Not found"), el("p", {}, "There is no manual page at this address."), el("a", { href: BASE + "/manual", "data-topic": "1" }, "Back to the manual home")); return; }
    current = id; markNav(id);
    document.title = page.title + " · Baton manual";
    const doc = $("doc"); doc.replaceChildren(
      el("nav", { class: "crumbs", "aria-label": "Breadcrumb" }, el("a", { href: BASE + "/manual", "data-topic": "1" }, "Manual"), " / ", page.part_title),
      el("h1", {}, page.title), el("p", { class: "lead" }, page.summary), render(page.markdown));
    if (page.related.length) doc.append(el("section", { class: "related" }, el("h2", {}, "Related"),
      el("ul", { class: "plain" }, page.related.map((r) => el("li", {}, el("a", { href: topicUrl(r.id), "data-topic": "1" }, r.title))))));
    doc.append(el("nav", { class: "pager", "aria-label": "Previous and next" }, neighbour("Previous", page.prev), neighbour("Next", page.next)));
    buildToc(page.headings);
    if (anchor && document.getElementById(anchor)) document.getElementById(anchor).scrollIntoView(); else window.scrollTo(0, 0);
    closeNav();
  }

  function buildToc(headings) {
    const toc = $("toc"); toc.replaceChildren();
    if (!headings.length) return;
    toc.append(el("div", { class: "toc-title" }, "On this page"),
      el("ul", {}, headings.map((h) => el("li", { class: "l" + h.level }, el("a", { href: "#" + h.anchor, "data-anchor": h.anchor }, h.text)))));
    if (spy) spy.disconnect();
    spy = new IntersectionObserver((entries) => {
      for (const e of entries) if (e.isIntersecting) {
        for (const a of toc.querySelectorAll("a")) a.removeAttribute("aria-current");
        const a = toc.querySelector('a[data-anchor="' + e.target.id + '"]'); if (a) a.setAttribute("aria-current", "true");
      }
    }, { rootMargin: "0px 0px -70% 0px" });
    for (const h of headings) { const t = document.getElementById(h.anchor); if (t) spy.observe(t); }
  }

  function route() {
    const m = /^\/manual\/([a-z]+)\/([a-z0-9-]+)\/?$/.exec(here());
    if (!m) return landing();
    return show(m[1] + "." + m[2], decodeURIComponent(location.hash.slice(1)));
  }

  function go(url) { history.pushState({}, "", url); route(); }

  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[data-topic]");
    if (!a || e.defaultPrevented || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
    if (inManual()) { e.preventDefault(); go(a.getAttribute("href")); hideHits(); }
  });
  window.addEventListener("popstate", () => { if (inManual()) route(); });
  window.addEventListener("hashchange", () => { const t = document.getElementById(decodeURIComponent(location.hash.slice(1))); if (t) t.scrollIntoView(); });

  // ---- narrow screens: the contents open as a drawer --------------------------
  function closeNav() { document.body.classList.remove("nav-open"); const b = $("nav-toggle"); if (b) b.setAttribute("aria-expanded", "false"); }
  $("nav-toggle").addEventListener("click", () => {
    const open = document.body.classList.toggle("nav-open"); $("nav-toggle").setAttribute("aria-expanded", String(open));
  });

  // ---- search ------------------------------------------------------------------
  const q = $("q"), hits = $("hits");
  let timer = null, active = -1;
  function hideHits() { hits.hidden = true; q.setAttribute("aria-expanded", "false"); active = -1; }
  function mark(i) {
    const items = [...hits.children]; active = items.length ? (i + items.length) % items.length : -1;
    items.forEach((li, k) => li.classList.toggle("active", k === active));
  }
  async function search() {
    const text = q.value.trim();
    if (text.length < 2) return hideHits();
    let out; try { out = STATIC ? { results: await staticSearch(text) } : await get("/api/manual/search?q=" + encodeURIComponent(text)); } catch (e) { return hideHits(); }
    hits.replaceChildren();
    if (!out.results.length) hits.append(el("li", { class: "none" }, "Nothing found for “" + text + "”."));
    for (const r of out.results) hits.append(el("li", { role: "option" }, el("a", { href: topicUrl(r.id, r.anchor), "data-topic": "1" },
      el("strong", {}, r.title), el("span", { class: "muted" }, r.summary))));
    hits.hidden = false; q.setAttribute("aria-expanded", "true"); active = -1;
  }
  // Static site: the same scoring as the server's, over search.json.
  async function staticSearch(text) {
    if (!corpus) corpus = await (await fetch(BASE + "/search.json")).json();
    const words = (text.toLowerCase().match(/[a-z0-9]+/g) || []).filter((w) => w.length > 1);
    const out = [];
    for (const t of corpus) {
      let score = 0, anchor = null;
      for (const w of words) score += 5 * t.title.toLowerCase().includes(w) + 3 * t.summary.toLowerCase().includes(w) + t.text.toLowerCase().includes(w);
      for (const h of t.headings) if (words.some((w) => h.text.toLowerCase().includes(w))) { score += 2; anchor = anchor || h.anchor; }
      if (score) out.push({ id: t.id, anchor, title: t.title, summary: t.summary, score });
    }
    return out.sort((a, b) => b.score - a.score || (a.id < b.id ? -1 : 1)).slice(0, 12);
  }
  q.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(search, 120); });
  q.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { e.preventDefault(); mark(active + 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); mark(active - 1); }
    else if (e.key === "Enter") { const a = hits.children[Math.max(active, 0)]; if (a && a.querySelector("a")) a.querySelector("a").click(); }
    else if (e.key === "Escape") { hideHits(); q.blur(); }
  });
  document.addEventListener("click", (e) => { if (!e.target.closest(".search")) hideHits(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) { e.preventDefault(); q.focus(); q.select(); }
  });

  // ---- start -------------------------------------------------------------------
  const tabs = document.querySelectorAll("[data-tab]");
  for (const t of tabs) if ((t.dataset.tab === "manual") === inManual()) t.setAttribute("aria-current", "page");
  window.BatonManual = { inManual };
  if (inManual()) {
    $("view-setup").hidden = true; $("view-manual").hidden = false; if (!STATIC) $("quit").hidden = false;
    get("/api/manual/tree").then((out) => { tree = out.parts; buildNav(); return route(); })
      .catch((e) => { $("doc").replaceChildren(el("h1", {}, "The manual is not available"), el("p", {}, e.message)); });
  }
})();
