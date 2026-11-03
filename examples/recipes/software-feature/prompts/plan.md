# Plan vertical slices

Split the change into **vertical slices**: each one a small, end-to-end increment that can
be implemented, reviewed and accepted on its own and leaves the project working.

Inputs: `requirements_doc` and, when the change was designed, `design_doc` (at `standard`
complexity there is no design; it is listed as not applicable). You can read the project's
working tree (read-only) to see what exists; do not change any file.

For each slice return:
- `title`: what it delivers, in a few words ("Sign-in form posts credentials").
- `outcome`: what a user or caller can do once it is done.
- `criteria`: acceptance criteria, each one checkable by a test or a short manual step,
  tied to the numbered requirements they satisfy ("R3: …").
- `effort`: `S` (under an hour of focused work), `M` (a few hours) or `L` (a day). Split
  anything bigger.

Rules:
- Order slices so each builds on the ones before; the first should be the thinnest useful
  path through the system.
- Every numbered requirement must be satisfied by at least one slice.
- Do not put pure set-up, refactoring or test-only work in a slice of its own unless it is
  unavoidable; fold it into the first slice that needs it.
- **When you are revising a plan** (your packet holds the previous plan's items with their
  ids): echo the `id` of every slice you keep, changed or not, and omit `id` on new ones.
  Never invent an id.
