---
id: "0161"
title: "An owner may have an AI delegate act for them: warned and waived where risky, never the Director, recorded as the delegate"
status: accepted
date: 2026-11-16
source: "Owner, 2026-11-16: \"The human should be treated as sovereign\"; \"It's the decision of the sovereign human to act against warnings.\"; \"The delegate can only be a distinct AI agent separate from the Director.\"; \"1-concur. 2-concur.\"; \"1-agreed.\"; \"Concur with your recommendation for the communication channels approach.\""
sections: ["§2", "§8.4", "§13.3", "§13.7"]
---

# 0161. An owner may have an AI delegate act for them: warned and waived where risky, never the Director, recorded as the delegate

## Context

AI agents can be long-lived assistants that know what a person needs and act for them. The owner wants such an assistant to be able to act for the owner during steps of a process, and wants this settled before the `recipe-builder` changes are finished. Baton's rules today assume that an owner's decision comes from the owner: the Director never fabricates one, and a worker's claim of approval never stands in for it.

## Decision

1. **The owner is sovereign.** An owner may name an AI delegate to act for them at any step or decision of a run. Baton forbids no kind of act to a delegate.
2. **Risky acts are warned and waived, not refused.** Baton recognizes the traits that make delegating risky: an effect that cannot be undone or that spends money, accepting a risk, waiving a check. Before a delegate handles such an act, the owner is shown a clear warning and Baton records the owner's decision to go on, in their words.
3. **A waiver lasts one run by default.** A standing waiver is possible only in project policy, and is listed whenever the policy is shown.
4. **The Director is never a delegate.** The Director carries enough of Baton's identity that it is prohibited from acting for the owner. A delegate is a distinct AI agent, separate from the Director. Baton refuses this case; it does not warn and go on.
5. **A delegate's act is recorded as the delegate's,** never as the owner's, and the owner can list what was decided for them. A delegate is a model: it never counts as a person for review independence (§8.4).
6. **The owner of a recipe and the owner of a run are distinct.** A recipe's author marks which stages are risky to delegate and why, and the marks travel with the recipe. A run's owner decides whether to delegate, sees those marks and gives the waiver. Only a run's owner has a delegate for now; delegates for other people in a process are not designed.
7. **Baton does not model roles in an organization, and does not prove who decided.** The platform Baton runs on authenticates and authorizes its users. Baton's record is evidence of what was shown and what was answered. It makes no claim about legal liability.
8. **A delegate reaches Baton through one defined interface.** Baton defines a single request-and-answer contract (structured, checked against the act's schema, asynchronous) and offers it first over MCP with a delegate-only set of tools (Decision [0048](0048-mcp-transports.md)). Baton keeps nothing running to push requests; the delegate asks for them. Chat and email are bridges others may build on that contract, not interfaces Baton maintains.
9. **Built later,** as its own change ([2026-11-ai-delegates](../changes/2026-11-ai-delegates.md), on hold). `recipe-builder` records the delegation mark in its designs from `2026-11-builder-step-design` on.
