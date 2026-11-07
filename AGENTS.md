# Baton — working instructions

These are the working instructions for every agent working in this repo (Claude Code, Codex, or any other). `CLAUDE.md` imports this file; keep the instructions here, not there.

The docs are in `docs/`; `docs/README.md` maps every file and every § to where it lives. Work is change-sized: each piece of work has a change doc in `docs/changes/`, and every change doc has a row in the change register, `docs/changes/REGISTER.md`. The original build guide was split up after Phase 17; its build phases are frozen in `docs/history/build-phases.md`.

## Every session

1. Read `docs/principles.md` (always) and `docs/README.md`.
2. To find work or a change's status, read `docs/changes/REGISTER.md`, not the change docs themselves.
3. Read the change doc you are working on, then only the design docs it lists under `touches:` and the decision records under `decisions:`. Follow a § reference into another doc only when the work needs it.
4. Follow §0 (Ground Rules) throughout.
5. Before starting, confirm `pytest` is green (`.venv/bin/python -m pytest -q`). If the only failure is the register test (`test_change_register_matches_change_docs`), the owner has dropped in or edited a change doc: bring the register up to date first (see below), in the commit for your current work.

## The change register

`docs/changes/REGISTER.md` has one row per change doc: id (linked), title, status, level and a short note. It is the owner's view of the changes, so it must always match the change docs.

- Whenever you create a change doc, or change its `status`, `title` or `level`, update its row in the same commit.
- Whenever you touch the register, reconcile all of it: add a row for every change doc that has none (the owner may drop new files in without registering them), fix any row whose status, title or level no longer matches its front matter, and remove rows whose file is gone.
- Rows are ordered by status (in-progress, accepted, proposed, done, abandoned), then by id. The note says why a change is waiting (for example "On hold: after 2026-11-step-tool-harness", from the `# ON HOLD` comment on its status) or is empty.
- `tests/test_docs.py` checks that every change doc has exactly one row and that its status, title and level match.

## Starting a change

- New work starts as a change doc: copy `docs/changes/TEMPLATE.md` to `docs/changes/YYYY-MM-<slug>.md`, fill in the Request with the owner, `status: proposed`, and add its row to the register. Its `touches:` lists every design doc the change will edit.
- Open decisions: never silently decide one. Before designing, find every decision record with `status: proposed` that the change touches, plus any new question the change raises, and ask the owner about them up front, in one batch, each with a suggested answer and its rationale.
- Any other ambiguity in the docs: ask, don't guess.

## Recording decisions

- Each owner decision becomes a record `docs/decisions/NNNN-<slug>.md` (the next free number; front matter `id`, `title`, `status`, `date`, `source`, `sections`; then *Context* and *Decision*). An open question the owner has not settled is a record with `status: proposed`.
- When the owner decides a proposed record, set `status: accepted` and its date, and write the decision.
- In the design doc, the rule itself is written into its section, with a short `Decision: [NNNN](../decisions/NNNN-<slug>.md)` link where it was decided. Add the record to the change doc's `decisions:` and to the lists in `docs/README.md`.

## Doing a change

- Work slice by slice, as the change doc's Plan sets out. Each slice is one commit, with `pytest` green, that holds its code, its tests, the edits to the design docs it changes, its entry in the change doc's Log, and any register update.
- Section numbers are stable references: never renumber a heading. A new section takes the next free number in its file and gets a row in the `docs/README.md` § index. `tests/test_docs.py` checks that every § reference and every relative link in `docs/` resolves.
- Never edit `docs/history/`.

## Finishing a change

- All acceptance criteria demonstrated by tests; `pytest` green; the change doc's `status: done`, and its register row too.
- Commit subjects name the change: `<change id>: <slice title>`. The body lists modules, design docs touched, decisions recorded, and what the tests cover. The change doc and its Log are the handoff to the next session: keep them complete.
- Ask before pushing.
