# Clarify requirements

Turn the request in the `feature_request` input into requirements the rest of the process
can rely on: the plan, the slices and their acceptance are checked against what you write.

Write the `requirements_doc` artifact (Markdown) with these sections:

1. **Problem:** who needs this and why, in a few sentences.
2. **Behaviour:** what must be true when the change is done, as numbered, testable
   statements ("When a signed-out user opens /settings, they are sent to /login").
3. **Out of scope:** what this change deliberately does not do.
4. **Constraints:** compatibility, performance, security or platform limits that apply.
5. **Open questions:** anything the request leaves undecided.

Rules:
- Stay at the level of behaviour. Do not choose modules, libraries or data structures;
  that is design work.
- Do not invent requirements the request does not support. If something essential is
  missing, list it under open questions; if you cannot write useful requirements without
  an answer, ask through `questions_for_human` and set `status` to `blocked`.

In `output`, return `summary` (two or three sentences) and `open_questions` (the same list
as the document's last section).
