# `describe`: Profile the idea

- Run: `r_20261101_ab12`
- Recipe: `fit-check@5`
- State: **passed**
- Attempts: 2

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:11.000000Z
- Packet: `c4bf938880f547e26fe8dc25091fd253c910c5c75f023bd5924eeab228dd9e0e` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:14.000000Z (`result.json` `f9140bb362e0d05d63bd7b6da878f5c0a33a786d9171fb48a7a12fbc7f834666`)
- Rejected:
  - output (root): 'scope' is a required property
  - output (root): 'work' is a required property
- Outcome: not accepted; ready for attempt 2

## Attempt 2

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:22.000000Z
- Packet: `ca9787b0d7a01cc43acd5b72f938ee684f3703a8fa11c4d325c792d842088c38` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Retry guidance: Fill in every occurrence field.
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:25.000000Z (`result.json` `b3ef1e20c39c639710eda324e04ee846246a5df983423c3d90262a7868f6fce4`)
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
