---
id: "0158"
title: "Tool steps: uv never downloads a Python, and a tool runs in a fresh scratch folder"
status: accepted
date: 2026-11-16
source: "Owner, 2026-11-16: chose \"No download\" and \"Fresh scratch folder\", and approved the Request and Design of 2026-11-tool-steps."
sections: ["§6.3", "§15.2"]
---

# 0158. Tool steps: uv never downloads a Python, and a tool runs in a fresh scratch folder

## Context

Checking the `2026-11-tool-steps` Design before approval confirmed the [VERIFY] in Decision [0156](0156-tool-steps-details.md) against uv 0.13.7 (`uv pip compile --generate-hashes`, `uv venv --python`, `uv pip install --require-hashes`) and raised two questions the Design left open. uv fetches a managed Python on its own when none matches, and the Design ran a tool with its own folder as the working directory, which lies inside the project's vendored recipe.

## Decision

1. **uv never downloads a Python for a tool.** Environments are built with `--no-python-downloads`. A machine with no Python matching the tool's `runtime.version` makes the tool not ready, with a plain reason naming what to install. Installing the lock's packages during `baton tools setup` is allowed, since that is what setup is for.
2. **A tool runs in a fresh, empty scratch folder per dispatch**, not in its own folder. The runner passes the tool's folder to the entry command through a `{tool}` placeholder, so the command can name its script (`["python", "{tool}/backtest.py", ...]`). A tool therefore cannot change the vendored recipe it belongs to.
