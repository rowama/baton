# Assess complexity

Rate this change on the recipe's scale. Size it; do not plan, design or start it.

The change, in the requester's words, is in the `feature_request` input. When the project
is being adopted from work already under way, the `research` input lists what already exists
for it; take that into account (work already done does not make a change smaller).

## Levels

Pick the **lowest** level whose description fits. When in doubt between two, pick the higher
one and say why.

| Level | Typical change | What the process adds |
|---|---|---|
| `minor` | A bug fix, a small increment, a configuration or copy change. One coherent change, one sitting; no new module, interface or data format. | One implementation, an independent code review, the owner's acceptance. |
| `standard` | A feature that touches several files or modules and is worth splitting into vertical slices, with behaviour the requester should confirm. | Written requirements and a reviewed, owner-approved plan of slices, each implemented, reviewed and accepted. |
| `major` | A new subsystem, a public interface or data format others depend on, a migration, security- or money-sensitive behaviour, or anything hard to undo. | Owner-approved requirements, a technical design with an independent review, then the standard plan and slices. |

Signals for `major`: changes a stored format or a public API; needs a migration or a
rollout plan; touches authentication, authorization, payments or personal data; several
teams or services are involved.

## Output

Return `level` (one of `minor`, `standard`, `major`) and `reasons`: one short line per
signal or level description that decided it, quoting the request where you can.
