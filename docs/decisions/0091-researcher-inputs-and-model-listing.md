---
id: "0091"
title: "The researcher gets tool maps, starting URLs and LiteLLM entries; model availability is verified by use"
status: accepted
date: 2026-11-08
source: "change 2026-11-cli-model-routes (owner, 2026-11-08)"
sections: ["§4.1", "§6.4"]
---

# 0091. The researcher gets tool maps, starting URLs and LiteLLM entries; model availability is verified by use

## Context

Extends 0083. Three questions were open: how to treat the models a plan does not allow in a CLI, where LiteLLM's model-map facts are read, and where the starting documentation URLs live.

## Decision

- **Entitlement:** which models an owner's plan allows in a harness CLI is left to verification by use: an unavailable model fails as `platform` and the profile is re-routed (0086). `workers setup` does not ask the CLI to list models, since no CLI is known to offer that and a listing mechanism per CLI would tie setup to particular CLIs.
- **Catalog facts:** the researcher reads LiteLLM's model map and the facts are written into the data, reviewed in the diff; `workers setup` never reads LiteLLM at run time. The report records the LiteLLM version.
- **Starting URLs:** a maintainer file, `tools/worker-research/harness-docs.yaml`, per harness provider.
- **Inputs (extends 0083):** the packet also carries the current tool maps, the vocabulary's tooling capabilities, the starting URLs, the LiteLLM entries for every API route in the data, and a command the worker may run to validate its own proposal.
