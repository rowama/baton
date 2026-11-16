"""Compare two CSV tables on a key column (the spreadsheet-reconcile recipe's tool).

Usage: python csv_diff.py <inputs.json> <output folder>

Reads `before` and `after` (files) and `key` (a column name) from the inputs
file, and writes `output.json` (counts) and `differences.csv` (one line per
added row, removed row or changed cell: change, key, column, before, after).
A missing key column, an empty key or a key that appears twice is an error:
the program says which, and exits 1.
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def read(path: str, key: str, which: str) -> tuple[list[str], dict[str, dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = list(reader.fieldnames or [])
        if key not in columns:
            raise SystemExit(f"the {which} table has no column {key!r} (its columns: {', '.join(columns) or 'none'})")
        rows: dict[str, dict[str, str]] = {}
        for n, row in enumerate(reader, start=2):
            k = (row.get(key) or "").strip()
            if not k:
                raise SystemExit(f"the {which} table has a row with an empty {key!r} (line {n})")
            if k in rows:
                raise SystemExit(f"the {which} table has {key!r} {k!r} twice (line {n}); a key must identify one row")
            rows[k] = {c: (row.get(c) or "") for c in columns}
    return columns, rows


def compare(before: tuple[list[str], dict], after: tuple[list[str], dict], key: str) -> tuple[dict, list[list[str]]]:
    (cols_b, rows_b), (cols_a, rows_a) = before, after
    shared = [c for c in cols_b if c in cols_a and c != key]
    diffs: list[list[str]] = []
    by_column: dict[str, int] = {}
    added = [k for k in rows_a if k not in rows_b]
    removed = [k for k in rows_b if k not in rows_a]
    changed = 0
    for k in rows_b:
        if k not in rows_a:
            continue
        cells = [c for c in shared if rows_b[k][c] != rows_a[k][c]]
        if cells:
            changed += 1
        for c in cells:
            by_column[c] = by_column.get(c, 0) + 1
            diffs.append(["changed", k, c, rows_b[k][c], rows_a[k][c]])
    diffs = [["added", k, "", "", ""] for k in added] + [["removed", k, "", "", ""] for k in removed] + diffs
    out = {
        "key": key, "rows_before": len(rows_b), "rows_after": len(rows_a),
        "added": len(added), "removed": len(removed), "changed": changed,
        "unchanged": len(rows_b) - len(removed) - changed,
        "columns_added": [c for c in cols_a if c not in cols_b],
        "columns_removed": [c for c in cols_b if c not in cols_a],
        "changed_by_column": dict(sorted(by_column.items())),
    }
    return out, diffs


def main(argv: list[str]) -> int:
    inputs = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out_dir = Path(argv[2])
    key = inputs["key"]
    try:
        before = read(inputs["before"]["path"], key, "earlier")
        after = read(inputs["after"]["path"], key, "later")
    except SystemExit as e:
        print(f"csv_diff: {e}", file=sys.stderr)
        return 1
    except UnicodeDecodeError as e:
        print(f"csv_diff: a table is not UTF-8 text ({e}); save it as CSV UTF-8 and try again", file=sys.stderr)
        return 1
    result, diffs = compare(before, after, key)
    with (out_dir / "differences.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["change", "key", "column", "before", "after"])
        w.writerows(diffs)
    (out_dir / "output.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
