# Program review rubric

| Check | Typical severity |
|---|---|
| The program does more or less than the contract's `does`, or its inputs or `output.json` differ from the contract's schemas | high |
| It touches more than the contract's `reach` declares: files outside its output folder, the project when its workspace is `none`, the network when `network` is false, a secret it does not name | high |
| It uses a package the contract does not name, or imports one not pinned in its lock | high |
| It handles the awkward example by recognising that example (its values, its file name) instead of by a rule that covers every case like it | high |
| It starts a process that keeps running, keeps state between runs, or could give a different result for the same input (time, randomness, unordered iteration) | high |
| Input it cannot handle is not refused with a plain reason and exit 1 | medium |
| It is more than one program with one job: work that belongs in a separate software project | high |
| Its own tests, if any, check something the examples do not, or nothing at all | low |
