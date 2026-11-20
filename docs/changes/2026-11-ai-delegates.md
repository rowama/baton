---
id: 2026-11-ai-delegates
title: "An owner can have their own AI assistant act for them in a run, with warnings and a recorded waiver where that is risky"
status: proposed
level: major
decisions: ["0161", "0050", "0143", "0048", "0076", "0165"]
touches: [principles.md, design/recipes.md, design/runtime.md, design/director-interface.md, design/platform-and-security.md]
manual: []
---

# An owner can have their own AI assistant act for them in a run, with warnings and a recorded waiver where that is risky

## Request

### Problem

Every decision in a run, and every step a person does, waits for the owner. The owner answers through the Director (`decide`, `disposition`, `waive`) or by handing in a result (`submit`). Many owners will have a long-lived AI assistant that knows their preferences and could answer for them, but Baton has no way to name one, offer it a request, warn when that is unwise, or record that an answer came from it and not from the owner.

Decision [0161](../decisions/0161-ai-delegates.md) settles the principles: the owner is sovereign and may delegate anything; risky acts are warned and waived, not refused; a waiver lasts one run unless project policy makes it standing; the Director is never the delegate; a delegate's act is recorded as the delegate's; a recipe's author marks the risky stages and the run's owner decides; and the delegate reaches Baton through one contract, first over MCP.

`recipe-builder@6` already marks, in every design, whether delegating each person's stage and owner decision is risky (`delegation {risky, reason}`, §5.7). The marks reach the design document and walkthrough but not the recipe, and nothing acts on them. This change makes them work.

### Acceptance criteria

1. **The owner names a delegate in project policy.** `policy.delegate` gives its name, its declared identity (who makes its model) and which kinds of request it handles. It is set, changed and removed only with `policy set` and the owner's words, as any policy change is (§13.7). A project has at most one delegate.
2. **Recipes carry the marks.** A step or gate may declare `delegation: {risky: true, reason: "<in the owner's words>"}`. `recipe-builder` writes the marks from its design into the recipe it generates. The recipe format stays `baton-recipe/1`.
3. **Baton adds its own risky acts.** Whatever the recipe says, these are risky to delegate: accepting a risk (`disposition … accepted_risk`), waiving a gate (`waive`), and a step or gate whose recipe mark is risky.
4. **A request goes to the delegate when policy allows.** When something in a run waits on the owner, and it is of a kind the delegate handles, Baton offers it to the delegate. The owner can always answer it instead, and the first answer recorded wins.
5. **A risky request needs a waiver first.** A risky request is not offered to the delegate until the owner has waived for it. The Director shows the owner the warning (the recipe's reason, or Baton's) and records their answer. A waiver covers one request, or the rest of the run. A standing waiver for a recipe is project policy and is listed whenever the policy is shown.
6. **The delegate has its own interface and nothing else.** `baton mcp --delegate` serves only three tools: list the requests offered to it, read one, and answer one. It has none of the Director's tools, and the Director's server has no tool that records a delegate's answer.
7. **The delegate sees what the owner would see.** A request carries the question, the choices with their plain labels, the documents the owner would be shown, and the deadline for answering. Nothing about the rest of the project.
8. **An answer is checked like the owner's.** It must be one of the request's choices, with the delegate's reason. Answers to a blocked step's questions must cover the needed ones. A result for a person's step is checked as `submit` checks it. A wrong answer is refused and the request stays open.
9. **A delegate's act is recorded as the delegate's.** Every decision carries who made it. `status`, `board`, step records and the run summary show which decisions the delegate made, in plain words ("your assistant approved this").
10. **Unanswered requests return to the owner.** A request the delegate has not answered within the policy's time, or that it declines, goes back to the owner, and the Director is woken as for any decision that waits on the owner. Nothing waits on a silent delegate forever.
11. **The owner is told and can undo.** At the owner's next contact the Director says what the delegate decided since they last looked. Each delegate decision can be reversed as the owner's own can (`revise`, `decide`), where the work it led to can still be redone.
12. **A delegate is never an independent person.** For independence (§8.4) a delegate is matched by its declared identity; an undeclared one is unknown, so it is never independent of anything (Decision [0076](../decisions/0076-unknown-identity-not-independent.md)).
13. **The Director cannot act as the delegate.** The two servers are separate, and over HTTP the delegate needs its own token. The Director skill forbids connecting to the delegate's interface. Baton cannot tell two sessions of the same agent apart; that is left to the platform, as Decision 0161, item 7 says.
14. **Nothing changes without a delegate.** A project with no `policy.delegate` behaves exactly as today.
15. **Manual and design are current.**

### Open questions

Each has a suggested answer, assumed until the owner decides.

1. **Which kinds of request can a delegate handle in this change?** *Suggested:* the owner's acts on a run's steps, as six kinds: `gates` (human gates, including protected-file and triage approvals), `answers` (a blocked step's questions), `person_steps` (a step a person does), `escalations` (retry or abandon, and an iteration limit), `ratings` (rating signals), `findings` (dispositions, and waiving a gate). The project's own acts stay with the owner for now: permissions, vendoring, binding and attesting documents, notes, adoption baselines and framing selections. *Rationale:* run acts all come through one pending-decision path, so one contract covers them; project acts have their own paths and can be added once this is proven. This scopes the first version; it forbids nothing.
2. **Are there acts only the owner can do, whatever the policy?** *Suggested:* yes, three, because delegation rests on them: naming or changing the delegate and what it handles; giving a waiver; changing project policy. *Rationale:* if the delegate could waive its own warnings, the warning would mean nothing. This follows from Decision 0161, items 2 and 3, but it is a limit on the delegate and should be the owner's explicit choice.
3. **How does a person's step reach the delegate?** *Suggested:* only steps whose result is the output and text artifacts, handed in inside the answer; a step needing binary files or physical work stays with the owner. *Rationale:* MCP carries text well; files on the delegate's machine are not Baton's to reach.
4. **Does a delegate's answer skip the confirm-back?** *Suggested:* yes. The confirm-back (§13.8) protects against the Director misreading a conversation; a delegate's answer is already structured and checked, with its reason as the note. The owner's protection is criterion 11. *Rationale:* asking the owner to confirm each delegate answer would make the delegate pointless.
5. **How long may a delegate take?** *Suggested:* `policy.delegate.answer_within`, default `24h`. Expiry is noticed by any Director call on the run and by `waits check` (§8.7), so a scheduled check also returns stale requests. *Rationale:* no new process; the existing check already runs on a schedule when the owner set one.
6. **How is the delegate told a request is waiting?** *Suggested:* an optional hook, `on_delegate_request`, beside the other completion hooks (§8.7); without it the delegate asks for its requests. *Rationale:* Baton pushes nothing itself, and a hook is how it already wakes a Director.
7. **How are delegate decisions recorded?** *Suggested:* as the same `human_decision` events, with actor `delegate:<name>` and `by: delegate`, the request id and any waiver id; never with actor `human`. *Rationale:* every path that acts on a decision keeps working, and every report can still tell the two apart. The alternative, a new event type, would duplicate each decision path.
8. **What does the owner hear, and when?** *Suggested:* at the next contact, one short list of what the delegate decided since the owner last looked, risky ones first; and `delegated(run?)` lists them all on request. *Rationale:* told at once would interrupt the owner, which is what they delegated to avoid; told only on request would let risky acts pass unseen.
9. **How is the delegate's identity known?** *Suggested:* the owner declares it in the policy (`identity: {creator, model_id?}`), and Baton takes it as declared. *Rationale:* Baton cannot inspect another agent; declared is honest, and unknown is safe.

### Out of scope

- **Delegates for people other than the run's owner** (Decision 0161, item 6).
- **Project-level acts** by a delegate (open question 1).
- **Chat or email bridges.** Others may build them on the contract (Decision 0161, item 8).
- **Proving who answered.** The platform authenticates its users (Decision 0161, item 7).
- **More than one delegate per project.**

## Design

For the owner's approval, with the Request.

### Shape

- **Policy.**
  ```yaml
  policy:
    delegate:
      name: rob-assistant
      identity: { creator: openai, model_id: gpt-5 }      # as the owner declares it
      handles: [gates, answers, escalations, ratings]
      answer_within: 24h
      waivers:                                           # standing; owner only
        - { recipe: quick-run, scope: run, note: "Fine for quick runs" }
  ```
  It is part of the policy's value (§13.7): hashed, changed only with words, pinned per run like the rest. The delegate's HTTP token lives in `~/.baton/mcp.yaml` under `delegate_token`, never in the project.
- **Recipe.** `delegation` is allowed on a step and on a `human` or `review` gate; `risky` is a boolean, `reason` is required when `risky` is true. `generate` in `recipe-builder@9` copies the design's marks; the package review checks that every mark arrived.
- **Requests.** When an owner decision becomes pending (the same moment `status` would list it), and its kind is in `handles`:
  - not risky, or covered by a waiver: `delegate_requested {request_id, ref, kind, risky, waiver_id?, deadline}`;
  - risky with no waiver: nothing is offered. `status` lists the decision with `delegable_after_waiver {reason}`, and the Director asks the owner.
  A request is one pending owner decision; its id is stable while the decision stays pending.
- **Waiver.** `delegate_waive(run, ref?, scope: request|run, note)` (CLI `baton delegate waive`) records `human_decision {kind: delegate_waiver, scope, reason_shown, note, decision_id}` with actor `human`, then offers the request. It is refused with no words, or when the policy names no delegate.
- **The delegate's server.** `baton mcp --delegate [--http]` serves:
  - `requests()`: the open requests offered to it, `[{request_id, run_title, kind, question, deadline}]`;
  - `request(request_id)`: the full request: `prompt`, `options [{decision, label, effect}]` as the Director gets them (§13.8), questions with their ids for `answers`, and the contents of the documents the owner would be shown;
  - `answer(request_id, decision, reason, answers?, result?)`, or `decision: decline`.
  An answer runs the same checks and recording as the matching owner call, with actor `delegate:<name>`. `decline` returns the request to the owner (`delegate_declined`). Over stdio anyone who can start the server can use it, as for `baton mcp`; over HTTP the delegate's token is required and the Director's is refused.
- **Return to the owner.** Past `deadline`: `delegate_expired`, the decision stays pending for the owner, and `on_needs_human` fires. Checked on every `status`, `board`, `resume` and `waits check`.
- **Hook.** `on_delegate_request` fires on `delegate_requested` with `BATON_REQUEST_ID`; optional, project or machine level.
- **Reporting.** `delegated(run?, since?)` lists delegate decisions. `status` and `board` carry `delegated_since_last_seen`; "last seen" is the latest owner decision or `delegated` call. The run summary lists every delegate decision and every waiver.
- **Independence.** Matching (§8.4) treats `delegate:<name>` as a profile with the declared creator and model; nothing about a delegate ever satisfies a requirement for a person.
- **The Director skill** says: when a delegate exists, tell the owner what it decided since they last looked; before a risky request, show the reason and ask whether to let the assistant handle it, recording the answer with `delegate waive`; never connect to the delegate's server or answer through it.

### Doc edits

- `principles.md`: **Delegate**, a new concept: the owner's own AI assistant, named in policy, that may answer the owner's requests in a run.
- `design/recipes.md` §5.3 (load rules for `delegation`), §5.7 (`recipe-builder@9` writes the marks).
- `design/runtime.md` §8.2 (`delegate_requested`, `delegate_declined`, `delegate_expired`; the `delegate` actor; `human_decision` with `by`), §8.4 (a delegate's identity), §8.7 (the hook; expiry in `waits check`).
- `design/director-interface.md` §13.1 (`delegate waive`, `delegated`; `status` and `board` fields), §13.2 (`baton mcp --delegate`), §13.3 (the skill), §13.7 (`policy.delegate`), §13.8 (delegate answers and the confirm-back).
- `design/platform-and-security.md`: the delegate's server, its token, and what Baton can and cannot tell about who answered.

### Manual edits

To be listed when the change is accepted. Expected: an owner's topic on letting an assistant act for you, an administrator topic on connecting a delegate, `admin/director-commands.md` and `reference/commands.md`.

### Decisions

- [0161](../decisions/0161-ai-delegates.md) (accepted): the principles this change builds.
- [0050](../decisions/0050-action-permissions.md), [0143](../decisions/0143-project-policy.md) (accepted): project policy and how it changes.
- [0048](../decisions/0048-mcp-transports.md) (accepted): MCP over stdio and loopback HTTP with a token.
- [0076](../decisions/0076-unknown-identity-not-independent.md) (accepted): an unknown identity is never independent.
- [0165](../decisions/0165-waiting-steps-details.md) (accepted): `waits check`, which also returns expired requests.
- The nine open questions above become one record when the owner answers them.

## Plan

Slices as proposed; refined once the Request and Design are approved.

### Slice 1: marks and policy

- **Outcome:** recipes carry delegation marks, `recipe-builder@9` writes them, and a project can name a delegate; nothing is offered yet.
- **Criteria:** load rules for `delegation`; `generate` copies the marks and the package review checks them; `policy.delegate` validated, hashed, set and shown; standing waivers listed; `@6` pinned runs keep `@6`.
- **Effort:** M

### Slice 2: requests, waivers and the delegate's server

- **Outcome:** a pending decision is offered to the delegate, answered through `baton mcp --delegate`, and recorded as the delegate's; a risky one waits for the owner's waiver.
- **Criteria:** offering by kind; Baton's own risky acts; `delegate waive` for one request and for the run; the three tools and their checks per kind; first answer wins; decline; the Director's server has no answer tool and the delegate's has no Director tool; HTTP token separation; a person's step with an inline result.
- **Effort:** L

### Slice 3: return, reporting and the Director

- **Outcome:** an unanswered request returns to the owner, and the owner is told what the delegate did and can undo it.
- **Criteria:** expiry on status, board, resume and `waits check`; `on_needs_human` and `on_delegate_request`; `delegated` and `delegated_since_last_seen`; the run summary; reversing a delegate's approval with `revise`; independence with declared and undeclared identities; the Director skill; the manual; a scenario from naming a delegate to a reversed decision.
- **Effort:** M

## Log

### Proposal recorded

- **Summary:** Recorded from the owner's discussion of 2026-11-16 with Decision 0161. No design, no code.
- **Owner decision:** 2026-11-16, "I want to address it before we're done with recipe-builder."
- **Accepted:** No; on hold.

### Interface settled

- **Summary:** The delegate's interface is one contract defined by Baton, first over MCP; recorded as Decision 0161, item 8, and moved from the open questions into criterion 8.
- **Owner decision:** 2026-11-16, "Concur with your recommendation for the communication channels approach." (0161).
- **Accepted:** No; on hold.

### Taken off hold and written out

- **Summary:** The recipe-builder changes it waited on are done, and `recipe-builder@6` already produces delegation marks that nothing used. Request completed (fifteen criteria), nine open questions with suggested answers, Design and Plan written. No code changed.
- **Owner decision:** 2026-11-17, "Take it off hold".
- **Accepted:** No; proposal only. Nine open questions await the owner.
