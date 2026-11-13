# `assess`: Score against the fit rubric

- Run: `r_20261101_ab12`
- Recipe: `fit-check@5`
- State: **passed**
- Attempts: 1

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:35.000000Z
- Packet: `748b3c858e3c078651a0308a5e9213b682c5dabf20062fb026384eeabd43c24e` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `profile` from `steps.describe.output`: `e7f8cf76a73732957d941ac6af1d9359a5a09ddf6136a21c0e808609c72cb25c`
  - input `rubric` from `static.rubric.md`: `fe0bafae615b9a0426e0ba89d69b98aad128ca31adb7ee743446830c9b4dfabf`
  - input `recipes` from `catalog.summaries`: `37517e5f3dc66819f61f5a7bb8ace1921282415f10551d2defa5c3eb0985b570`
- Result: completed at 2026-11-01T12:00:38.000000Z (`result.json` `cce6927d8cd58c6529d9e11e01d4805fb0888ad2fc7148c8a104630cc774c972`)
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
  "assessed_work": "Reviewing vendor contracts",
  "next_step": "Author a contract-review recipe.",
  "reasons": [
    {
      "basis": "stated",
      "leans": "baton",
      "reason": "a few per month",
      "row": "recurrence"
    }
  ],
  "verdict": "fits"
}
```
