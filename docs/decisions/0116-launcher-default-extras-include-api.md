---
id: "0116"
title: "The launcher's default extras include api"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§14"]
---

# 0116. The launcher's default extras include api

## Context

API routes and catalog data need LiteLLM (`baton[api]`), but a per-version install adds only the extras in `~/.baton/launcher.yaml`, default none.

## Decision

`api` becomes part of the launcher's default extras, so a project-pinned runtime can always run API routes. LiteLLM does not become a core dependency, since a project using only CLI harnesses should not carry it.
