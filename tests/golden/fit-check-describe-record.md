# `describe`: Profile the idea

- Run: `r_20261101_ab12`
- Recipe: `fit-check@2`
- State: **passed**
- Attempts: 2

## Attempt 1

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:11.000000Z
- Packet: `287697901e89bed56095d104e0a52a43e3bccdc67e677850931fd985be66164f` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:14.000000Z (`result.json` `70fca279c7635a58f862dcd473b07c4f4c26b82a605d2acbcdec34af72302393`)
- Rejected:
  - output (root): 'occurrence' is a required property
- Outcome: not accepted; ready for attempt 2

## Attempt 2

- Worker: `owner`, dispatched by director:alice@host1 at 2026-11-01T12:00:22.000000Z
- Packet: `d16b650a2459622991827d0f85e110702fc52c2e3923e42da9aba70174c82385` (worker profile `f318571584e4549a2c69d16523bef672ed295bce25dd2b7e42c18d086f690bf2`)
- Retry guidance: Fill in every occurrence field.
- Inputs:
  - input `idea` from `run.inputs.idea`: `867870c0b097c1d3983c49f69d1563b76116655255e7d973e766688bfdfdae5d`
- Result: completed at 2026-11-01T12:00:25.000000Z (`result.json` `fa222dd621f89e69ff392dc7691b229da86b9b0ab00cf7c884bf83ebc3068701`)
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
