## 17. Testing Strategy

- **Unit:** loader and lint, vocabulary, routing and independence, hashing, the state machine, groups, gates and findings, env and PATH construction, classification rules, permissions, publishing and drift.
- **Property-based** (`hypothesis`): packet determinism; required-input removal; any legal event sequence rebuilds to the same state; `foreach` re-expansion is stable for unchanged items.
- **Fake adapter:** scripted good, bad-schema, wrong-hash, blocked, findings, timeout, crash, hang and exit-127 results.
- **Process control:** detachment, process-tree termination and marker liveness on POSIX and Windows.
- **Secret leak:** sentinel secrets through a full run; absent from the working tree and git history.
- **Golden files:** `INSTRUCTIONS.md`, records, summary, `explain` output.
- **Conversation review** (opt-in, with live tests): transcripts of a real Director with a scripted owner, reviewed by the owner against §13.8 *Review*. Not a pass/fail gate in CI: phrasing is judged, not enforced.
- **Live tests** (opt-in): real API models and harness CLIs.

## 19. Definition of Done

- All phases' acceptance criteria pass, on Linux and native Windows.
- README covers:
  - installing the launcher and `baton init`;
  - writing worker profiles;
  - `doctor` and `check`;
  - authoring a neutral recipe (including groups, complexity levels and reviews);
  - vendoring a recipe;
  - adopting an existing project;
  - framing a goal into work items, and choosing the conversational or operator communication style;
  - resuming on a new machine;
  - trialing a new version on a branch.
- Three example recipes ship (§5.7): `fit-check`, `software-feature` (software) and `backyard-project` (non-software).
- Swapping the Director harness or any worker needs only machine-local configuration. New recipes need no runtime changes.
- Principle checks, demonstrated in Phase 16:
  - after setup, a healthy project produces no routine owner prompts;
  - adoption needs exactly one owner decision;
  - every owner touchpoint is a recipe gate, an escalation, the baseline or a framing selection;
  - an owner unfamiliar with Baton can frame a goal and answer a step's questions without meeting Baton's vocabulary, and every answer recorded was confirmed back (Phase 17).
