# Fit rubric

Score the idea row by row. Each row leans one way; the verdict follows the balance,
and any single row that strongly leans "operations engine" must be called out.

| Row | Fits Baton | Fits an operations engine |
|---|---|---|
| occurrences | Few occurrences (at most daily) | Many (per order, ticket, event) |
| judgment | Judgment-heavy, mixed agents, human sign-offs | Mostly automated, predictable |
| duration | Minutes to days per occurrence | Seconds; latency matters |
| audit_trail | Repo audit trail is a benefit | Needs live-system integration, uptime, scale |

## Verdicts and next steps

- `fits`: run it with an existing recipe, or author a recipe for it.
- `fits_per_occurrence`: each occurrence fits, but they recur; use a recipe plus an
  external scheduler that starts one run per occurrence.
- `operations_engine`: the idea is a system to build, not a process to run; start a
  `software-feature` run whose deliverable is that system, choosing the engine in its
  design step.
