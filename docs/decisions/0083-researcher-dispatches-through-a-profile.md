---
id: "0083"
title: "The maintainer researcher is one Baton dispatch through a profile the maintainer names"
status: accepted
date: 2026-11-06
source: "change 2026-11-worker-setup (owner, 2026-11-06)"
sections: ["§4.1", "§6.4"]
---

# 0083. The maintainer researcher is one Baton dispatch through a profile the maintainer names

## Context

0074 puts research in a maintainer-only utility under `tools/worker-research/`, but left open what runs the research agent. Options were: Baton's own dispatch through a profile; a prompt file the maintainer runs by hand in any agent; or deferring the researcher.

## Decision

`tools/worker-research/research.py --profile <name>` runs a one-step recipe (`worker-research`, in the same directory) in a scratch Baton project and dispatches it to the named profile from the maintainer's machine (it needs `web_access`, `file_write`, `structured_output`, `technical_reasoning`). The packet carries the current known-workers file, the adapters and the capability vocabulary; the worker returns the proposed file as an artifact and a coverage report as its output.

The script validates the proposal (`known_workers.validate`) and refuses one that adds, changes or removes a `verified` entry, since research is not a live check. A valid proposal replaces `defaults/known-workers.yaml` for review with `git diff`; the report goes to `tools/worker-research/reports/<date>.md`. A refused proposal leaves the repository file alone and is saved beside the report.

This reuses Baton's packets, adapters and environment isolation, privileges no vendor, and adds no dependency. Being under `tools/`, none of it ships.

Amended 2026-11-06 by the owner: the researcher is a command, `baton-worker-research`, installed like `baton` into `~/.local/bin`. It is its own package in `tools/worker-research/` (its own `pyproject.toml`, depending on Baton by path), installed from the checkout with `uv tool install --editable tools/worker-research`, so Baton's wheel still ships none of it and the command always runs the checkout's code and recipe. `--repo` defaults to that checkout, so it runs from any directory. The alternative, a second entry point in Baton's wheel, was declined: it would ship a maintainer tool to every user.
