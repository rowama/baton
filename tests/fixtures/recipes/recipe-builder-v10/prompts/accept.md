# Check the finished process with the owner

The `walkthrough` input describes the finished process in plain language. Read it as the person who
will follow it: does it do what they asked for, and is what it leaves out acceptable? Return
`accepted` (true or false) and `notes`: what you checked and, if you would not accept it, what is
missing. The owner then decides; a rejection sends it back with their note.

When `programs` is given, it holds each program built to the owner's examples: which examples it passed,
in the owner's terms, what it needs installed and what it may touch. Check that each is what the
walkthrough says, and say in `notes` for each program what it passed.
