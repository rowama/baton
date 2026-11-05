## 9. Gates and Reviews

### 9.1 Gate types

| Type | Behaviour | Passes when |
|---|---|---|
| `schema` | Recorded at intake | Output valid |
| `script` | Runs a command (`cwd`, `timeout_s`) under a clean env; output redacted into CAS | Exit 0 |
| `review` | The runtime readies a **review step** `<step_path>~review` and the step waits in `verifying`. The Director picks a reviewer from `eligible` (`reviewer_requires`, `independence`) and dispatches it like any step; its packet holds the step's inputs, the result under review and the rubric (§7.1); it returns `baton:findings`. A rejected reviewer result is retried as the review's own attempt; abandoning an escalated review fails this gate | No finding at a `block_on` severity is open (§9.2) |
| `findings` | For a step whose own output is findings (e.g. a code-review step). Records `findings_recorded` | Same rule |
| `human` | Step waits in `awaiting_human`; the Director records the owner's decision | Approved |
| `provenance` | Implicit: every referenced artifact was registered through intake | Always enforced |
| `workspace` | Implicit on `read` and `none` steps done by a worker that can touch files (§6.3) | The working tree is unchanged; otherwise the step escalates (`workspace_modified`) |
| `protected` | Implicit on steps with `protect` (§9.4) | No change; in `warn` mode, the owner approves the change |

Common options: `advisory: true` (records, never blocks); `applies_to: [levels]`; any blocking `script`, `review`, `findings`, `independence` or `protected` occurrence can be waived (§9.3). Gate reasons and open findings become `prior_feedback` on retry or `group.previous_iteration.findings` in a loop.

### 9.2 Findings and dispositions

Runtime-owned findings schema (`baton:findings`); reviewers must return it, so nothing is parsed from prose:

```json
{
  "findings": [ {"id": "F1", "severity": "high", "location": "src/auth.py:42", "title": "…", "detail": "…", "suggested_fix": "…"} ],
  "coverage": {"complete": true, "notes": ""}
}
```

Severities: `critical | high | medium | low`. `coverage.complete: false` (e.g. a reviewer that could not run socket tests) marks the result "partial" in every record.

**Lines and ids.** The repeated evaluations of one review form a *line*: `<step_path>#<gate>` at top level, `<instance path>/<step id>#<gate>` inside a group (the same across iterations). A finding is its line plus the id the reviewer gave it; each reviewer gets the previous evaluation with its dispositions (`prior_findings`, §7.1) and reuses the id of a finding it still sees.

**Statuses.** At each evaluation a reported finding is `open`, except one the owner accepted as a risk at the previous evaluation, which stays `accepted-risk` while it is reported again. A previous finding the new review does not report is `resolved` (a `fixed` or `rejected` claim on it is thereby *confirmed*). A disposition takes effect only at the next evaluation (Decision: [0035](../decisions/0035-dispositions-next-evaluation.md)): nothing waits for dispositions, a failed gate retries or ends the iteration at once, and accepting the current failure as is takes a waiver (§9.3). Only the latest evaluation of a line can be dispositioned.

| Disposition | Requirement |
|---|---|
| `fixed` | A commit that exists, or a `file:line` in the current tree; confirmed by the next review not reporting it |
| `rejected` | A `file:line` that exists at the reviewed commit (the git HEAD recorded when the review was dispatched; the working tree outside git), or a test reference `path::name` whose file exists now and contains the name |
| `accepted-risk` | An owner decision id: `decide <step_path>#<finding> accept-risk --note "<owner's words>"` records the decision and the disposition; `disposition … accepted-risk --evidence <decision id>` cites it. Nobody else can set it |

Set by a worker (in `result.json`, §7.2) or by the Director relaying evidence (`disposition`). A Director's `fixed`/`rejected` closes the finding in the record until a later review reports it again.

**Worker dispositions are provisional** (§18 #12). A worker may set `fixed` or `rejected` in its result with evidence, and intake checks that the evidence exists. That alone never closes a finding: an independent review must confirm it. If the next review re-reports the same finding id, the finding is open again, whatever the worker said. A worker disposition with no later review to confirm it does not close the finding; only the Director (relaying evidence) or the owner can close it there. A worker and a reviewer who keep disagreeing are settled only by the owner, with `accepted-risk` or a waiver; in a loop, the iteration limit escalates the disagreement. A disposition never makes a finding unconditionally closed on a worker's word alone. Mediating disputes is deliberately not built (§18 #18).

Per reviewer profile and qualified step (`<recipe_id>@<version>/<step_path>`, §5.8), the runtime keeps counts by severity and disposition, plus iterations to clean. These feed the process SME and never block. (Everything they need is in `findings_recorded` and `finding_dispositioned`; the statistics are derived on demand for the process SME, §12.4.)

### 9.3 Waivers

`waive(run, step_path, gate, reason)` needs an owner decision and covers one gate occurrence only (e.g. grandfathering a step approved before a gate existed, or allowing one self-review). It never changes the recipe; waivers show in every dependent record.

Decision: [0036](../decisions/0036-waivers.md).
- **Naming.** `gate` is a declared gate's index, its type when the step declares exactly one of that type, `independence` (the step's own; a review gate's reviewer independence is waived on the review step `<step>~review`) or `protected`. Waivable: `script`, `review` and `findings` gates, `independence`, `protected`. Human gates are decided, not waived; schema failures are rejections.
- **Decision.** As with `revise`, the runtime requires the reason, recorded verbatim as a `human_decision` (`kind: waiver`) followed by `gate_waived`; the director skill requires the owner's approval first.
- **Which occurrence.** The failed occurrence the step still holds, if any (`scope: held`): an escalated step whose last attempt failed this gate (`attempts_exhausted`) resumes verification of that attempt with its later gates; a judge at its iteration limit counts as passed and the iteration goes on (refused when later blocking gates of that judge never ran). Otherwise the next occurrence (`scope: next`): consumed by the next evaluation of that gate whatever its outcome (a would-be failure is recorded as `gate_passed` with `waived` and the reasons; a pass with `waiver_unused`), or for `independence` by the next dispatch of the step, whichever worker is chosen. One pending waiver per step path and gate.

### 9.4 Protected files

`protect: [globs]` (warn) or `protect: {paths: [globs], on_violation: warn | fail}` (default `warn`). Globs use `*`, `?` and `**`, relative to the project root. The runtime hashes matching files (outside `.git` and `.baton`) when the attempt is dispatched (recorded in `dispatched`) and again at intake. A change records `protected_path_modified`. In `warn` mode the step waits on the owner like a human gate (Decision: [0037](../decisions/0037-protected-warn-waits-on-owner.md)): `approve` keeps the change and the step goes on; `reject` fails the gate (the owner or the next attempt reverts it). In `fail` mode the gate fails. A pending `protected` waiver lets one change through. *Deferred:* an approval gate that records the protected hash set at approval time (e.g. locked acceptance specs) for later steps to preserve.
