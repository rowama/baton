---
id: "0159"
title: "Tool runs: environments named by lock and Python, an inputs file of values and file references, built at dispatch, undeclared output files fail"
status: accepted
date: 2026-11-16
source: "Owner, 2026-11-16: chose \"Lock + Python\", \"Values and file refs\", \"Build at dispatch\" and \"Attempt fails\" for 2026-11-tool-steps Slice 2."
sections: ["§4.4", "§5.9", "§6.3", "§7.1"]
---

# 0159. Tool runs: environments named by lock and Python, an inputs file of values and file references, built at dispatch, undeclared output files fail

## Context

Starting Slice 2 of `2026-11-tool-steps` (a tool step runs) raised four details the Design and Decisions [0156](0156-tool-steps-details.md) and [0158](0158-tool-steps-no-python-download-scratch-cwd.md) left open. The suggested answers were put to the owner in one batch, and the owner chose each.

## Decision

1. **An environment is named by its lock and its Python:** `~/.baton/tools/<lock sha256>-py<major>.<minor>/`. Two tools with the same lock that need different Pythons (an empty lock is common) never share one. This refines 0156 item 6.
2. **The inputs file** a tool reads is one JSON object keyed by input name. A JSON input is its value; any other input is `{"path": <absolute path in the packet>, "media_type": <type or null>}`. Input values never appear on a command line.
3. **Dispatch builds a missing environment** from the lock before the attempt is recorded. A missing uv or Python, or a failed build, is a platform failure: nothing is dispatched, the step stays ready and an incident says why. `baton tools setup` builds environments ahead of time. Dispatch refuses only what Baton cannot fix itself (0156 item 5).
4. **Only `output.json` and declared artifacts** (`<name>` or `<name>.<ext>`, one file each) may be left in the output folder. Any other file fails the attempt, and the result's notes name it.
