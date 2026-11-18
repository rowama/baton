---
id: "0172"
title: "Baton's one software recipe is named software, designed fresh by recipe-builder with eng-process as evidence; commercial work is its highest ratings, with business concerns in other processes"
status: accepted
date: 2026-11-18
source: "Owner, 2026-11-18: \"I want to start from scratch on the software engineering recipe, but still have my old process carry weight, esp wrt lessons learned.\"; \"I was thinking that a commercial scope software would just be a maximally rated (under existing scale) software this is also part of a larger business oriented baton project; marketing handled by a different process.\"; \"Change name and use recipe-builder. I'll go with your recommendation for the commercial sw question.\""
sections: ["§5.7"]
---

# 0172. Baton's one software recipe is named software, designed fresh by recipe-builder with eng-process as evidence; commercial work is its highest ratings, with business concerns in other processes

## Context

Decision [0149](0149-one-software-recipe.md) made eng-process Baton's one software recipe, and `2026-11-eng-process-recipe` proposed porting the eng-process kit into Baton with a coverage table showing parity. Since then Baton has taken over most of what the kit's machinery did (packets, the event log, routing, gates, action permissions, waits, interaction requests), and recipe-builder can now design steps by their traits and build programs. The owner wants the software recipe designed from scratch, drawing on current practice (Horthy, gstack, Farley and others), with eng-process's lessons carrying weight, and wants recipe-builder put through its paces doing it.

## Decision

1. **The recipe is named `software`.** It is Baton's one software recipe; Decision 0149 is amended to name it, and its other terms stand.
2. **It is designed fresh, by a recipe-builder run.** eng-process is evidence, not a specification: its process, lessons and sources are inputs to the run, and every lesson and adopted practice is accounted for in a sources-and-lessons ledger (adopted, adapted or rejected, with a reason). There is no parity requirement.
3. **Commercial software is the recipe at its highest ratings,** usually within a larger business project. The four axes stay as they are (`discovery`, `coordination`, `assurance`, `release`).
4. **Product discovery about the software stays inside the recipe** (who uses it, the problem, how success is measured, scope). **Market and commercial work stays outside** (pricing, positioning, channels, marketing, launch messaging), in other processes; their results enter a software run as bound project documents, such as a product brief.
5. **`2026-11-eng-process-recipe` is abandoned,** superseded by `2026-11-software-recipe`.
