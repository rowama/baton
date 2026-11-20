# Baton bug: recipe-builder@7 research step cannot return an owner question (blocked) because its output schema demands the choice already be decided

- Reported: 2026-11-19 (America/Chicago) by the Director for Rob Martin
- Baton: 0.1.0, recipe `recipe-builder@7`
- Run: `r_20261119_ee96` (Software recipe), step `research`, attempts 2 and 3
- Severity: blocking. Every run whose profile produces a `before_design` discovery record stops at research. By design (profile.md:134, recipe.yaml:78) that covers every standard or complex run that has a process-shaping choice.
- Status: build on hold at `research` by owner decision ("Write it up as a Baton bug and hold the build").

## What happened
1. `profile` (attempt 2, claude-code-claude-opus-5-5) passed and was approved: approach complex, software simple. It emitted discovery record **D1** with `timing: before_design`, `status: to_research`, `target_status: preference`. The question is which practices from the sources-and-lessons ledger, the eng-process kit and current practice to adopt, adapt or reject.
2. `research` attempt 1 (claude-code-research) failed on a platform issue: the Claude Code weekly usage limit (HTTP 429, `usage_limit_reached`). That one is unrelated to this bug.
3. `research` attempts 2 and 3 (codex-gpt-6-1-terra) each returned `failed` after about 30 to 40 seconds with the same reason, quoted from attempt 3:
   > D1 is an unanswered before_design choice. The instructions require researching it and asking the owner, without confirming an unanswered decision, while the output schema requires every before_design record to be decided with a decision and comparison. ... this output cannot validate against the schema; changing D1 or fabricating an owner decision would violate the packet.
4. The runtime treated both as `retry` with no pending owner decision, so retrying loops forever.

## Root cause: the contract contradicts itself
- `prompts/research.md` lines 44-50 (packet INSTRUCTIONS.md §2) say: "The choice is the owner's. A recommendation is not a decision. Return `blocked` with one structured question per choice ... When the owner's answers arrive, set the record's `status` to `decided` ... Never confirm an entry the owner has not answered."
- Packet INSTRUCTIONS.md line 115 says, with no exception for `blocked`: "`output` validates against output_schema.json."
- `schemas/discovery.json` lines ~250-275 (pulled into `research_out.json`) say: `if timing == before_design then status const "decided" and require comparison and decision`. The same rule appears in `design_out.json:1046-1056`, `ledger_file.json:344-354` and `profile_out.json:513`.

So the first research pass can never produce a valid output. An honest worker can't mark D1 decided before the owner answers, can't drop it, and can't change its timing without a reason. It also can't return `blocked` with an output that fails the schema. Codex chose `failed`, which is the correct conservative behavior. A more permissive model might invent a decision, which is worse.

## Expected
The first research pass returns `blocked` with `questions_for_human` (one per before_design choice, with best_guess and options), and its output validates with D1 as `status: researched` plus a filled `comparison`. After `baton decide research retry --answers ...`, the second pass sets `decided` with a confirmed ledger entry.

## Suggested fixes (pick one)
1. **Narrowest:** loosen the `research_out` (discovery) rule so a before_design record must be `researched` or `decided` and must have `comparison`, with `decision` required only when status is `decided`. Keep the strict "must be decided" rule in `design_out.json`, where it belongs.
2. Have the runtime skip `output_schema` validation, or validate against a partial schema, when the result `status` is `blocked`, and say so explicitly in INSTRUCTIONS.md's result section.
3. At minimum, state the exception in research.md/INSTRUCTIONS.md so workers know a blocked result's output is exempt.

## Secondary issue
When a worker reports `failed` because of a packet contradiction, the runtime offers an automatic `retry` and no owner or Director escalation. A contract mismatch should escalate (like `unknown` failures do) instead of inviting identical retries.

## Evidence on Merkle (WSL)
- `/mnt/d/rob/projects/baton-recipes/.baton/runs/r_20261119_ee96/steps/research/attempt-2/` and `attempt-3/` (packet and result)
- `/home/rob/.baton/logs/r_20261119_ee96/research/attempt-{1,2,3}.log`
- `/tmp/ee96-research2.json`, `/tmp/ee96-research3.json` (dispatch JSON)
- Profile output with D1: `.baton/runs/r_20261119_ee96/steps/profile/attempt-2/result/result.json` (~line 66)
