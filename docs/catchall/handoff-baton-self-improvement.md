# Handoff: Baton self-improvement (discussion only)

**For:** a fresh conversation with Rob about integrated self-improvement in Baton (repo `rowama/baton`).
**State:** discussion stage. Nothing is designed or implemented. Rob wants to keep thinking; the likely output is an **on-hold change doc** (`status: proposed`, marked on hold) in `docs/changes/`, like `2026-11-zero-friction-setup.md`.
**Out of scope here:** the framing-scope fix and its Claude Code prompt. Those continue in another conversation. Its only link to this topic: that change includes the Director silently recording `feedback confusing` when the owner is confused, which is the first piece of "capture" below.

## What prompted it

In the first real project (pure-water vending, Grok Bot as Director), the framing question confused the owner twice: "which parts to start work on now". Rob caught it because he built Baton. A real owner wouldn't think "fix the Director"; they'd just ask something like "I want my project to include all of those; do you mean which one to start on only?" Rob wants Baton to notice that kind of signal and improve itself, without it being in the owner's face.

## Rob's positions (stated)

- Baton should always watch for unexpected owner behavior: confusion, redirection, asking for clarification, chatting about the question instead of answering it.
- On detection, Baton should automatically try to improve the recipe, but tentatively. It must know it's experimenting, and adjustments must not be brittle.
- Idea: recipes could have git-like branches, merged into a trunk only on evidence of improvement. Rob is concerned that the very low number of occurrences makes evidence hard.
- Recipes should evolve **locally to match the owner**, at the terminal leaves (the user level), without spilling over to other owners. Proliferation at the leaves is fine.
- The **cases** themselves should be documented at the public repo level. An intelligent analyst looks for common or popular cases as candidates for the public recipe, raised as PRs against it.
- Eventually, public recipe owners may maintain recipes outside the Baton repo; Baton needs to know that repo to feed cases upstream.
- Rob isn't an expert here: "maybe trunk is bad wording, maybe this capability is imprudent or infeasible." He wants a frank view.

## Assessment so far (Claude's suggestions, not decided)

**Feasible and prudent, with guardrails.** It's the Linux-distribution pattern: each distribution carries its own patches on top of upstream and sends the general fixes back.

**Suggested terms** ("trunk" and "branch" would collide with git in the project repo):
- **Upstream:** a recipe as its owner publishes it (`fit-check@2`).
- **Local line:** this owner's evolved version: upstream plus accepted wording changes, recorded per run (e.g. `fit-check@2+local.3`).
- **Candidate:** a tentative change being tried.
- **Case:** one recorded incident (confusion, correction, redirection).

**Existing plumbing in Baton:**
- `process_feedback` events with kind `confusing` (among others), the process SME, lessons with confirmation counts, and proposals applied as new recipe versions (§12.4, `docs/design/experts.md`).
- Recipe versions are immutable and pinned per run.
- `baton simulate`, a dry run of a recipe, is foreseen in §15.3 (`docs/design/platform-and-security.md`).
- Hand-written bug evaluations (`docs/bug-evals/`) are effectively manual cases today.

**Suggested mechanism:**
1. **Detect.** The Director is the only part that sees the owner, so it's the sensor. It records a case silently: what was shown, the owner's words, and what produced the question (a worker output, a label, a skill rule).
2. **Candidates.** A small wording-only overlay (a prompt, a label, a skill rule) on the published version, used for new runs. Each run records which candidate it used.
3. **Evidence despite few occurrences.** Make each case a replayable test: replay it with the candidate, with a judge from a different vendor plus a simulated owner, and replay all earlier cases so nothing regresses. Real use then confirms: clean occurrences count up, and a recurrence rolls the candidate back automatically.
4. **Local lines.** Accepted candidates join the owner's local line. On an upstream upgrade, the local changes are replayed onto the new version and the owner's cases re-run against it: changes upstream made redundant are dropped, and conflicting ones become candidates again. "What has Baton adjusted for me?" gets a plain answer, with undo.
5. **Upstream cases.** `recipe.yaml` gets an `upstream:` entry naming where the recipe is maintained and where cases go (e.g. issues on its repo). Built-in recipes and the director skill point at `rowama/baton`. Cases are sent in a **shareable form**: the question's shape, the reaction type, the source, and the local fix, with subject matter stripped. Sharing is **opt-in**, chosen once (a natural fit for the setup flow), never automatic by default.
6. **Analyst.** A periodic job at the recipe's repo. It groups similar cases, weighs how many owners and versions they came from, replays candidate fixes against all of them, and opens PRs with the evidence for a human to review. It could itself be a Baton recipe.

**Hard boundaries:**
- Automatic changes touch wording only, never steps, gates, schemas or the runtime. This keeps "the Director never modifies a process" (§1.4 #10).
- Only one candidate per question at a time.
- Nothing upstream merges without human review.

**Risks:**
- A judge model is a noisy stand-in for people.
- Local lines can overfit to one person's taste, which is acceptable locally but is a reason upstream needs volume.
- A simulated owner misses things a real one wouldn't.
- Separating subject matter from the question's shape isn't fully automatic, so the owner should see the exact shareable text, at least at first.
- Incoming upstream cases are written by strangers, a prompt-injection route into the analyst. Treat them as data only.
- Upstream volume is low early on; until there's volume, a person reading the case list beats an analyst.

**Suggested build order:** capture → replay → local lines (with rebase on upgrade) → shareable cases with opt-in submission → analyst. The first two pay off even if nothing ever goes upstream.

## Open questions for Rob

- Is promotion into the local line automatic (all replayed cases pass plus N clean real uses), or always the maintainer's approval in a quiet digest? Rob's "local evolves to match the owner" leans automatic for local, with human review only upstream.
- Who sees and approves a case's shareable text before it leaves the machine, and how often?
- Does self-improvement also cover the director skill and communication style, which are vendored per project, or recipes only?
- What counts as a confusion signal strong enough to open a case? The Director's judgment alone, or also cheap runtime signals (a reject with a note, a retry right after a human gate, an owner question while a decision is pending)?

## How Rob works (for the next session)

- Rob is an experienced developer (EE/CS background) and prefers short, direct answers unless he asks for depth. He wants factual claims sourced, and guesses labeled as guesses.
- The Baton repo's `CLAUDE.md`: work is change-sized; every change starts as `docs/changes/YYYY-MM-<slug>.md` from `docs/changes/TEMPLATE.md` (statuses `proposed | accepted | in-progress | done | abandoned`; levels `minor | standard | major`). Owner decisions become records in `docs/decisions/NNNN-<slug>.md`. `docs/principles.md` is always read. Ask before pushing.
- Principle 5 (`docs/principles.md`): deterministic machinery, human conversation. The owner side is fuzzy and judged; anything recorded is structured and confirmed. Self-improvement must respect that split.
