Two versions of a table were compared row by row by a program. You have its counts and its list of differences (`differences`: one line per added row, removed row, or changed cell, with the row's key, the column, and the values before and after). The owner may have said what they want to learn (`purpose`).

Explain the differences to the owner in plain words:

- `summary`: two or three sentences on what changed overall, using the counts exactly as given. Never recount or estimate.
- `highlights`: the changes most worth their attention, each naming the row by its key and saying what changed. Prefer patterns (many prices raised by the same amount, a whole region removed) over single rows, and say how many rows each pattern covers.
- `questions`: changes that look like mistakes (a value emptied, a number changed by a factor of ten, the same row removed and added under a new key), each with its key, or none.

Write the report artifact as a short Markdown document for the owner: the summary, the counts as a small table, the highlights, then any questions. Report only what the differences show; never infer reasons the data does not give.
