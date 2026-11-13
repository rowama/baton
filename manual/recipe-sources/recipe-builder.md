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
- If how the work could be done changes what the process must contain, to choose after it has compared the ways: see [choosing how it will be done](#implementation-choices).
- For larger processes, after the design has been checked: **Is this the process you want?** Saying no sends it back with your note.
- At the end, after reading the walkthrough: **Use this process?**

It works out what it can and says what it assumed, so you confirm rather than start from a blank page. It will not promote its own guess to something you said: it records only what you confirmed.

## Choosing how it will be done {#implementation-choices}

You may know what you want without knowing how it could be done: which software, framework, standard or set of procedures and training would do it. You do not need to name any. When a choice like that is open and matters, Baton looks into it and tells you what it found: a short list of plausible ways (including doing it by hand or building something custom, where that is sensible), what each would need, where the information came from and when it was read, what it left out and why, what is uncertain, and its recommendation. A recommendation is only that; nothing is decided until you say so, in your own words.

When it happens depends on the choice:

- **Early, while the process is being made.** If the answer changes what the process must contain (a printed guide and a mobile app need different things made and checked), Baton settles it with you before designing those parts. This work then gets the larger size, so the research step runs.
- **Inside the finished process.** If one process fits every way (each job picks its own tool, say), the process itself includes a stage that compares the options for that job, a point where you decide, and the stages that use your decision, before any work that depends on it.
- **Not at all.** If you already said how it must be done, or the work is plain, it does not compare anything.

If you name a product or a method, Baton asks whether it is a must, a preference or only an example. A must is not argued with, though it will tell you if what it finds contradicts it. Baton does not recommend one product over others as a rule, and it does not build exports for other tools or operate them. If it cannot reach current sources, it says so and asks rather than answering from memory.

## What it produces {#what-it-produces}

- A **plan** of the process, in a document in the project (`recipes/plans/`).
- The **process** itself as a draft in your project (`recipes/drafts/`), checked automatically for mistakes.
- A **walkthrough** in plain language, so you can judge the process without reading it.

It never adds the process to your project's set on its own. After you approve it, your assistant asks before making it available.

## What it needs {#what-it-needs}

- Helpers that can reason and write, and, for the larger sizes, a helper that can **search the web** to learn how the work is usually done and which ways of doing it exist. If none can, you are told plainly before it starts, and the fix is to log in to a coding assistant such as Claude Code or Codex.
- A different company's model for the independent check of the design.

## The parts {#parts}

%parts%

## Example {#example}

> **Note:** You say: "We onboard new clients every month; I want the same steps each time." The assistant describes back what it heard and you confirm. It researches typical onboarding, designs the process, and has it checked. You read the walkthrough ("collect the contract, set up their account, schedule the kickoff...") and choose **Use this process?**.

> **Note:** You say: "I want a planting plan for my beds; maybe an app?" Baton compares a printed guide with an app, notes what each would need and that app prices change, and recommends the guide. You answer: "A printed guide, yes." The process it designs then lays out and proofreads a guide, with no app stages. If you had said "whichever tool each customer's site already uses", the finished process would instead compare the options on each job, ask you to choose, and then use your choice.

## If it goes wrong {#if-it-goes-wrong}

- **It cannot find current information:** it tells you what it could not check and asks, instead of treating its memory as research. The fix is a helper that can search the web (see above).

- **You do not recognise the design:** say so at **Is this the process you want?**; it is reworked with your note, up to three rounds.
- **It asks something you cannot answer:** say that; it is not a test. See [if a question confuses you](user.answer-questions-and-decide#confusing).
