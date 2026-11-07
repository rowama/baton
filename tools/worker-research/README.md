# Worker research (maintainers only)

Proposes updates to `defaults/known-workers.yaml` (§6.4, Decisions 0074, 0080,
0083). Its own package, so Baton's wheel never ships it.

Install from the checkout, beside `baton` in `~/.local/bin`:

```
uv tool install --editable tools/worker-research
```

The install is editable, so the command always runs this checkout's Baton and
recipe; reinstall only when `pyproject.toml` changes. Then, from anywhere:

```
baton-worker-research --profile <name> [--home ~/.baton] [--repo DIR] [--reports DIR]
```

It runs the one-step `worker-research` recipe in a scratch Baton project,
dispatching to the profile you name from your own machine (it needs
`web_access`, `file_write`, `structured_output` and `technical_reasoning`).
The proposal is validated; a valid one replaces `defaults/known-workers.yaml`
in the checkout it was installed from (or `--repo`), and the report goes to
`tools/worker-research/reports/<date>.md` there. Review both with `git diff`
before committing. An invalid proposal, or one that adds or changes a
`verified` entry, writes nothing to the repository and is saved beside the
report for inspection.

Exit codes: 0 written, 1 refused or the worker failed, 2 usage.
