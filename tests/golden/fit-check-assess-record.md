# `assess`: Score against the fit rubric

- Run: `r_20261101_ab12`
- Recipe: `fit-check@3`
- State: **passed**
- Attempts: 1

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:35.000000Z
- Packet: `e656a4e170ad25e0774cc7e5afe78ec72eadba61e3fa606439cb663ef3d28eb9` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `profile` from `steps.describe.output`: `52eb5f0df293945773533ebf48fbaed310e1f0ebf1bf7fcb9fb04a689e6ffaa1`
  - input `rubric` from `static.rubric.md`: `b4698d1a640c8eec723f018c81c03c1f4ad18f21fb214e4ce3ca069bf0230e94`
  - input `recipes` from `catalog.summaries`: `2fe16bb220fb97b06fc34009ca528cd83c3d4046359e87c885f565dfb05c7bcb`
- Result: completed at 2026-11-01T12:00:38.000000Z (`result.json` `3d91ec23e3457cd2a51fe87f6d4384b98dc55e0200da42d0abb5c0e6a4549b6f`)
- Gates:
  - provenance: passed
  - 0 schema: passed
  - 1 human: opened — Accept this verdict and its suggested next step?
  - Owner decision, recorded by director:alice@host1: **approve** — "Agreed; author the recipe."
  - 1 human: passed
- Outcome: **passed** at 2026-11-01T12:00:46.000000Z

## Accepted output

```json
{
  "next_step": "Author a contract-review recipe.",
  "reasons": [
    {
      "leans": "baton",
      "reason": "a few per month",
      "row": "occurrences"
    }
  ],
  "verdict": "fits"
}
```
