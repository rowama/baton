---
id: user.choose-models
title: Choose which models Baton may use
audience: owner
order: 30
summary: Filter the models table, turn models off, prefer cheaper or more proven ones, check that one works and what it can do, and let cheaper models earn work.
related: [user.connect-an-account, user.connect-a-subscription]
---

## Here, now {#here-now}

**Models** lists every model Baton can use through the accounts and subscriptions you connected. Use the filters above the table to narrow it: **free only**, a **maximum price**, a **capability**, a **tier** or a **provider**.

- The **Use** box at the start of a row turns that model on or off for Baton's choices. Unticked means Baton will not pick it. Tick **turned off** in the filters to list the ones you switched off.
- **Check it works** makes one real, small request to that model and records the result.
- **Check abilities** gives a model a few short tasks, once, to learn what it can really do. See [Check abilities](#check-abilities).
- **by cost** is on unless you turn it off: Baton picks what you already pay for first (a subscription such as Claude Code or Codex, while it has quota left), then free models, then the cheapest capable model. Turned off, Baton picks the most proven one first. When your assistant offers you a choice of model, it says what each costs: included in your subscription, free, or its price.

## Reading the table {#reading-the-table}

| Column | Meaning |
|---|---|
| Model | The provider's name for it, and Baton's short name for it underneath |
| Provider | Which provider, or subscription, reaches it |
| Price | What the provider lists, per million tokens in and out (a token is roughly a short word). **free** and **subscription** are shown as such. **unknown** means the provider did not say. **web search billed per search** means the provider also charges for each web search the model makes |
| Context | How much text it can take at once |
| Tier | How capable Baton believes it to be: a rough guide, not a promise. For most well-known models it comes from published, independent test results; see [Rate from published evaluations](#rate-from-evaluations). Underneath: how the model has done on real steps of each tier, and **put back at …** with **Promote** when it did badly; see [Try cheaper models](#try-cheaper-models) |
| Capabilities | What it can do, each marked **likely**, **verified** or **absent** |
| Checked | When a real request last confirmed it works, or **not yet**, and when its abilities were last checked, with what that cost |

## Likely, verified, absent {#likely-verified-absent}

A capability starts as **likely**: it should be there, and Baton uses it. When real work shows it, it becomes **verified**. If it fails to work, it becomes **absent** and Baton stops choosing that model for steps that need it. You never have to set these by hand; **Check it works** and **Check abilities** are only ways to confirm them early.

## Prefer a model for one kind of work {#prefer-a-model}

Above the table, **Prefer a model for…** lets you pick a capability, pick a model and choose **Save**. Baton tries that model first for steps that need that capability, and falls back to others if it cannot be used. These choices are kept for this computer.

## Check abilities {#check-abilities}

Most models start out unproven, so Baton keeps to the few it already trusts. **Check abilities** lets cheaper models earn real work. It gives each model a few short tasks, each with one right answer that Baton checks itself. No model marks another's work. The tasks cover:

- replying in the exact form asked for
- calling tools, and reading files it was pointed to
- following instructions for the length and layout of a piece of writing (not how well it is written)
- small reasoning problems

Use **Check abilities** on a row for one model, or **Check abilities of the shown** under the table for every model the filters show (for example, tick **free only** first). Baton first shows how many tasks it will run and roughly what they will cost at the provider's prices, and starts only when you agree. Checks take a few minutes. Free models cost nothing, and a subscription's checks are included in it.

Afterwards, each ability a model passed is **verified**. One it failed is **absent** (a task it gets wrong is given a second try first, so one slip does not count), and Baton stops choosing that model for work that needs it. If a check could not run, for example because the provider was busy or a free allowance was used up, nothing is recorded and the model is due for a check again. A model Baton knew little about may gain an ability it proved, such as calling tools. Writing and reasoning, and how capable Baton judges a model overall (its tier), are never decided by these short tasks.

A model is checked once. Baton skips models already checked unless Baton's tasks change, or the model's name can point to a different model over time. From a terminal: `baton workers check <model>`, `--free` or `--provider <account>`; add `--again` to repeat a check, and `--yes` to skip the question.

## Rate from published evaluations {#rate-from-evaluations}

A model's tier (basic, standard or strong) decides which steps Baton gives it. For most well-known models Baton takes the tier from published test results: the Artificial Analysis Intelligence Index, which tests the models itself on coding, science and reasoning work. A score of 50 or more is **strong**, 25 to 49 **standard**, and below 25 **basic**; standard or better also means the model can reason through technical work. Preference rankings such as LMArena are noted as support but never decide.

A model your account lists that Baton has no results for stays **basic**. Under the table, **Rate … unrated models from published evaluations** asks a strong model of yours that can search the web to look up those results for the models shown (up to ten at a time). Choose which model does the looking up. It costs one run of that model. Baton checks the answer itself: it computes the tier from the scores it was given and refuses any other, and it keeps the result for this computer only. From a terminal: `baton workers assess <model id> --profile <researcher>`.

## Try cheaper models {#try-cheaper-models}

A model that does well on Baton's short checks has still not done your real work. Above the table, **try cheaper models on steps below strong** lets it earn that. With it on, when your assistant gives a step to a model, Baton may first give it to a cheaper one that is rated for the step (a free one, or one cheaper than your assistant's choice). Your assistant tells you when it does. If the cheaper model's work does not pass the step's checks, your assistant's choice does the step again, and the cheaper model's try is not held against the step.

Only some steps are tried this way: steps that do not need a strong model, that say they change nothing or only things that can be undone, and that Baton can check (a check that runs, or a review by another model). A step that spends money, sends something, or might reach outside your computer is never tried. Each step of a run is tried at most once.

Baton keeps a record of how each model did on each kind of step:

- After 5 good tries at a tier, with none of the last 5 failed, a model is **proven** there and is no longer tried; it is used like any other model.
- After 2 failures in its last 5 tries at a tier, it is **put back**: Baton treats it as one tier lower until you promote it. Your assistant tells you when that happens. Tick **put back** in the filters to list these models; **Promote at …** on a row restores one. A new version of the model, a new route to it, or a new published rating gives it a fresh start on its own.

The **daily limit** caps what Baton may set aside each day for these tries, in US dollars. At $0, the default, only free models are tried. Before each paid try, Baton sets aside a cautious estimate of its cost and replaces it with the real cost afterwards, so two tries at once cannot both use the last of the limit. A provider can still charge more than the estimate. **shadow strong steps with one candidate** is the matching switch for steps that need a strong model; it takes effect once Baton supports it.

From a terminal: `baton workers assessment --trials` (or `--no-trials`) and `--daily-limit <dollars>`; `baton workers standing <model> --tier <tier> --promote` (or `--put-back`, or `--clear` to let the record decide again); `baton workers status` lists each model's record and the models put back.
