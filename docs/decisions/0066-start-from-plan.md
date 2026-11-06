---
id: "0066"
title: "A part is started later with start --from-plan, from the framing run's record"
status: accepted
date: 2026-11-05
source: "change 2026-11-framing-perspective (owner, 2026-11-05)"
sections: ["§11.6", "§13.1"]
---

# 0066. A part is started later with start --from-plan, from the framing run's record

## Context

Framing's breakdown keeps the parts the owner did not choose (0064). They need a way to be started later that starts exactly what they proposed.

## Decision

`baton start --from-plan <part>` (`<framing run>/<part>` when the part id is in more than one framing run) starts the part's proposal as recorded in the framing run's record, never as read from the published file, which the owner may have edited. A part already started is refused, naming its run. The start is recorded as `run_started.framing {run, part}`, as for `select`, and gaps are reported the same way.
