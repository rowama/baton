---
id: "0113"
title: "Profiles are generated only for text models meeting the adapter contract; the owner can exclude"
status: accepted
date: 2026-11-10
source: "change 2026-11-model-listings (owner, 2026-11-10: accepted the suggested answers)"
sections: ["§6.4"]
---

# 0113. Profiles are generated only for text models meeting the adapter contract; the owner can exclude

## Context

Hundreds of profiles are noise in eligibility lists and `doctor`.

## Decision

Only text models that meet the adapter's reply contract get profiles. Routing considers all of them; `workers status` summarises listing profiles by provider (counts, free count, cheapest per tier). The owner can hide providers or models from routing with an `exclude` preference, deleting nothing.
