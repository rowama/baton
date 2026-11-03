# Accept the slice

You are checking whether this slice is done, as the person who will use it.

The slice is in the `slice` input (its outcome and criteria, or the original request for a
minor change); the independent review is in the `review` input.

Check only what you can check now against what is live in your working copy:
1. Check out or pull the slice's commit and try each criterion yourself, or watch its test
   run. Note how you confirmed each one.
2. Read any open review findings and decide whether they matter to you.

Return `accepted` (true or false) and `notes`: what you checked, how, and, if you would
not accept it, what is missing. The owner then accepts or rejects the slice; a rejection
sends it back to implementation with the owner's note.
