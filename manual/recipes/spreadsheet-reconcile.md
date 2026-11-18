---
id: recipes.spreadsheet-reconcile
title: Spreadsheet reconcile
audience: owner
order: 60
summary: Compare two versions of a spreadsheet, see exactly what was added, removed and changed, and get it explained in plain words.
related:
- user.what-baton-may-do
- admin.recipes-and-vendoring
generated: true
---

## Here, now {#here-now}

Use **spreadsheet reconcile** when you have two versions of the same table, such as last month's and this month's price list or two exports of a customer list, and want to know exactly what changed. A small program compares them row by row, the same way every time, so the counts are exact. A helper then explains the differences in plain words, and you accept the report.

To use it, tell your assistant which two files to compare and which column identifies a row (an id, a code, an email address): "Compare March's price list with April's, by product id."

## What you will be asked {#what-you-are-asked}

- Before it is added to your project: whether the comparison program may run on your computer. Your assistant tells you what it does (it compares two tables), what it needs (Python, nothing else) and what it touches (only the two files you give it; no internet, no passwords).
- At the start: the two files, which must be saved as CSV, and the column that identifies a row. The files must be in your project, and you confirm that they are the versions to compare.
- At the end: **That's a fair account** or **Something's missing or wrong**. If something is wrong, say what, and the explanation is redone. The comparison itself is not redone, because it is exact.

## What it produces {#what-it-produces}

The counts (rows added, removed, changed and unchanged, and any columns added or removed), a list of every difference with its row and its old and new values, and a short report in plain words that points out patterns and anything that looks like a mistake. Nothing in your project's files is changed.

## What it needs {#what-it-needs}

Python 3.10 or newer on this computer, which Baton never downloads; and one ordinary helper to write the explanation. No coding assistant, no web access. If Python is missing, your assistant tells you before the comparison is due.

## The parts {#parts}

| Part | When | You are asked |
|---|---|---|
| Compare the two tables row by row | always | nothing |
| Explain the differences | always | Accept this report on what changed? |

It can build on documents your project already has. Before the work that needs one starts, you are shown the document proposed and asked to confirm it.

| Document | Needed | How many |
|---|---|---|
| The earlier version of the table, as a CSV file | yes | one |
| The later version of the same table, as a CSV file | yes | one |

## Example {#example}

> **Note:** You say: "Compare March's price list with April's, by product id." The program finds one product added, one removed and one price changed. The report says the apple went from 1.00 to 1.10, the pear was dropped and figs were added, and that a new stock column appeared. You choose **That's a fair account**.

## If it goes wrong {#if-it-goes-wrong}

- A file has no column with the name you gave, a row has no value in it, or the same value appears twice: the comparison stops and says which. Fix the file or choose another column, and your assistant tries again.
- A file is not saved as CSV with UTF-8: save it again as "CSV UTF-8" and try again.
- Python is not installed: see [what a recipe's programs need](admin.recipes-and-vendoring#programs).
