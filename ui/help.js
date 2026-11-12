"use strict";
// Context help on the Setup page (§13.10): a "?" beside a part of the page opens the manual's short answer for it in a side panel.
// The page keeps no copy of the words: it reads the manual through /api/manual/* and the map in context.yaml.
(function () {
  const { render, topicUrl, el } = window.BatonRender;
  let ctx = null, opener = null, panel = null;

  async function context() {
    if (ctx) return ctx;
    try { const res = await fetch("/api/manual/context"); ctx = res.ok ? await res.json() : { ui: {}, errors: {} }; }
    catch (e) { ctx = { ui: {}, errors: {} }; }
    return ctx;
  }

  function build() {
    const close = el("button", { type: "button", class: "quiet panel-close", "aria-label": "Close help" }, "Close");
    close.addEventListener("click", hide);
    panel = el("aside", { id: "help-panel", class: "panel", role: "dialog", "aria-labelledby": "help-title", hidden: true },
      el("div", { class: "panel-head" }, el("h2", { id: "help-title" }, ""), close),
      el("div", { id: "help-body", class: "panel-body", tabindex: "-1" }),
      el("div", { class: "panel-foot" }, el("a", { id: "help-more", href: "/manual" }, "Open the full guide")));
    document.body.append(panel);
    panel.addEventListener("click", (e) => {
      const a = e.target.closest("a[data-topic]");
      if (!a) return;
      e.preventDefault();
      const m = /^\/manual\/([a-z]+)\/([a-z0-9-]+)(?:#(.*))?$/.exec(a.getAttribute("href"));
      if (m) show(m[1] + "." + m[2] + (m[3] ? "#" + m[3] : ""));
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !panel.hidden) hide(); });
    document.addEventListener("click", (e) => {
      if (!panel.hidden && !e.target.closest("#help-panel") && !e.target.closest("[data-help]")) hide();
    });
  }

  function hide() {
    if (!panel || panel.hidden) return;
    panel.hidden = true; document.body.classList.remove("help-open");
    if (opener && document.contains(opener)) opener.focus();
  }

  async function show(ref) {
    if (!panel) build();
    const c = await context();
    const target = ref.startsWith("ui.") ? c.ui[ref] : ref;
    const body = document.getElementById("help-body"), title = document.getElementById("help-title");
    panel.hidden = false; document.body.classList.add("help-open");
    if (!target) { title.textContent = "Help"; body.replaceChildren(el("p", {}, "There is no help written for this part yet.")); return; }
    const [id, anchor] = target.split("#");
    try {
      const res = await fetch("/api/manual/topic/" + encodeURIComponent(id) + (anchor ? "?anchor=" + encodeURIComponent(anchor) : ""));
      const page = await res.json();
      if (!res.ok) throw new Error(page.message || "Not available.");
      title.textContent = page.title;
      body.replaceChildren(render(page.markdown));
      document.getElementById("help-more").setAttribute("href", topicUrl(id, anchor));
      body.scrollTop = 0;
    } catch (e) {
      title.textContent = "Help";
      body.replaceChildren(el("p", {}, "That help is not available: " + e.message));
    }
    document.querySelector("#help-panel .panel-close").focus({ preventScroll: true });
  }

  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-help]");
    if (!b) return;
    e.preventDefault();
    opener = b;
    show(b.getAttribute("data-help"));
  });

  async function forError(code) { return code ? ((await context()).errors[code] || null) : null; }

  window.BatonHelp = { show, forError };
})();
