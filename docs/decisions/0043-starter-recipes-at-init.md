---
id: "0043"
title: "init vendors the starter recipes"
status: accepted
date: 2026-11-04
source: "inline note, §11.6"
sections: ["§11.6", "§13.1"]
---

# 0043. init vendors the starter recipes

## Context

A Director should be able to start with the owner immediately after `init`, without hand vendoring.

## Decision

`init` vendors the starter recipes (`fit-check` today) unless `--bare`, skipping any already vendored. What a machine still needs is a worker profile able to do the framing step.
