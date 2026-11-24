---
id: 2026-11-layered-questions
title: "Every question the owner is asked has a short form and a full brief, and is held one at a time in the most interactive way the client allows"
status: proposed
level: standard
decisions: ["0049", "0169", "0170", "0171", "0184"]
touches: [design/packets.md, design/workers.md, design/director-interface.md, design/recipes.md, design/testing.md]
manual: [user/answer-questions-and-decide.md, user/how-you-want-to-be-told.md, reference/commands.md]
---

# Every question the owner is asked has a short form and a full brief, and is held one at a time in the most interactive way the client allows

## Request

### Problem

In the owner's recipe-builder run in `D:\rob\projects\baton-recipes` (Grok Bot as Director, 2026-11-23), the design step returned seven questions for the owner. Four things went wrong. Each is a gap in Baton, not only in that Director: nothing in the worker protocol, the request format or the Director skill prevents any of them on another model or harness.

**Q-1. The questions were too terse to decide.** A worker's question is `{id, ask, why, best_guess?, options?: [{id, label}]}` (§7, `packet.py`, `worker_runner.py`). `why` is one line on what the answer changes *in the process*; an option is only a label. Nothing carries what each option means in the owner's world, with an example, what it costs, and why the worker recommends one. The owner had to ask what "reading past an early warning level" meant before he could answer.

**Q-2. The detail came as a wall, apart from the questions.** Asked for more, the Director wrote seven executive summaries in a row and then put the seven terse questions in one card below them. The owner had to read everything first, then match each card question back to its summary. Discussing any one question meant breaking out of the card, with the sense of derailing the sequence.

**Q-3. The Director wrote the briefs itself.** It went back to the design document and the review and wrote the summaries from them. That is the Director interpreting subject material, which the skill forbids ("Don't answer subject questions"; relay experts faithfully). The worker that asked has the context; the brief should come from it.

**Q-4. No way to move around, see progress, or stop part way.** The owner could not move freely between questions, show or hide detail per question, see how far along he was, or stop with some answered without losing them. A blocked step's `retry` refuses a missing `needed` answer unless `--partial` is given, and nothing keeps answers between turns except the Director's conversation.

The owner's direction (2026-11-23): Baton must force his opinionated question UX on any Director, whatever the model, harness or chat. Every question comes with at least two levels of detail, a terse question and an expounded executive summary. The client decides how they are shown, but the Director must use the most interactive presentation it has: in plain chat the owner has all the detail he needs without feeling the interview will get off track, for example a terse question with an "explain more" answer, or full detail by default with a "just the question" answer. Never a write-up of several summaries followed by a card of the matching questions. The ideal, not required: move freely between questions, hide or reveal detail at will, see progress, and submit without every question answered, failing gracefully.

### Acceptance criteria

1. **Two levels in the data.** Every question a worker returns (`questions_for_human`, blocked or completed) carries `ask` (one line) and `brief`: an executive summary in the owner's terms of what the answer decides, what each option means in practice with a concrete example, what each costs or gives up, and which the worker recommends and why. Each option carries `means` (one or two sentences: what choosing it leads to). A result whose question lacks `brief` fails the result schema, as a missing `why` does now.
2. **The request carries both.** An interaction request built from questions (a blocked step's `retry`, open questions, the optional fields of a `retry` or `reject`) gives each field the `ask` as `title`, `why` as `description`, and, in `hints.fields.<id>`, the brief as `detail`, each option's `means`, and the recommended option. A recipe's hints file may give `detail` for a person step's fields too. Renderers that do not know the hint still give a valid answer.
3. **Held one at a time, detail beside its question.** The Director never shows a set of briefs apart from their questions, and never puts several questions in one card when it cannot attach each question's own detail to it. Each question is shown with its position ("3 of 7") and with its brief, or with its brief one word or one tap away, per the owner's detail setting (5).
4. **The most interactive presentation available.** The Director uses, in this order of preference: the client's native question widget, one question per card or tab, with each option's `means` as its description and the brief as the question's detail or preview, plus the answers *Explain more*, *Skip for now* and *Back*; otherwise plain chat, one question per message, with the position, the ask, the brief (or "say *more* for the full picture"), numbered options with their `means`, the recommendation, and what the owner can reply (a number, *more*, *skip*, *back*, *list*, *done*). When there are two or more questions and the local page can open, it offers the page once, in one line, as the place to move freely between them; the owner may stay in chat.
5. **Detail on the owner's terms.** `communication.md` says whether questions start with the brief shown (`full`, the conversational default) or with the ask and the recommendation only (`terse`, the operator default). The owner can switch mid-set ("just the questions", "give me the detail"); the Director follows it for the rest of the set and offers once to keep it in `communication.md`.
6. **A side discussion keeps the place.** When the owner discusses a question, the Director handles it as now (routing subject questions to an expert), then returns with "Back to question 4 of 7", keeping every answer given so far.
7. **Stopping part way fails gracefully.** When the owner says *done* with questions unanswered, the Director confirms back what was answered and lists what is left. Open questions: records the answered ones (a partial set is already allowed). A blocked step: keeps the answered ones as a draft (8), says plainly that the work stays paused on the rest, and offers the worker's recommendations for them, recorded only on the owner's yes. Nothing answered is lost; no guess is recorded as the owner's.
8. **Drafts last.** `answer <id> --draft` keeps confirmed answers on an open request without deciding it, with the owner's words. `interaction <id>` returns the draft; a Director picking the conversation up later, or the local page, starts from it. When a request changes (a new id), the draft carries over for every question whose id and text are unchanged.
9. **The Director never writes a brief.** When a question has no brief (a result from before this change, a Director-raised decision), the Director asks the expert who owns the material for one (`ask_sme project` for the subject, `ask_sme process` for how Baton or the recipe works) and relays it as theirs; it never writes one from the work's documents itself.
10. **The local page holds a question set the ideal way.** A request built from questions shows every question in a list with answered marks and "n of m answered"; the owner moves freely between them; each shows its ask, its options with their `means`, the recommendation marked, and a *Details* toggle for the brief. The draft is saved as the owner goes, so closing the page loses nothing. Confirm with questions unanswered says which, and offers to keep the answers as a draft or, where allowed, record them and leave the rest open.
11. **Checked.** The live test's transcript review (§17) counts as failures: briefs shown apart from their questions, a question shown with no detail reachable, several questions in one card without their own detail, and a lost answer. The Director skill's *Before you ask* list gains **Depth**: can the owner get the whole picture of this question without leaving it?
12. **Manual and design are current.**

### Open questions

1. **Brief on every question, or only `needed`?** *Suggested:* every question, required by the result schema; guidance of about 60 to 150 words. *Rationale:* `helpful` questions are where the owner most needs the stakes to decide whether to bother; a schema rule holds on any model, where guidance alone does not.
2. **A question with no brief: what does the Director do?** *Suggested:* as criterion 9, the expert writes it; the runtime marks such a field `detail: null` in its hints so the Director knows it is missing rather than empty. *Rationale:* sending it back to the worker costs a retry of the whole step; an expert consultation is cheaper and keeps the Director out of the subject.
3. **Default detail level.** *Suggested:* `full` for the conversational style, `terse` for the operator style (criterion 5). *Rationale:* matches what each style already promises; one line in each default file.
4. **Drafts in the runtime (criterion 8), or only in the conversation?** *Suggested:* in the runtime: `answer --draft` writes `.baton/runs/<run>/drafts/<request>.json`, records no decision and no event, and carries over by question id. *Rationale:* a Director's conversation can end or change harness mid-set (as happened when Codex gave way to Grok Bot); the local page needs it to be forgiving.
5. **The local page: offer, or open automatically?** *Suggested:* offer in one line when there are two or more questions (criterion 4); never open it unasked. *Rationale:* it is the richest view, but leaving the chat is the owner's call.
6. **Review findings shown to the owner.** A finding the owner must decide on (`accept-risk`) is a Director-raised decision, not a worker's question. *Suggested:* out of scope for the schema; criterion 9 covers it (the process expert writes the brief). Revisit if findings reach the owner often.

## Design

### Doc edits

- `design/packets.md` and `design/workers.md` (worker result): a question gains required `brief`; an option gains `means`; the packet instructions say what a brief holds and that it is in the owner's terms.
- `design/director-interface.md` §13.1 (requests): questions map to `title`, `description` and `hints.fields.<id>.{detail, options, recommended}`; `answer --draft` and the draft in `interaction`.
- `design/director-interface.md` §13.6: both styles gain the question rules (one at a time, position, detail beside its question, never a wall of briefs then a card) and the `questions: full | terse` setting.
- `design/director-interface.md` §13.8: the conversation layer's question flow (criteria 3, 4, 6, 7, 9), and drafts under the confirm-back seam (a draft is confirmed answers not yet decided).
- `design/director-interface.md` §13.9: the page's question-set view (criterion 10).
- `design/recipes.md` (interaction hints): `detail` joins `help` and `label` as a field hint.
- `design/testing.md` §17: the transcript checks of criterion 11.

### Manual edits

- `manual/user/answer-questions-and-decide.md`: how questions come (short and full), what to reply (*more*, *skip*, *back*, *list*, *done*), stopping part way, the page's question view.
- `manual/user/how-you-want-to-be-told.md`: the `full` / `terse` setting and switching mid-set.
- `manual/reference/commands.md`: `answer --draft`.

### Decisions

- New decision (next number) records the open questions' answers once the owner gives them. It amends 0049 (communication styles gain the question setting) and 0170 (a new field hint, and drafts); 0169's renderer neutrality stands: Baton supplies both levels, each renderer decides how to show them.

## Plan

### Slice 1: two levels in the data

- **Outcome:** workers return briefs and option meanings, and requests carry them.
- **Criteria:**
  - A result whose question has no `brief` fails the schema (test).
  - `questions_schema` puts the brief, the options' `means` and the recommended option in `hints.fields` (test).
  - recipe-builder's `design` prompt and the packet instructions ask for briefs in the owner's terms.
- **Effort:** S

### Slice 2: the Director holds questions the owner's way

- **Outcome:** the skill, §13.6, §13.8 and both communication defaults carry criteria 3 to 7, 9 and 11.
- **Criteria:**
  - The skill's *Answering requests* and *Before you ask* sections say it; the default files carry the detail setting.
  - The live test's transcript review checks for the patterns of criterion 11.
- **Effort:** S

### Slice 3: drafts

- **Outcome:** `answer --draft` keeps answers across conversations and changes of request.
- **Criteria:**
  - A draft is returned by `interaction`, records no decision, and carries over by unchanged question id (tests).
- **Effort:** M

### Slice 4: the page's question view

- **Outcome:** criterion 10 in the local page.
- **Criteria:**
  - Free movement, detail toggle, progress, autosaved draft, and Confirm with gaps (UI tests).
- **Effort:** M

## Log
