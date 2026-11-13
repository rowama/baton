# `describe`: Profile the idea

- Run: `r_20261101_ab12`
- Recipe: `fit-check@5`
- State: **passed**
- Attempts: 2

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:11.000000Z
- Packet: `cd093e67ac02ed8c47844ef0712adbb7814a4bf5ec31f1df49c746d981548b3f` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:14.000000Z (`result.json` `ac16c1d12cca1304ba87f9df744b306c5d1804c3215acc4d98feebc8d6f1a33e`)
- Rejected:
  - output (root): 'scope' is a required property
  - output (root): 'work' is a required property
- Outcome: not accepted; ready for attempt 2

## Attempt 2

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:22.000000Z
- Packet: `4610a326df1b163ca40d73d3d9d96e52c550bf913599f9b59049e0f57bc9fc45` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Retry guidance: Fill in every occurrence field.
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:25.000000Z (`result.json` `09ec114fadc466b07889bb18e56b09bdddcf79109656a86a6c54d17d46e27c1a`)
- Gates:
  - provenance: passed
  - 0 schema: passed
- Outcome: **passed** at 2026-11-01T12:00:29.000000Z

## Accepted output

```json
{
  "scope": {
    "kind": "executing_a_process",
    "statement": "Review each vendor contract before signing."
  },
  "summary": "Vendor contract review",
  "work": {
    "bulk_processing": false,
    "dependent_reasoning": "high",
    "duration": "two days",
    "frequency": "a few per month",
    "handoffs": true,
    "human_signoffs": true,
    "judgment": "high",
    "latency_sensitive": false,
    "live_integration": false,
    "participants": [
      "legal agent",
      "owner"
    ],
    "record_value": "benefit"
  }
}
```
