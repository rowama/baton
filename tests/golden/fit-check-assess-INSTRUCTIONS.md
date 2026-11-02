# Score against the fit rubric

You are the worker for step `assess` (attempt 1) of a Baton run.
Do this step's work only, as described below, and report through the result files.

## Task

# Score against the fit rubric

Score the `profile` input against the `rubric` input, row by row.

- Give one reason per rubric row, saying which way the row leans and why, using the
  profile's own facts.
- Choose the verdict the rubric's balance supports: `fits`, `fits_per_occurrence`
  or `operations_engine`.
- Give the next step the rubric names for that verdict, made concrete for this idea.

Do not add rows, weights or criteria the rubric does not contain.

## Inputs

### `profile`

File: `inputs/profile.json` (application/json)

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
  "summary": "Weekly vendor contract review"
}
```

### `rubric`

File: `inputs/rubric.md`

## Done when

- Write result/result.json (status, output, artifacts), echoing packet_sha256 from manifest.json.
- `output` validates against output_schema.json.
- The owner approves: Accept this verdict and its suggested next step?

## Protocol

- This directory is the packet. Do not modify anything in it.
- Write results only to `../result/` (relative to this packet directory): artifacts under
  `../result/artifacts/`, then `../result/result.json` **last**.
- Do not read or modify the project working tree.
- `result.json` is a JSON object:

```json
{
  "protocol": "baton-packet/1",
  "packet_sha256": "<copy from manifest.json>",
  "status": "completed | blocked | failed",
  "output": "<an object matching output_schema.json>",
  "artifacts": [
    {
      "name": "<declared artifact name>",
      "path": "artifacts/<file>"
    }
  ],
  "notes": "",
  "questions_for_human": [],
  "process_feedback": []
}
```

- Use `blocked` with `questions_for_human` when only the owner can answer something; `failed` when
  you cannot do the step. Never guess or improvise around a mismatch: report it.
- Report friction with the process itself in `process_feedback`.

## Output schema

Also in `output_schema.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "verdict",
    "reasons",
    "next_step"
  ],
  "properties": {
    "verdict": {
      "enum": [
        "fits",
        "fits_per_occurrence",
        "operations_engine"
      ]
    },
    "reasons": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "row",
          "leans",
          "reason"
        ],
        "properties": {
          "row": {
            "enum": [
              "occurrences",
              "judgment",
              "duration",
              "audit_trail"
            ]
          },
          "leans": {
            "enum": [
              "baton",
              "operations_engine"
            ]
          },
          "reason": {
            "type": "string"
          }
        },
        "additionalProperties": false
      }
    },
    "next_step": {
      "type": "string"
    }
  },
  "additionalProperties": false
}
```
