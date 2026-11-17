# Reusable process shapes

Use these shapes when designing a process. A departure is allowed when `summary` says where and why.

## 1. Research, options, decide, plan, execute, review

For work where the right approach is not obvious. Learn how the work is usually done; set out two or
three options with what each costs; the owner (or the role that owns the decision) decides; plan the
work in pieces that can each be checked; do each piece; have a different worker review the result
against what was decided.

### Discovering implementation options

Where the owner may not know how the work could be done (existing software, frameworks, standards, a
set of procedures and training, custom work), the shape needs this stage in front of the choice:

- A choice that changes the stages, workers, deliverables or checks is researched *while the process is being
  designed*, and the owner settles it before the stages it affects are fixed.
- A choice one process shape already accommodates becomes stages in the process: research the options
  for the job (a worker that can read current sources), the owner decides, and the stages that use the
  decision take it as an input. Nothing dependent starts before it.
- The research compares a proportionate shortlist against criteria from the requirements, with sources
  and the date each was read, tradeoffs, what was left out and why, what is uncertain, and a recommendation.
  A recommendation is never the owner's decision.
- Settled or simple work gets no comparison.

## 2. Make, then check independently

Whoever makes something does not check it. A check is another worker, or an automatic check, with a
stated pass condition. Block on serious findings; let minor ones through with a note.

## 3. A bounded improve loop

When a check can send work back, say how many times (three is a good default), what the maker is
given each time (the findings, and the owner's note if any), and what happens at the limit: the owner
decides whether to try again, accept the risk, or stop. Never loop without a limit.

## 4. One owner decision at each point of no return

Before a step that spends money, changes something others depend on, or cannot be undone, the owner
approves. Approvals ask a plain question with plain answers; saying no goes back to the stage that
can change the answer.

## 5. Failure dispositions

Every stage that can fail has one of these, chosen in advance:

| Disposition | Use when |
|---|---|
| retry | The failure is likely to be a one-off (a check was flaky, a worker ran out of time) |
| revise | An earlier stage's output was wrong; return to it with what was learned |
| escalate | Only the owner can resolve it (a missing decision, a worker that cannot do the work) |
| stop | Continuing would do harm |
| accepted risk | The owner knowingly goes on; record their words |

## 6. Inputs from the job, not the process

A process works on many jobs. What differs between jobs (sizes, names, dates, sites) is supplied
when a job starts, never written into the process itself.

## 7. Splitting a large idea

When an idea holds independent parts with different end states, people or schedules, build one
process per part and let each hand its result to the next as a document the next one reads. A part
that is ongoing operations becomes a process that produces the operating material (procedures,
templates, communication plans, and software where needed) when the owner asked for a process to
be made; do not change what the owner asked for from running the work to making a process for it.
The material may be meant to run elsewhere (a workflow tool, a diagram, a checklist).
