---
id: recipes.recipe-builder
title: Recipe builder
audience: owner
order: 40
summary: Describe a process you do, and get a checked, ready-to-use process you approve.
related: [recipes.fit-check, user.start-with-a-goal]
step_labels: {}
---

## Here, now {#here-now}

Use **recipe builder** when you do something repeatedly, or a process you care about, and want Baton to follow it: onboarding a client, launching a product, planting a garden, closing the books. You describe the work in your own words; Baton asks what it needs, looks up how the work is usually done, designs the process, has it independently checked, and shows you a plain-language walkthrough. You decide whether to use it.

You never need to know how Baton describes processes. Talk about your work. The process it makes can be for work that will be done elsewhere, such as a workflow in another tool, a diagram, or a set of procedures and templates; where it will run is not a reason to refuse it. It builds a Baton process for making that work, not an export for another tool. If you want work run rather than a process made for it, it says so and asks, instead of changing the request.

## What you will be asked {#what-you-are-asked}

- To describe the process: a title and what you want, in your words, and any process you already have in mind.
- To confirm what it understood: **Is this what the process should do?**
- For larger processes, after the design has been checked: **Is this the process you want?** Saying no sends it back with your note.
- At the end, after reading the walkthrough: **Use this process?**

It works out what it can and says what it assumed, so you confirm rather than start from a blank page. It will not promote its own guess to something you said: it records only what you confirmed.

## What it produces {#what-it-produces}

- A **plan** of the process, in a document in the project (`recipes/plans/`).
- The **process** itself as a draft in your project (`recipes/drafts/`), checked automatically for mistakes.
- A **walkthrough** in plain language, so you can judge the process without reading it.

It never adds the process to your project's set on its own. After you approve it, your assistant asks before making it available.

## What it needs {#what-it-needs}

- Helpers that can reason and write, and, for the larger sizes, a helper that can **search the web** to learn how the work is usually done. If none can, you are told plainly before it starts, and the fix is to log in to a coding assistant such as Claude Code or Codex.
- A different company's model for the independent check of the design.

## The parts {#parts}

%parts%

## Example {#example}

> **Note:** You say: "We onboard new clients every month; I want the same steps each time." The assistant describes back what it heard and you confirm. It researches typical onboarding, designs the process, and has it checked. You read the walkthrough ("collect the contract, set up their account, schedule the kickoff...") and choose **Use this process?**.

## If it goes wrong {#if-it-goes-wrong}

- **You do not recognise the design:** say so at **Is this the process you want?**; it is reworked with your note, up to three rounds.
- **It asks something you cannot answer:** say that; it is not a test. See [if a question confuses you](user.answer-questions-and-decide#confusing).
