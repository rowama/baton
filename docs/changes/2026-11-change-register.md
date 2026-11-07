---
id: 2026-11-change-register
title: "Change statuses are tracked in one register that every agent keeps up to date"
status: done
level: minor
decisions: []
touches: []                 # docs/README.md, docs/changes/REGISTER.md, AGENTS.md, CLAUDE.md, tests/test_docs.py
---

# Change statuses are tracked in one register that every agent keeps up to date

## Request

### Problem

The list of change docs is growing, and the only way to see a change's status is to open its file and read its front matter. The working instructions also reached only Claude (`CLAUDE.md`); other agents (Codex and the like) read `AGENTS.md`, which did not exist.

### Acceptance criteria

- `docs/changes/REGISTER.md` lists every change doc with its title, status, level and a note on why it is waiting.
- Every agent's instructions say to keep the register up to date, including registering change docs the owner drops in without a row.
- A test fails when a change doc has no row, has more than one, or its row's status, title or level differs from its front matter.

## Design

### Doc edits

- `AGENTS.md` (new) holds the working instructions for every agent, with a section on the change register; `CLAUDE.md` imports it.
- `docs/README.md`: the map row for `changes/` points at the register.
- `docs/changes/REGISTER.md` (new): the register.

### Decisions

- None.

## Plan

One slice (minor).

## Log

### The change register

- **Commit:** 2026-11-change-register: The change register
- **Summary:** Added `docs/changes/REGISTER.md` with a row for each of the 13 change docs; moved the working instructions to `AGENTS.md` (imported by `CLAUDE.md`) with the register rules; `tests/test_docs.py` scans `AGENTS.md`, skips `REGISTER.md` as a change doc, and adds `test_change_register_matches_change_docs`.
- **Review:** clean
- **Accepted:** yes, 2026-11-06, the owner's request: "Set things up so that all agents (not just Claude) starts using a change register for tracking the formal changes in docs/changes."
