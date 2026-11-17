---
id: 2026-11-ai-delegates
title: "An owner can have their own AI assistant act for them in a run, with warnings and a recorded waiver where that is risky"
status: proposed            # ON HOLD: recorded 2026-11-16 so the builder changes can allow for it; to be designed after the recipe-builder changes of Decision 0155
level: major
decisions: ["0161", "0050", "0143", "0048"]
touches: [principles.md, design/recipes.md, design/workers.md, design/runtime.md, design/director-interface.md, design/platform-and-security.md]
manual: []
---

# An owner can have their own AI assistant act for them in a run, with warnings and a recorded waiver where that is risky

> **On hold.** Discussed 2026-11-16 (Decision [0161](../decisions/0161-ai-delegates.md)). Recorded now so recipes can carry delegation marks from the start. Not to be designed further until taken off hold.

## Request

### Problem

A person's step or an owner's decision can be answered only by the person, through the Director or by submitting a file. Many owners will have a long-lived AI assistant that knows their preferences and could answer for them. Baton has no way to name such an assistant, to route a step to it, to warn when that is unwise, or to record that an answer came from it and not from the owner.

### Acceptance criteria (draft)

1. **The owner names a delegate** in project policy (§13.7): which agent, and what it may handle. Naming or changing a delegate is always the owner's own act.
2. **The Director switches on it.** At a person's step or an owner's decision, the Director engages the delegate when policy allows, otherwise the owner.
3. **Recipes carry delegation marks.** A step or gate may be marked as risky to delegate, with the reason, in the recipe author's words. Baton also treats as risky, whatever the recipe says: an accepted risk, a waiver, and a permission the project policy sets to ask or deny.
4. **A risky act needs a waiver.** Before a delegate handles a marked act with no waiver covering it, the owner is shown the warning and answers. The waiver records the warning shown, the owner's words and its extent (this act, this run, or standing in policy).
5. **The Director cannot be the delegate.** Baton refuses a delegate that is the Director. The Director has no command that records a delegate's answer: a delegate's answer enters only through the delegate's own interface.
6. **Records.** A delegate's result carries the delegate's identity. `status`, step records and the run summary show which decisions a delegate made. The owner can list them and can revise them where the effect still allows.
7. **Independence.** A delegate is matched as its model and vendor, never as a person (§8.4).
8. **One defined interface.** A delegate receives only what the owner would be shown for that act, answers only in the act's schema with a reason, and can do nothing else in the project. The interface is one request-and-answer contract defined by Baton, offered first over MCP with a delegate-only set of tools; the delegate asks for its requests, since Baton keeps nothing running to push them. Chat and email bridges may be built on the contract by others (Decision 0161, item 8).

### Open questions

- **How far can "never the Director" be enforced?** By structure: separate tools, a separate credential, and no Director command that records a delegate's answer. Beyond that Baton cannot tell two sessions of one agent apart; the Director's instructions carry the rest, and the platform's authentication is assumed.
- **Does a waiting delegate use the waits change** (a step held as state until an answer arrives)?
- **What does the owner see, and when,** of what the delegate decided: at once, in a digest, or on request?
- **How does a recipe's mark relate to the builder's stage traits** (`effect`, `result`)?
- **Delegates for people other than the run's owner.** Not designed; needs identities Baton does not have.

## Design

To be written when taken off hold.

## Plan

To be written when taken off hold.

## Log

### Proposal recorded

- **Summary:** Recorded from the owner's discussion of 2026-11-16 with Decision 0161. No design, no code.
- **Owner decision:** 2026-11-16, "I want to address it before we're done with recipe-builder."
- **Accepted:** No; on hold.

### Interface settled

- **Summary:** The delegate's interface is one contract defined by Baton, first over MCP; recorded as Decision 0161, item 8, and moved from the open questions into criterion 8.
- **Owner decision:** 2026-11-16, "Concur with your recommendation for the communication channels approach." (0161).
- **Accepted:** No; on hold.
