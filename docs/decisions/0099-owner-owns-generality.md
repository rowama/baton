---
id: "0099"
title: "The owner owns a recipe's generality; the builder defaults to the narrowest rung and always shows the next"
status: accepted
date: 2026-11-09
source: "change 2026-11-recipe-builder (owner, 2026-11-09)"
sections: ["§5.1", "§11.6"]
---

# 0099. The owner owns a recipe's generality; the builder defaults to the narrowest rung and always shows the next

## Context

A new recipe is cheap, and the owner may never share it, so the builder must not push toward reuse. But a bare narrow default would hide the wider option from an owner who gave no signal.

## Decision

The owner decides how general a recipe is. The builder proposes the narrowest rung that covers the jobs the owner named. The goal confirmation the owner already gets states that rung and names the next one in a single clause (for example: "This covers flower beds. Say so if you'd want it to handle any garden bed or a shed too."), so it adds no question and no exchange. The builder recommends a wider rung only on a signal in the owner's words. The walkthrough always lists what the recipe covers and does not. If the owner picks a wider rung, `audit` checks both too narrow and too broad. The builder never widens a recipe for the sake of the catalog.
