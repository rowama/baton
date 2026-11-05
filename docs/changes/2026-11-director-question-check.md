---
id: 2026-11-director-question-check
title: "The Director checks its questions before asking the owner, and the framing label tells the truth"
status: done
level: minor
decisions: []
touches: [design/director-interface.md]   # §13.3; also defaults/labels.yaml and the shipped skill
---

# The Director checks its questions before asking the owner, and the framing label tells the truth

## Request

### Problem

In the first real use, the Director asked the owner "Which framing parts should we start on?". The question used Baton vocabulary ("framing parts"), was ambiguous (start now, or include in the plan at all?), and its option label promised that the parts not chosen were "left for later", which Baton does not do: parts not selected are not kept. The skill made the Director a relay of Baton's choices, with no mandate to check a question's logic, ambiguity and completeness before the owner sees it.

The real fix for keeping unpicked parts is a separate framing-plan change; this change only makes the current label honest in the meantime.

### Acceptance criteria

- The section "Before you ask the owner anything" is in the shipped skill (`skills/baton-director/SKILL.md`) and, identically, in the §13.3 skill text.
- The `frame.select` label and effect in `defaults/labels.yaml` say what Baton actually does: work starts now on the chosen parts; the others are not kept.
- `pytest` green.

## Design

### Doc edits

- `design/director-interface.md` §13.3: the shipped skill text gains the section "Before you ask the owner anything" (meaning, promise, ambiguity, completeness, answerability, fit; judge the shape, not the subject; send flawed worker material back).

## Plan

Minor: one slice, *Director checks questions before asking* (effort S).

## Log

### Director checks questions before asking

- **Commit:** 2026-11-director-question-check: Director checks questions before asking
- **Summary:** Added "## Before you ask the owner anything" at the end of `skills/baton-director/SKILL.md` and identically at the end of the §13.3 skill text. `defaults/labels.yaml` `frame.select`: label "Start work on these", effect "Work starts now on the parts you chose. The parts you don't choose are not kept; to do them later, describe the goal again." Tests: `test_director_skill_names_every_call_it_relies_on` asserts the new heading is in the skill; `tests/test_conversation.py` follows the renamed label.
- **Review:** clean
- **Accepted:** yes, 2026-11-05, the owner's request: "Small change: the Director checks its questions before asking the owner, and fix a misleading label."
