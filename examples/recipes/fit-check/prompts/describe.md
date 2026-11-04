# Profile the idea

You are profiling an idea so it can be scored for fit. Keep this to a few minutes.

The idea, in the owner's words, is in the `idea` input.

Focus on **one occurrence** of the idea: one instance of the work it describes.
Establish, for one occurrence:

1. **Frequency:** how often an occurrence happens.
2. **Judgment:** how much judgment it needs (`low`, `medium`, `high`).
3. **Duration:** how long it takes end to end.
4. **Participants:** which agents and people are involved, and whether people sign off.
5. **Audit trail:** whether a record kept in a repository would be a benefit, neutral, or a burden.
6. **Latency and integration:** whether seconds matter, and whether it needs live-system integration, uptime or scale.

## Infer first

Fill the profile from the idea as far as you reasonably can. Each value you inferred
rather than read goes under `assumptions` as `{field, value, basis}`, with the basis in
the owner's terms, so it can be confirmed with the owner instead of asked from scratch.
List anything you still cannot pin down under `unknowns`.

## Ask only what you cannot infer

If something you need cannot be inferred, set `status` to `blocked` and ask through
`questions_for_human`. Each question is an object:
`{id, ask, why, best_guess?, options?: [{id, label}], multi_select?, priority?}`.

- **Use the owner's terms, never these.** "Occurrence", "audit trail", "live integration",
  "judgment" and "latency" are this rubric's words, not the owner's. Ask about what one
  occurrence *is* in their world: for a water-vending idea, opening a site or serving a
  customer; for a hiring idea, filling one role. Never "which piece of work is one occurrence?".
- Say `why` it matters in one plain sentence, offer a `best_guess` when you have one, and
  give `options` when the answer is a choice.
- Mark a question `needed` only when the profile cannot be completed without it;
  otherwise `helpful`.

## Several kinds of work

An idea may hold several kinds of work: setting up a business *and* running it,
building a product *and* selling it. Do not force them into one profile. Instead set
`status` to `blocked` with **one** question whose `options` are the parts (one option
each, in the owner's terms), `multi_select: true`, and explain in `why` that each part
would be looked at separately. The Director will suggest breaking the goal down first.
