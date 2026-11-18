# Build the program to its examples

You build one program, `program` (its id in `program.program`), for the process drafted in
`recipes/drafts/<run slug>/` (`generated` says where). Its contract is in
`programs/<id>/contract.json` and in the approved design (`shaped`): what it does, its inputs file and
its `output.json` (the schemas), what it may touch, and the packages it may use. Its examples are in
`programs/<id>/examples/`: the owner's own, or drafted and approved by the owner. They are what the
program must do. You may not change them: a changed example fails your attempt.

1. Write the program named in `programs/<id>/program.yaml`'s `entry` (`programs/<id>/<id>.py`, and other files
   in the program's folder if it needs them). It reads the inputs file named by its first argument (one
   JSON object keyed by input name; a file input is `{"path", "media_type"}`), writes `output.json`
   (a JSON object) and any declared artifacts into the folder named by its second argument, and
   nothing else. On input it cannot handle it prints a plain reason on stderr and exits 1. It starts
   nothing that keeps running, keeps no state between runs and gives the same result every time.
2. Use only the packages the contract names. Pin them in `programs/<id>/requirements.lock` with exact
   versions and hashes: `uv pip compile --generate-hashes`, which needs the network. If you cannot
   reach the network, return `blocked` and say so. A program with no packages keeps the lock empty.
3. Handle the awkward example for the reason it is awkward, by a rule that covers every case like
   it, never by recognising the example.
4. You may add tests of your own in `programs/<id>/tests/`. They help you; only the examples decide.
5. Run `baton programs test recipes/drafts/<run slug> --program <id> --repeat 2 --require-examples` and
   fix the program until every example passes twice. The runtime runs it again as a gate, then
   `baton recipe check`, which holds the program to its contract's reach and packages and to 600
   lines of code unless the contract says why it is more.

`open_findings`, when given, are the reviewer's findings and the failures of the last round, and
the owner's note when they asked for another try: fix each one. Commit your work. Return the commit,
the program, each example it passes with what it `says` in the owner's terms, what it `needs`
installed and what it `touches`, in the owner's terms, and a short summary.
