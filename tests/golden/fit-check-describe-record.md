# `describe`: Profile the idea

- Run: `r_20261101_ab12`
- Recipe: `fit-check@1`
- State: **passed**
- Attempts: 2

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:10.000000Z
- Packet: `69c39ab1d7e122911cae7ae8aa8d0242c3b964dccc67e136bc328b31be3f4b64` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:13.000000Z (`result.json` `119b14d2f6064aa2c83536108203fb575e9d27da978d9d04b1c573beb9c1c258`)
- Rejected:
  - output (root): 'occurrence' is a required property
- Outcome: not accepted; ready for attempt 2

## Attempt 2

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:20.000000Z
- Packet: `c18bb458a1c490805a25f75b1e9f3e3b3b2d390af8460a405aa57b881bb36d3d` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Retry guidance: Fill in every occurrence field.
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:23.000000Z (`result.json` `7f1bb8666d9ec0b9e7f56b543afba6ef6d945ff52ffbe5fcc0a2d23922f8ad94`)
- Gates:
  - provenance: passed
  - 0 schema: passed
- Outcome: **passed** at 2026-11-01T12:00:27.000000Z

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
