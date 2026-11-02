# Owner communication contract

The Director follows this file exactly when it talks to the owner. It belongs to
the project: edit it to suit how you want to be told things.

## Shape of every message

1. A brief status, or none at all.
2. A labeled list of the owner's actions, one step per line. Each pasteable
   command stands alone in its own code block.
3. The single decision owed, if any.

With nothing for the owner to do, write one line: "No action needed."

## Rules

- **Placeholders** are never valid shell syntax: write `PASTE_TOKEN_HERE`, never `$TOKEN`.
- **First mention** of anything new the owner must do or understand says where it
  lives (product, UI path, file or CLI), what it does, and the exact value or action.
- **Manual verification** lists only steps runnable against what is live now, each
  with how readiness was confirmed. Blocked steps say what unblocks them.
- **A reversed default** gets a one-line "Before → After".
- **Risk mitigations the agents propose** are a decision for the owner, with their
  cost and a narrower alternative; never absorbed silently.
- **Healthy progress** is reported briefly or not at all.
