# Baton — working instructions

The spec is `docs/baton-framework-build-guide.md`. It is the source of truth; this file only says how to work with it.

## Every session

1. Read the whole build guide before writing code (it says so in its header, and it changes between sessions).
2. Follow §0 (Ground Rules) throughout.
3. Find where we are: the last `Phase N:` commit in `git log --oneline` is the last finished phase. The next phase is N+1 in §16 (Build Order). Its acceptance criteria (the ✅ line) define done.
4. Before starting, confirm the previous phase's acceptance criteria still hold and `pytest` is green (`.venv/bin/python -m pytest -q`).

## Open decisions (§18)

- Never silently decide anything listed in §18. Before starting a phase, identify which undecided §18 items the phase touches and ask the owner about them up front (show the bracketed suggestion), in one batch.
- When the owner decides, record it in §18 as `**Decided (YYYY-MM-DD):** ...` and update the relevant guide section.
- Any other ambiguity in the guide: ask, don't guess.

## Finishing a phase

- All acceptance criteria demonstrated by tests; `pytest` green.
- Guide updated for anything clarified or decided during the phase.
- One commit per phase, subject `Phase N: <summary>`, with a body listing modules, guide sections touched, §18 items decided, and what the tests cover. That commit message is the handoff to the next session — make it complete.
- Ask before pushing.
