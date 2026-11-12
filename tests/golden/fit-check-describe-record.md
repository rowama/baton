# `describe`: Profile the idea

- Run: `r_20261101_ab12`
- Recipe: `fit-check@4`
- State: **passed**
- Attempts: 2

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:11.000000Z
- Packet: `385d173e38bd8b53f46711fd6a4297d0d7ed00e19b5819e47c0dc9ab0d9b71d0` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:14.000000Z (`result.json` `853f3bbdc461807caf2d1d63a84c6cf2c0e40e796c314f8fcaef2d1a17b56bc8`)
- Rejected:
  - output (root): 'occurrence' is a required property
- Outcome: not accepted; ready for attempt 2

## Attempt 2

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:22.000000Z
- Packet: `0948d16266a075cb387a6d8397775f6966542a5c3d5114abd13abf1ef258045f` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Retry guidance: Fill in every occurrence field.
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:25.000000Z (`result.json` `535c80bd9b62322a30c115252e1d5ed041cabfdd36f5c2a2795945d00ad4e2a4`)
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
