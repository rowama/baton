---
name: baton-worker
description: Do one Baton step from its packet — read the packet, do exactly the step, and write a valid result. Use whenever you are handed a Baton packet directory or an INSTRUCTIONS.md that names the baton-packet protocol.
---

# Baton Worker

You do one attempt of one step. Everything you need is in the packet; everything you return goes in the result directory.

## The packet (read only)
- `INSTRUCTIONS.md`: your role, the step's prompt, the output schema, prior feedback. Follow it exactly.
- `manifest.json`: `packet_sha256`, `inputs` (files under `inputs/`), `required_artifacts`, `optional_artifacts`, `exit_criteria`, `deadline`, `workspace`, `protected_paths`.
- `output_schema.json`: the JSON Schema your `output` must satisfy.
- Never modify anything under `packet/`.

## What the manifest means
- `exit_criteria`: what "done" means for this step. Stop when they are met; do not do more.
- `deadline`: the time you have. Iterate inside it (e.g. run tests until they pass), never past it.
- `workspace`: `none` — touch no project files; `read` — read the working tree, change nothing; `write` — change and commit in the working tree, and report the commit as `commit_sha` in `output`.
- `protected_paths`: never change files matching these globs, even in a write step.

## The result
Write to the result directory named in `INSTRUCTIONS.md`:
- `artifacts/<name>.<ext>` for each declared artifact (required ones must exist).
- `result.json` **last**: `protocol: "baton-packet/1"`, `packet_sha256` echoed from the manifest, `status` (`completed` | `blocked` | `failed`), `output` (valid against the schema), `artifacts` (`[{name, path}]`), `notes`, `questions_for_human`, optionally `process_feedback` and `dispositions`.
- `blocked`: you need an answer from the owner; put the questions in `questions_for_human`, each `{id, ask, why, best_guess?, options?: [{id, label}], multi_select?, priority?: needed | helpful}`. Write them in the owner's terms, never the process's or a rubric's vocabulary; infer what you reasonably can and offer it as `best_guess`; ask only what you cannot infer.
- `prior_feedback.answers` (in the manifest and `INSTRUCTIONS.md`): the owner's confirmed answers to your earlier questions, `{id, answer, owner_words}`. Use them as given.
- `dispositions`: only for findings you were shown — `fixed` or `rejected`, each with evidence (a commit or `file:line`; for `rejected`, `file:line` or `path::test`). Never `accepted-risk`.

## Rules
- Stop and report a mismatch (missing input, contradictory instructions, an impossible schema) as `blocked` or `failed` with the reason, instead of improvising.
- Report friction with the process in `process_feedback` (`{kind: friction | waste | confusing, text}`).
- Never contact people, push, tag, merge or deploy.
