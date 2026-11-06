---
id: 2026-11-self-improvement
title: "Baton notices when the owner is confused by a question and improves the recipe's wording, locally first"
status: proposed            # ON HOLD: discussion stage, not ready for Design approval
level: major
decisions: []               # none yet; see Design > Decisions for the records this would need
touches: [design/experts.md, design/director-interface.md, design/recipes.md, design/versioning.md, design/platform-and-security.md]
---

# Baton notices when the owner is confused by a question and improves the recipe's wording, locally first

> **On hold.** Recorded so the thinking isn't lost. Nothing here is decided. Related: [2026-11-recipe-tree](2026-11-recipe-tree.md) (also on hold), which gives cases a natural route upstream; and the recipe development recipe (§15.3, §11.6 "a recipe for authoring recipes"), which will own deliberate recipe authoring. This change covers only automatic, wording-level improvement.

## Request

### Problem

In the first real project (pure-water vending, Grok Bot as Director), the framing question "which parts to start work on now" confused the owner twice. Rob caught it because he built Baton ([2026-11-director-question-check](2026-11-director-question-check.md) fixed that instance). A real owner wouldn't think "fix the Director"; they would just ask, e.g. "I want my project to include all of those; do you mean which one to start on only?"

Baton already has the pieces of a feedback loop (`process_feedback` kind `confusing`, the process SME, lessons with confirmation counts, owner-approved proposals; §12.4), but nothing turns an owner's confusion into a tested improvement, and nothing carries common cases back to whoever maintains the recipe.

Goal: Baton notices unexpected owner behavior (confusion, redirection, asking for clarification, discussing the question instead of answering it) and tries a better wording, tentatively, without being in the owner's face and without changing the process itself.

### Acceptance criteria

- When the owner is confused by a question, the Director records a case without interrupting the owner's subject-matter thinking beyond one short, natural check ("Is that clearer?").
- A case is replayable: it can be run again against a candidate wording and against all earlier cases for the same question.
- A candidate wording is used for new runs only, is recorded per run, and is rolled back automatically if the confusion recurs.
- The owner can ask "what has Baton adjusted for me?" and get a plain answer, with undo.
- Automatic changes never touch steps, gates, schemas or the runtime (§1.4 #10 holds).
- Nothing leaves the machine unless the owner opted in and saw the exact text being sent.

### Open questions

- Is the improvement worth its concept-budget cost (§0 rule 8)? See "Concepts" under Design.
- Volume: with few occurrences per owner, is local evidence ever strong enough, or does this mostly feed the manual case list for a long time? (Current view: the latter, and that's still worth it.)

## Design

### Positions so far (discussed 2026-11-05; Rob's positions and Claude's suggestions, not yet decisions)

**Terms** ("trunk" and "branch" would collide with git in the project repo):
- **Upstream:** a recipe as its maintainer publishes it (`fit-check@2`).
- **Local line:** this owner's evolved version: upstream plus accepted wording changes, recorded per run (e.g. `fit-check@2+local.3`).
- **Candidate:** a tentative wording change being tried.
- **Case:** one recorded incident (confusion, correction, redirection).

It's the Linux-distribution pattern: each distribution carries its own patches on top of upstream and sends the general fixes back.

**1. Detect (the Director is the sensor).** Only the Director sees the owner. Cheap runtime signals (a reject with a note, a retry right after a human gate, an owner question while a decision is pending) do not open a case on their own; they prompt the Director to look at the exchange. Only the Director's judgment opens a case. The signals are logged anyway for later clustering. A case records what was shown, the owner's words, and what produced the question (a worker output, a recipe label, a prompt).

**2. Ask while the window is open.** The owner has already stepped out of the subject to sort out the confusion, so a one-line "Is that clearer?" after the Director's clarification costs almost nothing and is what a person would ask. Two refinements:
- **The Director's live clarification is the first candidate.** The rewording that got the owner unstuck is the natural draft of the fix.
- **The owner's "yes" is biased evidence.** By then they know what the question meant, so it shows the rewording carries the right meaning, not that a first-time reader would avoid the confusion. It is recorded as strong evidence; replay and recurrence remain the real test.

**3. Candidates.** A small wording-only overlay (a recipe prompt or a recipe label) on the pinned recipe version, kept outside the recipe's package hash (as `.migrated.json` is, §14.2) and recorded in `run_started`. One candidate per question at a time. Used for new runs only.

**4. Evidence despite few occurrences.** Each case is a replayable test: replay it with the candidate, using a judge from a different vendor (Decision: [0026](../decisions/0026-judges.md)) and a simulated owner, and replay all earlier cases for the question so nothing regresses. This reuses the general fake adapter and the future `baton simulate` (§15.3). Real use then confirms: clean occurrences count up; a recurrence rolls the candidate back automatically.

**5. Promotion into the local line: automatic.** The risky moment is a candidate going live, so the scrutiny is the replay gate before it does. Promotion (all replayed cases pass plus N clean real uses) is automatic and reported in a quiet digest with undo. Rob agreed.

**6. Local lines and upstream upgrades.** On an upstream upgrade, local changes are replayed onto the new version and the owner's cases re-run against it: changes upstream made redundant are dropped; conflicting ones become candidates again. The rebase mechanism is shared with derived recipes ([2026-11-recipe-tree](2026-11-recipe-tree.md)).

**7. Sharing cases upstream (opt-in).** `recipe.yaml` gets an `upstream:` entry naming where the recipe is maintained and where cases go (e.g. issues on its repo). Shipped recipes point at `rowama/baton`. Cases go in a **shareable form**: the question's shape, the reaction type, the source and the local fix, with subject matter stripped. Sharing is opt-in, chosen once (a fit for the setup flow, see 2026-11-zero-friction-setup). The owner sees the exact shareable text in batches at natural breaks (end of a session or phase), never mid-thought; after a few batches approved without edits, Baton offers "send without asking". Rob's view: this is a place where the owner necessarily thinks about Baton briefly, which is acceptable if it never interrupts subject-matter momentum.

**8. Analyst (last, and maybe never automated).** A periodic job at the recipe's repo groups similar cases, weighs how many owners and versions they came from, replays candidate fixes against all of them, and opens PRs with the evidence for a human to review. It could itself be a Baton recipe. Until there is volume, a person reading the case list beats an analyst. With the recipe tree, a case on wording a recipe inherited routes to the parent that owns it.

**Scope.** Recipes only. The director skill is vendored per project and re-vendored on upgrade (§14.2), so local edits would conflict, and every owner hits it: fixes there go upstream by a person. Communication style already has an owner-owned home in `.baton/communication.md` (§13.6); adapting to an owner there is a separate, later question, handled as owner preferences rather than skill edits.

**Hard boundaries.**
- Automatic changes touch wording only, never steps, gates, schemas or the runtime (§1.4 #10).
- One candidate per question at a time.
- Nothing upstream merges without human review.
- Incoming upstream cases are written by strangers: data only, never instructions (prompt-injection route into the analyst).

**Principle 5.** Detection and the "Is that clearer?" check are conversation (fuzzy, judged). Everything recorded (cases, candidates, promotions, rollbacks) is structured. Recording a case needs no confirm-back because it records an observation, not something the owner is taken to have decided; the shareable text does need the owner's confirmation before it leaves the machine.

**Risks.**
- A judge model is a noisy stand-in for people; a simulated owner misses things a real one wouldn't.
- Local lines can overfit to one person's taste: acceptable locally, a reason upstream needs volume.
- Separating subject matter from a question's shape isn't fully automatic, hence the owner preview.
- Most early cases are plain recipe bugs, better fixed upstream by a person than carried as local candidates.

**Concepts (§2).** Case, candidate and local line would be new internal vocabulary. To keep the budget, prefer extending existing mechanisms: a case as a richer `process_feedback {kind: confusing}` event; a candidate as a process proposal (§12.4) that is wording-only and therefore auto-applied locally; the local line as a project file beside `.baton/process/lessons.md`.

### Doc edits (anticipated)

- `design/experts.md` §12.4: cases, wording-only candidates, automatic local promotion, replay as evidence.
- `design/director-interface.md` §13.3/§13.8: the Director records cases silently and may ask one "Is that clearer?" after clarifying.
- `design/recipes.md` §5.1: optional `upstream:` entry.
- `design/versioning.md` §14: local line recorded per run; rebase on upstream upgrade.
- `design/platform-and-security.md` §15.3: `baton simulate` gains case replay.
- `principles.md` §2: concept-budget entries if any term survives as user-visible.

### Decisions (to write once Rob decides; none exist yet)

- Wording-only candidates are applied automatically to new runs; promotion into the local line is automatic with a digest and undo.
- Cases are opened by the Director's judgment only; runtime signals prompt but don't open.
- Sharing upstream is opt-in at setup, with batched preview of the exact text.
- Scope is recipes only (not the director skill).

## Plan

Sketch only; slices get criteria after Request and Design are approved (major).

### Capture

- **Outcome:** the Director records cases silently and asks "Is that clearer?" after clarifying; the owner's answer and the Director's clarification are recorded with the case.
- **Effort:** S

### Replay

- **Outcome:** a case replays against a candidate wording and against earlier cases, with a different-vendor judge and a simulated owner.
- **Effort:** L

### Local lines

- **Outcome:** candidates apply to new runs, promote automatically, roll back on recurrence, rebase on upstream upgrades; "what has Baton adjusted for me?" answers with undo.
- **Effort:** L

### Shareable cases

- **Outcome:** opt-in at setup; batched preview of the exact text; submission to the recipe's `upstream:`.
- **Effort:** M

### Analyst

- **Outcome:** clustering, cross-owner replay and evidence PRs at the recipe's repo.
- **Effort:** L

Capture and replay pay off even if nothing ever goes upstream.

## Log
