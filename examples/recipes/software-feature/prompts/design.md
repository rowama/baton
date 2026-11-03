# Technical design

Design how the change described in the `requirements_doc` input will be built. The plan
splits this design into slices, and an independent reviewer reads it against its rubric.

Write the `design_doc` artifact (Markdown) with these sections:

1. **Approach:** the shape of the solution in a few paragraphs, and why this shape.
2. **Components:** each module, interface or data format added or changed, and its
   responsibility.
3. **Data and interfaces:** schemas, signatures, formats, with compatibility notes for
   anything that already exists.
4. **Failure modes:** what can go wrong at runtime and how the design handles it.
5. **Testing:** how each requirement will be verified.
6. **Rollout:** migration, flags or ordering needed to ship safely; "none" if none.
7. **Alternatives considered:** at least one, and why it was not chosen.
8. **Open questions.**

Rules:
- Every numbered requirement must be covered by a component and by a test approach; say
  which.
- Prefer the smallest design that meets the requirements. Name trade-offs plainly.

In `output`, return `summary` and `open_questions`.
