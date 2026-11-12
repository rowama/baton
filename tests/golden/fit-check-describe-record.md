# `describe`: Profile the idea

- Run: `r_20261101_ab12`
- Recipe: `fit-check@4`
- State: **passed**
- Attempts: 2

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:11.000000Z
- Packet: `8b7300f085ec300204451c11ad2ea452938a48dbdffda77979f4ccb9f9006337` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:14.000000Z (`result.json` `f1549a6365691c446c7184eb65cd7056a3038de543fc47681a6aaa12997fc8fa`)
- Rejected:
  - output (root): 'occurrence' is a required property
- Outcome: not accepted; ready for attempt 2

## Attempt 2

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:22.000000Z
- Packet: `385d551bf6fa16a8d2589b37a92f6beb137f28210eb3e65579ff75c70c5d32a3` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Retry guidance: Fill in every occurrence field.
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:25.000000Z (`result.json` `c8e4331217e364a8c05b8aa7f5e3fd81083c965d7e880f867aad2657e088a272`)
- Gates:
  - provenance: passed
  - 0 schema: passed
- Outcome: **passed** at 2026-11-01T12:00:29.000000Z

## Accepted output

```json
{
  "occurrence": {
    "audit_trail": "benefit",
    "duration": "two days",
    "frequency": "a few per month",
    "human_signoffs": true,
    "judgment": "high",
    "latency_sensitive": false,
    "live_integration": false,
    "participants": [
      "legal agent",
      "owner"
    ]
  },
  "summary": "Vendor contract review"
}
```
