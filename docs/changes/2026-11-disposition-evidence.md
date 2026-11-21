---
id: 2026-11-disposition-evidence
title: "A worker can cite its own new result as evidence for a fixed finding, and a claim that fails its check is dropped, not the result"
status: in-progress
level: standard
decisions: ["0183", "0181"]
touches: [design/gates-and-reviews.md, design/packets.md, design/runtime.md]
manual: "none: dispositions are worker and Director protocol; the owner sees only the step record, whose dropped-claim line explains itself"
---

# A worker can cite its own new result as evidence for a fixed finding, and a claim that fails its check is dropped, not the result

## Request

### Problem

The owner asked for a fix to `issues/2026-11-20-design-evidence-and-lost-answers.md`, filed from run `r_20261119_ee96` (recipe-builder, `shape/x5b12127/i2/design`).

1. **Evidence for `fixed`.** The design round marked 19 findings `fixed`, citing lines of the design document it had just written. Intake checked `fixed` `file:line` evidence at the HEAD commit, made before the attempt, not "in the current tree" as §9.2 says. An honest worker could not pass: it cannot commit, and Baton commits only after intake. Every claim was refused, the whole result was rejected, and the step retried with the same impossible check, at about 30 minutes of the owner's subscription each time. The packet text also left the `fixed` rule unclear.
2. **Lost round-one answers.** Round two's first attempt asked again three questions the owner had answered in round one. This was already fixed by `2026-11-first-use-feedback-batch-a`, Slice 4 (Decision 0181, item 2; commit `9100ac5`, 2026-11-20 04:36). That attempt's packet was built at 23:29 on 2026-11-19, before the fix. Round two's attempt 2 packet, built afterwards, lists `q_e14_lowest_checking`, `q_e18_reflection` and `q_e12_four_layers` under "The owner's earlier answers". No change is needed; `tests/test_lasting_answers.py` covers it.
3. **Secondary.** A contract failure the worker cannot fix retried without the owner. The owner chose to drop a failed claim and keep the result (0183) rather than escalate.

### Acceptance criteria

- A `fixed` disposition whose `file:line` points into the attempt's own uncommitted `result/` (or any uncommitted file) is accepted when the file has that line.
- `rejected` `file:line` evidence is still checked at the reviewed commit.
- A worker's claim that fails its check is dropped with its reasons (`result_submitted.dispositions_dropped`, shown in the step record), and the result goes on to its gates instead of being rejected.
- The packet's Dispositions section says where `fixed` evidence may point and that a failed claim is dropped.

## Design

### Doc edits

- `design/gates-and-reviews.md` §9.2: `fixed` evidence is the working tree, uncommitted files included; a worker's claim that fails its check is dropped and recorded; a Director's is still refused.
- `design/packets.md` §7.2: an invalid `dispositions` entry is dropped, not a rejection.
- `design/runtime.md` §8.10: intake step 2 records `dispositions_dropped`.

### Manual edits

- none: dispositions are worker and Director protocol; the owner sees them only in the step record, and the dropped-claim line there explains itself. The `disposition` command's rules are unchanged.

### Decisions

- 0183 (new): evidence in the working tree; a claim that fails its check is dropped, not the result; Director calls are still refused; retries are unchanged (0180).
- 0181 (existing, item 2): answers that last, which already fixes the report's second issue.

## Plan

### Evidence in the tree, failed claims dropped

- **Outcome:** a design round's honest `fixed` claims on its own new document pass, and a bad claim no longer costs the whole result.
- **Criteria:**
  - `tests/test_reviews.py::test_rejected_evidence_is_checked_at_the_reviewed_commit`: `fixed` and test references read the working tree; `rejected` `file:line` reads the reviewed commit.
  - `tests/test_reviews.py::test_a_design_round_cites_its_own_new_document_and_a_bad_claim_is_dropped`: the run of 2026-11-20 in miniature.
- **Effort:** S

## Log

### Evidence in the tree, failed claims dropped

- **Commit:** 2026-11-disposition-evidence: evidence in the tree, failed claims dropped
- **Summary:** `reviews.check_evidence` reads `fixed` `file:line` evidence and the files of test references from the working tree (its `head` argument is gone); `rejected` `file:line` keeps the reviewed commit. `engine._worker_dispositions` returns the claims that failed their check, with reasons, instead of problems; `submit` records them as `result_submitted.dispositions_dropped` and the result goes on. `docs.step_record` shows each as "Claim dropped". The packet's Dispositions section and the worker skill say a `fixed` `file:line` may point into the worker's own `result/` by its path from the project root, and that a failed claim is dropped. Design §7.2, §8.10 and §9.2 edited; decision 0183 recorded.
- **Tests:** the two tests above.
- **Review:** The held run `r_20261119_ee96` needs this Baton build to pass `shape/x5b12127/i2/design`: its attempt-2 result, retried, now passes the evidence check. Dropping also covers claims on findings not shown or ambiguous, the same reasoning applied to every check a claim can fail.
- **Accepted:** Fix requested by the owner, 2026-11-20; dropping a failed claim chosen by the owner in this session (0183).
