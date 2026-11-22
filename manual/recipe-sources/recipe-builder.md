---
id: recipes.recipe-builder
title: Recipe builder
audience: owner
order: 40
summary: Describe a process you do, and get a checked, ready-to-use process you approve.
related: [recipes.fit-check, user.start-with-a-goal]
step_labels: {}
anchor_aliases: {engineered-tools: engineered-programs}
---

## Here, now {#here-now}

Use **recipe builder** when you do something repeatedly, or a process you care about, and want Baton to follow it: onboarding a client, launching a product, planting a garden, closing the books. You describe the work in your own words; Baton asks what it needs, looks up how the work is usually done, designs the process, has it independently checked, and shows you a plain-language walkthrough. You decide whether to use it.

Not every part of your work deserves a full process. When you need one document good enough to start on, such as a lean business plan or a procedure for the shop, recipe builder recommends a **quick run** instead: it chooses or writes a guide for that document, you approve the guide, and a [quick run](recipes.quick-run#here-now) writes the document. See [a full process or a quick run](#full-or-quick).

You never need to know how Baton describes processes. Talk about your work. The process it makes can be for work that will be done elsewhere, such as a workflow in another tool, a diagram, or a set of procedures and templates; where it will run is not a reason to refuse it. It builds a Baton process for making that work, not an export for another tool. If you want work run rather than a process made for it, it says so and asks, instead of changing the request.

## What you will be asked {#what-you-are-asked}

- To describe the process: a title and what you want, in your words, and any process you already have in mind. If you already have it written down, give it the documents too: see [what you already have written down](#your-documents).
- Once, to confirm what it understood and approve two things it judged, each with its reason: how much to build (a quick run, or a small, standard or large process), and whether it may write small programs for the process. A program does rule-like work (a calculation, a conversion, matching one list against another) the same way every time, at no cost each time it runs; it has to be written and checked first, and looked after if the work changes. The limit is none, small programs, or programs built to examples you supply (for work with exceptions or real data formats, such as matching a bank export to invoices). You set this limit; Baton recommends one.
- If how the work could be done changes what the process must contain, to choose after it has compared the ways: see [choosing how it will be done](#implementation-choices).
- For larger processes, or when it may write programs, after the design has been checked: **Is this the process you want?** Saying no sends it back with your note.
- When it builds programs to your examples, after the process is drafted: for your examples, and then **Build the programs to these examples?** See [programs built to your examples](#engineered-programs).
- At the end, after reading the walkthrough: **Use this process?**
- On a quick run instead, after that first question: **Use this guide?** Nothing else is built.

It works out what it can and says what it assumed, so you confirm rather than start from a blank page. It will not promote its own guess to something you said: it records only what you confirmed. When it designs the process and meets a choice that is yours, such as when a release waits for you, it stops and asks you, with its recommendation, before it designs around it; it is not allowed to go on with a guess. Smaller guesses, such as an assumption about how the work is done today, do not stop it: it goes on and asks you to confirm them, and you answer when you can (see [choices made on a best guess](user.answer-questions-and-decide#best-guesses)).

## What you already have written down {#your-documents}

If you already do this work and have it written down (a procedures manual, a checklist, an earlier kit, notes of what went wrong last time), give those documents to recipe builder when you start, instead of pasting them into your description. Your assistant attaches them to the run; you are shown each one and asked to confirm it before the work starts.

Recipe builder reads them as evidence of how you work: the steps, people, checks and lessons you already have. It keeps what works, and the design it shows you says what it kept from them, what it changed and why. It does not treat them as a specification it must copy, unless you say so ("follow our manual exactly"). Where a document and what you said disagree, what you said now counts, and it tells you about the difference.

## A full process or a quick run {#full-or-quick}

After checking whether a process you already have covers the work, recipe builder recommends one of two things, with what each costs and gives:

- **A full process:** it looks up how the work is usually done where that matters, designs the process, has it checked by a second helper, and builds it. It takes longer, and you get a process you can use for every job like this one.
- **A quick run:** one document good enough to use, written in a few minutes by a helper following a guide, and judged by you alone. It suits a plan, a brief or a procedure you need once or rarely, where nothing is costly, irreversible or regulated.

You choose; your first answer settles it. On a quick run, it adopts one of the guides that come with Baton, adapts one to your kind of work, or writes a new one, and shows it to you: **Use this guide?** The guide is kept in your project's `guides/` folder, and your assistant then offers the quick run that uses it. If one of Baton's guides already fits as it is, your assistant can copy it for you without recipe builder at all (`baton guides copy`).

A project that is still using an earlier version of recipe builder keeps it, and asks its questions as before.

## Choosing how it will be done {#implementation-choices}

You may know what you want without knowing how it could be done: which software, framework, standard or set of procedures and training would do it. You do not need to name any. When a choice like that is open and matters, Baton looks into it and tells you what it found: a short list of plausible ways (including doing it by hand or building something custom, where that is sensible), what each would need, where the information came from and when it was read, what it left out and why, what is uncertain, and its recommendation. A recommendation is only that; nothing is decided until you say so, in your own words.

When it happens depends on the choice:

- **Early, while the process is being made.** If the answer changes what the process must contain (a printed guide and a mobile app need different things made and checked), Baton settles it with you before designing those parts. This work then gets the larger size, so the research step runs.
- **Inside the finished process.** If one process fits every way (each job picks its own tool, say), the process itself includes a stage that compares the options for that job, a point where you decide, and the stages that use your decision, before any work that depends on it.
- **Not at all.** If you already said how it must be done, or the work is plain, it does not compare anything.

For an early choice, research pauses with its comparison and questions for you. It does not need a finished decision to ask. Your assistant confirms your answer and retries research with your words; only then does the decision go into the design. A recommendation never counts as your answer.

If you name a product or a method, Baton asks whether it is a must, a preference or only an example. A must is not argued with, though it will tell you if what it finds contradicts it. Baton does not recommend one product over others as a rule, and it does not build exports for other tools or operate them. If it cannot reach current sources, it says so and asks rather than answering from memory.

## Who does each part {#who-does-each-part}

The design gives each part of the process to the simplest kind of doer that can do it: a small program for rule-like work (adding up, converting, matching), an automatic check, a person, or an AI helper for reading, writing and judging. Programs come first because they give the same result every time, cost nothing each time they run and need no AI service. A part that reads something open-ended and also applies rules (a client's email and a price list) is split in two: first someone reads it, then a program or a check applies the rules.

The design document shows you, in plain words:

- each small program: what it does, what it may touch, and worked examples ("two lines of 1 and 2 make a total of 3") you can judge before anything is built;
- each part an AI helper does that a program could do, what you give up (the same result every time, no cost each run) and what a program would have cost, and why it was not used;
- the parts where letting your own AI assistant act for you would be risky, such as a payment that cannot be taken back.

If you said no programs, and the design finds parts a program could do, you are told once, with the parts named, and can raise the limit or keep it.

## Programs built to your examples {#engineered-programs}

Some work needs more than a small program: reading a real export from another system, matching records by rules that have exceptions, or a package that has to be installed. If you allowed it, the design describes such a program in full before anything is built: what it does, what goes in and what comes out, what it may touch, every package it needs and why, and why it is still one program and not a software project of its own. Anything bigger is left as a separate project you may start later, and that part of the process is done another way meanwhile.

The program is built to **your examples**: real files that go in, and the result you expect from each. You will be asked for at least three per program, one of them a case you find awkward. Baton makes a folder for each example in your project, under `examples/`, and says what goes in it; you put your files there and confirm they are yours. Your files are copied exactly, and a check proves they were not changed.

Three good examples are the minimum. You may supply fewer, or none, but with fewer the program is more likely to differ from what you expect. If you go ahead, Baton drafts the missing examples, and you approve each one before anything is built.

You then see every example once more: **Build the programs to these examples?** After that, a helper writes each program, it is run on every example (twice, so it must give the same result each time), and a reviewer from a different provider checks it against its description. A program that does not pass is tried again, at most three times. Then you decide: try again with a note, do that part another way (for example by an AI helper, or by you), with what that gives up said plainly, or stop. Before you approve the finished process, you see for each program which of your examples it passed, what it needs installed and what it may touch.

## What it produces {#what-it-produces}

- A **plan** of the process, in a document in the project (`recipes/plans/`).
- The **process** itself as a draft in your project (`recipes/drafts/`), checked automatically for mistakes.
- A **walkthrough** in plain language, so you can judge the process without reading it. It lists each small program in the process (what it does, what it needs installed, what it may touch) and each part an AI helper does that a program could have done, with the trade.
- When you allowed programs, the **programs** themselves, each with its worked examples. Each is run on its examples before you see the result, and an independent reviewer checks it does only what the design says.

On a quick run, it produces only a **guide** in your project (`guides/`), which a quick run then follows.

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
