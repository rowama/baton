# Choose how each tool's examples will come

This part is the owner's. The approved design (`shaped`) lists, for each tool to be built properly
(`tool.kind: engineered`), the examples it should be built to (`examples_needed`): what goes in,
what should come out, and which one is the awkward case. The tools are built to these examples and
to nothing else, so they decide whether the tools do what the owner means.

For each such tool, with the owner:

1. Read out what it needs, in their terms, from `examples_needed`.
2. Ask them to supply at least three good examples of their own, one of them a case they find
   awkward: real files that go in, and the result they expect. Make the folders
   `examples/<tool>/<example>/` in the project and say what goes in each.
3. If they would rather supply fewer, or none, tell them plainly: three good examples are the
   minimum, and with fewer the tool is more likely to differ from what they expect. They may still
   go ahead; the builder then drafts the missing ones, and they approve each drafted example before
   anything is built. Record their words.
4. When they have put their files in place, record that they vouch for them (`attest`, with their
   words) and bind them to this run's role `examples` (`bind <run> examples <paths…>`). Bind every
   tool's files in one binding.

Return `tools`: for each tool, how many examples the owner `supplied` and how many are to be
`drafted`; when any are drafted, `warned: true` and the owner's words (`owner_words`). Hand this in
only once the owner's files are bound.
