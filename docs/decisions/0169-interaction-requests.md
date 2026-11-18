---
id: "0169"
title: "Baton asks the owner through renderer-neutral interaction requests; how one is shown is the client's choice at the time, and recipes ship no script"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"I just want the recipe step/worker to ask for a structured interaction and let the owner have their preferred best experience available at any point in the future. Very loose coupling from interaction request to actual interaction client rendering.\"; \"Rewrite as interaction-requests and then obsolete the old proposal. Include a gui renderer as the baseline option\"; \"Concur with leaving JS out.\""
sections: ["§2", "§7.2", "§13.8", "§13.9"]
---

# 0169. Baton asks the owner through renderer-neutral interaction requests; how one is shown is the client's choice at the time, and recipes ship no script

## Context

`2026-11-person-step-forms` (on hold) proposed that Baton render a form for a person's step and serve it as a page on the owner's machine. That ties what a step asks to one way of showing it. The owner wants a step or worker only to ask for a structured interaction, and the owner to see it in whatever way suits them where they are at the time: in conversation with the Director, in a terminal, in a web panel of a web-based Director, in a desktop window, or through ways not yet built.

MCP's form elicitation works this way for tools: the server sends a JSON Schema and each client decides how to show it. It is limited to flat objects with primitive properties, too little for a table with a choice per row.

## Decision

1. **Baton asks through interaction requests.** An interaction request is data: what is asked, the shape of the answer as a schema, what to show for context, the choices and their effects, and optional presentation hints. It says nothing about how it is drawn. It has its own versioned format.
2. **Rendering is the client's choice at the time.** A renderer is a client, never part of the runtime and never required. Any number may exist; each says what it can show and falls back for what it cannot. The Director in conversation can always render a request.
3. **Hints are advice.** Order, grouping and a preferred widget may be given. A renderer may ignore any hint and still produce a correct answer. Renderer-specific extensions are allowed and are ignored by other renderers.
4. **Recipes ship no script for rendering.** A request carries no JavaScript or other code. A renderer's own code ships with the renderer.
5. **One way back in.** Whatever renderer was used, an answer comes back through one call, is checked against the request's schema, and is recorded as the owner's decision with their confirmation, as every owner decision is.
6. **The first renderer to ship besides conversation is a GUI**, a page of the optional local UI (§13.9), as its own change (`2026-11-interaction-ui`). "Baseline" means the best one to ship first, not the only or the best one.
7. **`2026-11-person-step-forms` is abandoned**, superseded by `2026-11-interaction-requests`.
