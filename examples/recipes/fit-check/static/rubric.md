# Fit rubric

Score the work being asked for, row by row. The profile's `scope` says what that work is:
developing a process (its design, build, tests and documents), executing one, or other work.
Developing, testing, documenting or improving a business process is eligible work however the
finished process will run; what it will do later is not a fact about the work. Judge the work's
own facts. Each row leans one way, and the verdict follows the balance. Frequency and duration
are signals, never standalone cutoffs.

| Row | Leans Baton | Leans against Baton |
|---|---|---|
| coordination | Several workers or people, handoffs, sign-offs, work that must stay consistent across steps | One worker, one short step, nothing to hand off |
| dependent_reasoning | Later work depends on earlier reasoning that should be checked | Little reasoning, or each piece independent |
| recurrence | Each occurrence is substantial and benefits from its own run | Occurrences so many, or so small, that a run for each costs more than it returns |
| duration | Minutes to days of work | Seconds, where latency matters |
| record | A repository record of decisions and results is a benefit | Needs live-system integration, uptime or bulk data processing that a run cannot supply |

For work to be executed, `recurrence` and `record` weigh heavily: running Baton for each event of a
high-volume process does not fit, and an external scheduler that starts runs does not change that.
For work of developing a process, judge the development effort (its design, checks and
deliverables), never the volume, speed or uptime of the process it produces.

## Verdicts and next steps

- `fits`: run the work with an existing recipe that covers all of it, or, when none does,
  author a recipe for it (`recipe-builder`). Missing recipe coverage is not a reason to
  recommend against Baton; neither is a deliverable the shipped recipes do not produce.
- `fits_per_occurrence`: each occurrence fits and is substantial, but they recur; use a recipe
  plus an external scheduler that starts one run per occurrence. Not for work whose
  occurrences are so many or so small that each does not warrant a run.
- `not_recommended`: Baton's coordination would cost more than it returns for this work.
  Suggest what would suit it better (a script, asking an assistant directly, an existing tool, a
  manual procedure, or an operations engine). When the work asked for was executing a process,
  developing a suitable process or system may be offered as a separate project; it is not started
  by accepting this verdict.
