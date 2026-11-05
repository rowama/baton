# Baton — working instructions

The docs are in `docs/`; `docs/README.md` maps every file and every § to where it lives. Work is change-sized: each piece of work has a change doc in `docs/changes/`. The original build guide was split up after Phase 17; its build phases are frozen in `docs/history/build-phases.md`.

## Every session

1. Read `docs/principles.md` (always) and `docs/README.md`.
2. Read the change doc you are working on, then only the design docs it lists under `touches:` and the decision records under `decisions:`. Follow a § reference into another doc only when the work needs it.
3. Follow §0 (Ground Rules) throughout.
4. Before starting, confirm `pytest` is green (`.venv/bin/python -m pytest -q`).

## Starting a change

- New work starts as a change doc: copy `docs/changes/TEMPLATE.md` to `docs/changes/YYYY-MM-<slug>.md`, fill in the Request with the owner, `status: proposed`. Its `touches:` lists every design doc the change will edit.
- Open decisions: never silently decide one. Before designing, find every decision record with `status: proposed` that the change touches, plus any new question the change raises, and ask the owner about them up front, in one batch, each with a suggested answer and its rationale.
- Any other ambiguity in the docs: ask, don't guess.

## Recording decisions

- Each owner decision becomes a record `docs/decisions/NNNN-<slug>.md` (the next free number; front matter `id`, `title`, `status`, `date`, `source`, `sections`; then *Context* and *Decision*). An open question the owner has not settled is a record with `status: proposed`.
- When the owner decides a proposed record, set `status: accepted` and its date, and write the decision.
- In the design doc, the rule itself is written into its section, with a short `Decision: [NNNN](../decisions/NNNN-<slug>.md)` link where it was decided. Add the record to the change doc's `decisions:` and to the lists in `docs/README.md`.

## Doing a change

- Work slice by slice, as the change doc's Plan sets out. Each slice is one commit, with `pytest` green, that holds its code, its tests, the edits to the design docs it changes, and its entry in the change doc's Log.
- Section numbers are stable references: never renumber a heading. A new section takes the next free number in its file and gets a row in the `docs/README.md` § index. `tests/test_docs.py` checks that every § reference and every relative link in `docs/` resolves.
- Never edit `docs/history/`.

## Finishing a change

- All acceptance criteria demonstrated by tests; `pytest` green; the change doc's `status: done`.
- Commit subjects name the change: `<change id>: <slice title>`. The body lists modules, design docs touched, decisions recorded, and what the tests cover. The change doc and its Log are the handoff to the next session: keep them complete.
- Ask before pushing.
