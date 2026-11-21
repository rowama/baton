# Baton bug: shape design rounds cannot cite their own new artifact as evidence for `fixed` findings, and later rounds lose earlier owner answers

- Reported: 2026-11-20 (America/Chicago) by the Director for Rob Martin
- Baton: 0.1.0, recipe `recipe-builder@7`
- Run: `r_20261119_ee96` (Software recipe), step `shape/x5b12127/i2/design`
- Severity: blocking. Every shape loop that reaches a second design round after an audit with findings stops here.
- Status: build on hold at `shape/x5b12127/i2/design` by owner decision ("Add both to the Baton bug report and hold the build"). Owner's ten round-two answers are recorded (d138) and should carry over.
- Related, already fixed: `issues/2026-11-19-research-blocked-vs-schema.md`. Its secondary issue (a failed contract check auto-retries instead of escalating) appeared again here.

## Issue 1: `fixed` dispositions are checked against a commit where the evidence cannot exist

### What happened
1. `shape/x5b12127/i1/audit` (codex-gpt-6-1-terra) recorded 18 high findings (F01-F06, F11, F13, F16-F22, F25-F27) against the i1 design doc.
2. `shape/x5b12127/i2/design` attempt 2 (claude-code-claude-opus-5-5, dispatch `d_f6715750`, 1737 s, exit 0) wrote a new `result/artifacts/design_doc.md` and `result/result.json` with 19 dispositions, all `fixed`. Each cites a line in its own new design doc, for example:
   ```json
   {"step": "shape/x5b12127/i1/audit", "finding": "F01", "disposition": "fixed",
    "evidence": ".baton/runs/r_20261119_ee96/steps/shape/x5b12127/i2/design/attempt-2/result/artifacts/design_doc.md:271"}
   ```
3. The runtime rejected all 19 with the same reason, then set outcome `retry` and made the step ready again, with no pending owner decision:
   > dispositions[0] (fixed F01): .baton/runs/r_20261119_ee96/steps/shape/x5b12127/i2/design/attempt-2/result/artifacts/design_doc.md does not exist at commit 13b48b35a3ad

   Commit `13b48b3` is the "decision retry [attempt 1]" commit made *before* attempt 2 started. The attempt-2 result directory is still untracked at check time.

### Root cause: the contract contradicts itself
- Packet INSTRUCTIONS.md (attempt 2, lines ~419-424, "Dispositions") says: "`fixed` needs a commit SHA or `file:line`; `rejected` needs a `file:line` that exists at the reviewed commit, or a test reference `path::name`." As written, only `rejected` is tied to the reviewed commit.
- The runtime checks `fixed` evidence the same way, against the pre-attempt commit.
- In a design round the fix *is* the new artifact. The worker cannot commit (Baton owns commits), so it has no SHA to give, and any `file:line` in its own result cannot exist at the earlier commit. An honest worker has no way to satisfy the check. Retrying will fail again the same way and burn about 30 minutes of the owner's subscription each time.

### Expected
A `fixed` disposition whose `file:line` points into the current attempt's own `result/` is checked against the submitted result (file exists, line in range), or the check runs after Baton ingests and commits the result. `rejected` keeps the reviewed-commit rule.

### Suggested fixes (any one)
1. Resolve `fixed` evidence paths under the current attempt's `result/` against the working tree at ingestion, not the reviewed commit.
2. Commit the result first, then validate dispositions against that commit.
3. Allow an artifact-relative form (for example `artifact:design_doc.md:271`) and say so in the Dispositions section.
4. If evidence fails, downgrade the disposition to an unverified claim (the next audit confirms it anyway, per the packet text) instead of failing the whole attempt.

### Secondary (repeat of the earlier report)
A deterministic contract failure produced outcome `retry` with `needs_owner: false`. A failure the worker cannot fix by trying again should escalate to the owner instead of looping.

## Issue 2: design round 2 did not receive the owner's round 1 answers

### What happened
- `i1/design` attempt 1 asked three questions (`q_e14_lowest_checking`, `q_e18_reflection`, `q_e12_four_layers`). The owner answered (d101). The `i1/design` attempt 2 packet lists them ("you asked the owner (q_e14_...)", INSTRUCTIONS.md:182-184) and that attempt passed.
- The `i2/design` attempt 1 packet has no "you asked the owner" entries, and its inputs (`context`, `open_findings.json`, `patterns.md`, `profile.json`, `research.json`) carry no i1 answers. It asked ten questions, three of which re-ask the round-one choices under new ids: `q3_four_layers`, `q4_lowest_checking`, `q5_reflection`. The Director had to resubmit the owner's earlier words by hand.

### Root cause (likely)
Owner answers are attached only to later attempts of the same step path. A new iteration of a `repeat_until` loop gets a fresh step path (`.../i2/design`), so answers recorded on `.../i1/design` aren't carried forward.

### Expected
Decisions recorded on earlier iterations of the same loop step (and on earlier steps whose outputs feed this one) appear in the packet as settled owner answers, so the worker builds on them instead of asking again.

### Suggested fix
When building a packet for iteration N of a loop step, include the owner answers from iterations 1..N-1 of that step in the "you asked the owner" section, marked as already decided.

## Evidence locations (baton-recipes)
- Attempt-2 result: `.baton/runs/r_20261119_ee96/steps/shape/x5b12127/i2/design/attempt-2/result/`
- Attempt-2 packet: `.../i2/design/attempt-2/packet/INSTRUCTIONS.md`
- Dispatch output: `/tmp/ee96-design-i2b.json`. Log: `~/.baton/logs/r_20261119_ee96/shape/x5b12127/i2/design/attempt-2.log`
- Round-one answers: d101. Round-two answers: d138 (`/tmp/ee96-answers3.json`).
