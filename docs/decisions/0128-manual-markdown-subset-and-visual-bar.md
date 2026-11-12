---
id: "0128"
title: "The manual is a restricted Markdown subset, rendered by a small shipped renderer, to a clean, professional, modern standard"
status: accepted
date: 2026-11-11
source: "change 2026-11-user-help (owner, 2026-11-11: concur)"
sections: ["§13.9", "§13.9"]
---

# 0128. The manual is a restricted Markdown subset, rendered by a small shipped renderer, to a clean, professional, modern standard

## Context

Open question 3. The suggestion was a restricted Markdown subset with a small renderer shipped with the page, no new dependency and no build step. The owner (2026-11-11) concurred on the condition that it looks clean, professional and modern in the web UI.

## Decision

- The manual uses a subset (headings with explicit ids, paragraphs, lists, tables, code blocks, links, notes and warnings) that a check enforces; a small renderer in the front end shows it. No runtime dependency, no build step.
- Visual bar, part of acceptance: a considered type scale and reading width, a persistent navigation and search, an on-this-page outline, clear code blocks with copy, notes that are visually distinct, light and dark themes following the system, phone to wide-desktop layouts, visible keyboard focus, accessible contrast. Slice 2 is accepted only after the owner has seen it running.
