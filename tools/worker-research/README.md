# Worker research (maintainers only)

Proposes updates to `defaults/known-workers.yaml` (§6.4, Decisions 0074, 0080,
0083). Not part of the installed runtime: `tools/` is outside the wheel.

```
python tools/worker-research/research.py --profile <name> [--home ~/.baton]
```

It runs the one-step `worker-research` recipe in a scratch Baton project,
dispatching to the profile you name from your own machine (it needs
`web_access`, `file_write`, `structured_output` and `technical_reasoning`).
The proposal is validated; a valid one replaces `defaults/known-workers.yaml`
and the report goes to `tools/worker-research/reports/<date>.md`. Review both
with `git diff` before committing. An invalid proposal, or one that adds or
changes a `verified` entry, writes nothing to the repository and is saved
beside the report for inspection.
