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

## 8. One kind of work per stage

Split the process until each stage has one kind of work, one doer and one output that can be checked.
Stop splitting when a further split would change neither who does the work nor how it is checked.
Two stages that always run together, by the same doer, with one check, are one stage.

## 9. Interpret, then enforce

A stage that both reads open-ended material (a letter, a photo, what a client said) and applies rules
(a price list, a limit, a schedule) is two stages. First a person or an AI worker turns the material
into a structured proposal; then software or an automatic check validates the proposal against the
rules and acts on it. The rules then hold every time, and only the reading is a judgment.

## 10. The simplest means that can do the work

For each stage, record what its work is like (`traits`), and give it to the first doer on this list
that can do it:

1. **A program** (small software the process ships) when complete rules can be written for every input
   in scope and the input is structured: a calculation, a conversion, matching one list against
   another, keeping a record. It gives the same result every time, costs nothing per run and needs no
   AI service.
2. **An automatic check** when the stage only checks something mechanically.
3. **A person** when the work is in the physical world, needs authority, or is the owner's judgment.
4. **An AI worker** when the input is open-ended or the rules are partial: reading, writing,
   judging, researching.

Software before an AI worker. When an AI worker does a stage software could do (`rules: complete` and
`input: structured`, or `repeatable: required`), record why (`executor_choice`): the owner's ceiling
on software, the owner's own choice (with their words in the ledger), or the work is over the program
budget; what is given up (the same result every time, no cost per run, no dependence on an AI
service); and what the software would cost (building it, and looking after it). Existing software
the owner already has is not yet a doer: record it as a discovery and do the stage another way.

**The program budget.** A program has one entry command, reads its inputs and writes its outputs, keeps no
service running, holds no state beyond what it declares, fits one effort band, and can be tested from
worked examples. At `software: simple` it is also one file, uses only the Python standard library,
reaches no network and needs no secrets. Anything bigger is a separate software project: do the stage
another way and say so.

**Contract, examples, then code** (`software: engineered`). A program that needs real engineering (a real
data format, rules with exceptions, a package) is built in that order: the design gives its contract
(inputs, outputs, what it may touch, every package and why, why it is one program) and the examples the
owner should supply; the owner supplies them, or approves drafted ones; another worker builds the
program to them, and a reviewer from another vendor checks it against the contract. Examples the builder
invents prove nothing about what the owner means, so the owner's own are asked for first. Prefer a
simple program wherever one will do.

**The check says what it establishes** (`acceptance.kind`): `format` (the output has the right shape),
`rule` (it obeys stated rules), `source` (it matches a source) or `judgment` (a reviewer or the owner
judges it). A stage with an effect, or whose result can be wrong about the world, needs more than
`format`.

**A point of no return has the owner's decision before it, whoever does the stage** (shape 4). A
program that spends money or changes something others depend on runs only after the owner approves.

**Delegation.** The owner may one day let their own AI assistant act for them. For each stage a person
does and each owner decision, say whether that would be risky (`delegation`), and why in plain words:
it is risky when the effect cannot be undone, or when the owner accepts a risk or waives a check there.
