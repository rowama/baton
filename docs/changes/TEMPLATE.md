---
id: YYYY-MM-<slug>          # the file name without .md
title: "<one line, in plain words>"   # quoted: titles often contain colons
status: proposed            # proposed | accepted | in-progress | done | abandoned
level: standard             # minor | standard | major (the software-feature triage scale, §5.5)
decisions: []               # decision records this change relies on or adds, e.g. ["0053"]
touches: []                 # design docs this change reads and edits, e.g. [design/runtime.md]
---

<!--
This template mirrors the shipped `software-feature` recipe (examples/recipes/software-feature,
§5.1), section for section, so a later crosswalk (§11.3) can import change docs as runs:

  front matter `level`   ↔ triage            (level, reasons)
  Request                ↔ run inputs + requirements (feature_request; summary, open_questions)
  Design                 ↔ design            (summary, open_questions; the design doc edits)
  Plan                   ↔ plan              (slices: title, outcome, criteria, effort)
  Log, one per slice     ↔ slices/<instance>: implement (commit_sha, summary, tests_added),
                           code_review (findings), accept (accepted, notes)

Keep the headings and field names. As in the recipe, the level decides how much is written:
  minor     Request and Log (one slice); Design lists the doc edits only; no Plan
  standard  Request, Plan and Log; Design lists the doc edits and decisions
  major     everything, and the owner approves Request and Design before Plan
-->

# <title>

## Request

### Problem

<What is wrong or missing, for whom, and how we know. Plain words; link evidence (logs, transcripts, bug evals).>

### Acceptance criteria

- <An observable outcome a test or a person can check.>

### Open questions

- <Anything the owner must answer before Design. Remove when empty.>

## Design

### Doc edits

- `<design doc>` §<n.m>: <what changes in the design, in a sentence>.

### Decisions

- <Decision record NNNN (new or existing) and what it settles; open ones stay `status: proposed` until the owner decides.>

## Plan

<Vertical slices, each delivering something observable. Effort is S, M or L (§8.7).>

### <slice title>

- **Outcome:** <what is true when this slice is done>
- **Criteria:**
  - <acceptance criterion, demonstrated by a test>
- **Effort:** M

## Log

<One entry per slice, written in the slice's own commit together with its code, tests and design doc edits.>

### <slice title>

- **Commit:** <the slice commit's subject; its SHA is found with `git log --grep`>
- **Summary:** <what was built; tests added>
- **Review:** <findings and how each was dispositioned, or "clean">
- **Accepted:** <yes or no, date, the owner's words>
