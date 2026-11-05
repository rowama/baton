---
id: "0057"
title: "BATON_OWNER_EXIT=0 makes owner-needed exit 0; the default stays 4"
status: accepted
date: 2026-11-04
source: "change 2026-11-director-wake (bug eval 2026-11-04-director-wake-on-needs-human, B3)"
sections: ["§13.1"]
---

# 0057. BATON_OWNER_EXIT=0 makes owner-needed exit 0; the default stays 4

## Context

`dispatch --wait` and `wait` exit 4 when the work finished and the run now waits on the owner, a success-path outcome. Some harnesses (the Grok Bot shell) mark any non-zero exit as `failed`, which made finished work look failed and may have changed how the harness delivered its wake. Changing the default would break existing scripts.

## Decision

The default stays 4. A Director's environment may set `BATON_OWNER_EXIT=0`, which makes every command that would exit 4 for a needed owner decision exit 0 instead; `needs_owner: true` stays in the JSON either way. An environment variable rather than a per-command flag, so it is set once beside `BATON_DIRECTOR` and `BATON_HARNESS` and cannot be forgotten on one call.
