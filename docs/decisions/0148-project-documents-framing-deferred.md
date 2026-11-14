---
id: "0148"
title: "Project documents: framing does not show roles yet, and a role is required unless it says otherwise"
status: accepted
date: 2026-11-13
source: "Owner, 2026-11-13, answering two questions while 2026-11-project-documents was built: \"Defer framing\" and \"Required\" (both as suggested)."
sections: ["§5.1", "§5.2", "§11.6"]
---

# 0148. Project documents: framing does not show roles yet, and a role is required unless it says otherwise

## Context

The Design of `2026-11-project-documents` said framing's run inputs would show each recipe's roles and a part's proposal could include bindings. Both need the built-in framing recipe's schemas to change (its run inputs and its output forbid extra fields), and changing `baton-frame@1` in place changes its hash, so framing runs open at upgrade could no longer be opened; Decision 0068 avoided a new framing version for the same reason. Separately, Decision 0142 lists `required` among a role's fields without saying its default.

## Decision

1. **Framing is deferred.** Roles appear in `catalog.summaries` (§5.2), `recipes()` and the manual's recipe topics. Framing's run inputs and output are unchanged, and `baton-frame@1` stays as it is. A part started later is bound like any start: the Director proposes bindings from `documents()` and the role descriptions and confirms them. Framing proposing bindings belongs to a later change (with the project review recipe).
2. **A role is required by default**, as step inputs are: an unbound required role stops the first step that needs it, and the Director asks the owner. `required: false` makes it optional (an unbound optional role is `not_applicable`).
