# Score against the fit rubric

You are the worker for step `assess` (attempt 1) of a Baton run.
Do this step's work only, as described below, and report through the result files.

## Task

# Score against the fit rubric

Score the `profile` input against the `rubric` input, row by row. You are judging the work the
profile's `scope` names, using that work's own facts.

- Say in `assessed_work` which work you scored, in a sentence: developing a process, executing it,
  or other work, as `scope` states it. A `scope.target` is not scored.
- Give one reason per rubric row, saying which way the row leans and why, using the profile's own
  facts. Set `basis` to `stated` for a fact the owner or the project context gave, or `assumed`
  for one the profile lists under `assumptions`.
- Choose the verdict the rubric's balance supports: `fits`, `fits_per_occurrence` or
  `not_recommended`.
- Give the next step the rubric names for that verdict, made concrete for this work.

Do not add rows, weights or criteria the rubric does not contain. Frequency and duration are
signals, not cutoffs. Do not reject development work because of how the finished process will
run.

For `not_recommended`, name a simpler `alternative` that suits the work (a script, asking an
assistant directly, an existing tool, a manual procedure, or an operations engine). If the work
asked for was executing a process, you may offer, in `development_offer`, developing a suitable
process or system as a **separate** project; the owner has not asked for it, so say so, and do not
word the next step as if it had been chosen.

If a `recipes` input is given, it lists the recipes this project can already run, each with a
`scope` (what it covers and what it is not for) where the recipe has one. For `fits` or
`fits_per_occurrence`, set `recipe` to the one recipe whose scope or description covers the whole
of the assessed work, as `{id, version}`, and say so in the next step; set it to `null` when none
does, and the next step is then to author one. A recipe that covers only part of the work, or is
for a different kind of deliverable, does not cover it. Never name a recipe that is not in the
list. Leave `recipe` out for `not_recommended`.

If a `context` input is given, it summarizes an existing project the request is about. Use it to
choose the recipe: prefer the recipe whose steps produce what the project already has. Do not add
rubric rows for it, and do not claim to know which files exist beyond what it says.

## Inputs

### `profile`

File: `inputs/profile.json` (application/json)

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

### `rubric`

File: `inputs/rubric.md`

### `recipes`

File: `inputs/recipes.json` (application/json)

```json
[
  {
    "description": "An example.",
    "id": "example-recipe",
    "levels": [],
    "run_inputs": null,
    "scope": null,
    "vendored": false,
    "version": 1
  }
]
```

## Done when

- Write result/result.json (status, output, artifacts), echoing packet_sha256 from manifest.json.
- `output` validates against output_schema.json.
- Afterwards the owner is asked (by the runtime, not by you; do not report `blocked` for it): Accept this verdict and its suggested next step?

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
- Each question is `{"id", "ask", "why", "best_guess"?, "options"?: [{"id", "label"}], "multi_select"?,
  "priority"?: "needed" | "helpful"}`, written in the owner's terms (never this process's vocabulary).
  Infer what you reasonably can and offer it as `best_guess`; ask only what you cannot infer.
- Report friction with the process itself in `process_feedback`.

## Output schema

Also in `output_schema.json`.

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "required": [
    "verdict",
    "assessed_work",
    "reasons",
    "next_step"
  ],
  "properties": {
    "verdict": {
      "enum": [
        "fits",
        "fits_per_occurrence",
        "not_recommended"
      ]
    },
    "assessed_work": {
      "type": "string",
      "minLength": 1,
      "description": "The work scored: developing a process, executing it, or other work"
    },
    "reasons": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "row",
          "leans",
          "basis",
          "reason"
        ],
        "additionalProperties": false,
        "properties": {
          "row": {
            "enum": [
              "coordination",
              "dependent_reasoning",
              "recurrence",
              "duration",
              "record"
            ]
          },
          "leans": {
            "enum": [
              "baton",
              "against_baton"
            ]
          },
          "basis": {
            "enum": [
              "stated",
              "assumed"
            ],
            "description": "A fact the owner or context gave, or a listed assumption"
          },
          "reason": {
            "type": "string"
          }
        }
      }
    },
    "next_step": {
      "type": "string"
    },
    "alternative": {
      "type": "string",
      "minLength": 1,
      "description": "For not_recommended: a simpler approach that suits the work"
    },
    "development_offer": {
      "type": "string",
      "minLength": 1,
      "description": "For not_recommended on work to be executed: developing a suitable process or system, offered as a separate project the owner has not chosen"
    },
    "recipe": {
      "type": [
        "object",
        "null"
      ],
      "description": "For fits or fits_per_occurrence: the existing recipe that covers all of the assessed work; null when none does",
      "required": [
        "id",
        "version"
      ],
      "properties": {
        "id": {
          "type": "string"
        },
        "version": {
          "type": "integer"
        }
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false,
  "allOf": [
    {
      "if": {
        "properties": {
          "verdict": {
            "const": "not_recommended"
          }
        },
        "required": [
          "verdict"
        ]
      },
      "then": {
        "required": [
          "alternative"
        ],
        "not": {
          "required": [
            "recipe"
          ]
        }
      },
      "else": {
        "not": {
          "anyOf": [
            {
              "required": [
                "alternative"
              ]
            },
            {
              "required": [
                "development_offer"
              ]
            }
          ]
        }
      }
    }
  ]
}
```
