---
id: "0073"
title: "A process plan's goal slug is shortened by rule, never summarized"
status: accepted
date: 2026-11-06
source: "change 2026-11-framing-perspective (owner, 2026-11-06)"
sections: ["§11.6"]
---

# 0073. A process plan's goal slug is shortened by rule, never summarized

## Context

The process plan's file name comes from the owner's opening words (0069). The first rule cut the slug at 40 characters, at a word. A request's lead-in ("I want to start a", "help me build a", "I need a") used up about half of that, so two goals that open alike could share a name and conflict, and accented letters were split ("möchte" became `m-chte`). A real summary would need the framing worker to supply a title, changing its output, which 0068 avoids.

## Decision

The goal slug is built from the owner's words, mechanically:

1. Accents are folded to plain letters (ö→o), then the words are slugged as before.
2. At most 40 characters: kept whole, lead-in included.
3. Longer: the lead-in is cut, meaning the leading run of subject pronouns, wanting or asking verbs, action verbs and articles (`frame.LEAD_WORDS`). If every word is lead-in, none are cut.
4. Still longer: common words (`frame.COMMON_WORDS`: articles, conjunctions, prepositions, possessives) are dropped anywhere, and the rest is cut at the last whole word within 40 characters (a single longer word is cut at 40).

It is never summarized. Two goals that still share a name conflict under §10.4, as before.
