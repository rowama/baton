---
id: "0088"
title: "A researched capability needs a basis, not proof, and ships as likely"
status: accepted
date: 2026-11-08
source: "change 2026-11-cli-model-routes (owner, 2026-11-08)"
sections: ["§6.4"]
---

# 0088. A researched capability needs a basis, not proof, and ships as likely

## Context

The research prompt allowed a capability only with documented evidence, so the 2026-11-06 run claimed no `structured_output` for new models and no `web_access` for any route, though both were almost certainly present. Since 0084 a claimed capability is `likely` until the work shows otherwise, so a wrong claim costs one failed attempt and a missing claim costs the capability for good.

## Decision

- Every capability the data claims for a model or route carries a **basis**: `documented` (with a source URL), `catalog` (a field of LiteLLM's model map: `supports_response_schema` for `structured_output`, `supports_function_calling` for `tool_use`, `supports_vision` for `vision`), or `judgment` (the creator class's normal capabilities, with a one-line reason).
- All ship as `likely` and are checked by use (0084). A capability with no basis at all is omitted.
- The basis is an optional field, `capability_basis`, so the format stays `baton-known-workers/1`; the research tool refuses a proposal whose claimed capability has none.
