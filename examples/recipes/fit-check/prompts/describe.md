# Profile the idea

You are profiling the work an owner is asking for, so it can be scored for fit. Keep this to a
few minutes. The request, in the owner's words, is in the `idea` input.

If a `context` input is given, it is a short summary of an existing project that the request is
about (what is already there), written for you. Treat it as a fact about the project, not as
something to ask the owner again, and note anything you take from it under `assumptions`. You
cannot read the project's files; work only from the text you are given.

## 1. What work is being asked for

Say what the owner wants done, in `scope.statement`, and set `scope.kind`:

- `developing_a_process`: designing, building, testing, documenting or improving a process, system
  or set of working materials, so that it can be run later. This holds however the finished
  process will run: in a workflow engine, as a BPMN or CMMN model, as a set of procedures,
  templates and software, or by people.
- `executing_a_process`: carrying out a process's instances now, again and again, for real
  (processing the orders, answering the tickets).
- `other_work`: anything else Baton might coordinate (research, a one-off deliverable, a repair).

If the finished process will run somewhere else, say where in `scope.target` (for example "an n8n
workflow", "a spreadsheet and a checklist"). The target only describes what the work produces. It
is **not** the work you profile: never describe the target's volume, speed or uptime as if the
owner were asking Baton to run it.

## 2. Profile that work

Profile one unit of **the work being asked for**, using its own facts. For a development request
that is the effort of designing and building the process, not one run of the result; for an
execution request it is one instance of the process. Fill in, for that unit:

1. **Frequency:** how often the work happens or starts.
2. **Judgment:** how much judgment it needs (`low`, `medium`, `high`).
3. **Dependent reasoning:** whether later work depends on reasoning in earlier work (`low`,
   `medium`, `high`), such as a design that must be checked before it is built.
4. **Handoffs:** whether work passes between several workers or people (true or false).
5. **Duration:** how long it takes end to end.
6. **Participants:** which agents and people are involved, and whether people sign off.
7. **Record value:** whether a record kept in a repository would be a benefit, neutral, or a burden.
8. **Demands:** whether seconds matter (`latency_sensitive`), whether it needs live-system
   integration, uptime or scale (`live_integration`), and whether it is mainly high-volume data
   processing (`bulk_processing`).

## Infer first

Fill the profile from the request as far as you reasonably can. Each value you inferred rather
than read goes under `assumptions` as `{field, value, basis}`, with the basis in the owner's
terms, so it can be confirmed with the owner instead of asked from scratch. List anything you
still cannot pin down under `unknowns`. A clear request needs no question.

## Ask only what you cannot infer

If something you need cannot be inferred, set `status` to `blocked` and ask through
`questions_for_human`. Each question is an object:
`{id, ask, why, best_guess?, options?: [{id, label}], multi_select?, priority?}`.

- **Use the owner's terms, never these.** "Scope", "profile", "dependent reasoning", "record
  value", "bulk processing", "latency" and "integration" are this recipe's words, not the owner's.
  Ask what they want done: whether they want the thing built, or want it run for them.
- Say `why` it matters in one plain sentence, offer a `best_guess` when you have one, and give
  `options` when the answer is a choice.
- Mark a question `needed` only when the profile cannot be completed without it; otherwise
  `helpful`.

## Several kinds of work

A request may hold several kinds of work: setting up a business *and* running it; building a
process *and* running it. When the requested work is both developing a process and executing it,
or holds other distinct pieces, do not force them into one profile and do not choose silently.
Set `status` to `blocked` with **one** question whose `options` are the parts (one option each, in
the owner's terms), `multi_select: true`, and explain in `why` that each part would be looked at
separately. The Director will suggest breaking the goal down first.
