---
id: "0122"
title: "The first UI is the stable only: a stdlib JSON API with a dependency-free front end"
status: accepted
date: 2026-11-10
source: "change 2026-11-setup-ui (owner, 2026-11-10: accept scope and packaging; the framework is a Design choice)"
sections: ["§13.9", "§13.2"]
---

# 0122. The first UI is the stable only: a stdlib JSON API with a dependency-free front end

## Context

Open questions 2 and 3 of the change. The owner accepted: first version is providers, models and preferences only; a JSON API served by `baton ui` from the runtime package; the framework is a Design choice.

## Decision

- Scope: providers, models and preferences. Project, run and recipe views are later work.
- The API is served by `baton ui` using only the standard library (`http.server`): no new runtime dependency, no `uvicorn`. It is the seam a later owner-interaction UI builds on.
- The front end is plain HTML, CSS and JavaScript, with no framework and no build step. It is data files shipped beside the runtime (`baton/_data/ui`), and no runtime module imports it.
- **Departure from the suggested answer.** The suggestion was a separately versioned front end in a `baton[ui]` extra. The launcher installs `baton[extras] @ <git source>` (§14.1), and an extra that names a second, unpublished distribution cannot be resolved that way. A dependency-free static front end costs the install nothing, so it ships in the wheel; the extra is not needed. If a framework or build step is ever adopted, the front end moves to its own distribution and an extra then.
