---
id: admin.accounts-and-costs
title: Accounts, subscriptions and who pays
audience: admin
order: 60
summary: How subscription and API accounts differ, how billing is kept separate, and how Baton prefers cheaper models.
related: [user.connect-an-account, user.connect-a-subscription, admin.secrets]
---

## Here, now {#here-now}

Baton uses two kinds of paid access, and keeps them apart so a job is always billed to the one you intended.

| | Subscription | API account |
|---|---|---|
| What | A coding assistant on its own login (Claude Code, Codex) | A key for a provider's model API, such as OpenRouter |
| Billed | By the plan | Per use, to the provider |
| Where it lives | The program's own stored login | A key on this machine: keyring or `~/.baton/secrets/` |
| Set up | Log in once; the setup page checks it | `baton workers connect` or the setup page |

## Keeping billing separate {#billing}

Helpers run in a constructed environment, not the caller's. A subscription profile removes the provider's API-key variables (`env_deny`), so a stray key in your environment cannot switch a login's billing to the API. `baton doctor` reports what each helper would really bill, and flags a login profile that would pick up a key.

## Connecting and removing accounts {#connecting}

```baton
baton workers connect openrouter
baton workers disconnect openrouter-main --forget-key
baton workers status
```

Connecting checks the key with one read of the provider's model list, stores it, declares the account and generates a helper for each model it lists. Disconnecting removes the account; its helpers stay recorded and flagged as no longer used. `baton workers disable` and `enable` stop and resume routing to an account's helpers without removing it. See [where keys are kept](admin.secrets#where-keys-are-kept).

## Price, free models and quota {#price-and-quota}

Each listed model carries the provider's price, and **free** and **subscription** are shown as such. A routing preference chooses cheapest first or most proven first (`baton workers prefs`). When a route's quota is used up, Baton routes around it until it resets (`~/.baton/quota.yaml`), and the setup page shows an account's credit or free allowance when the provider reports one.

## Reviewer independence {#independence}

Some recipes require a reviewer from a different maker than the author. Baton knows a profile's `vendor`, so that rule needs models from at least two makers; with only one, no reviewer is eligible and the owner is asked how to proceed.
