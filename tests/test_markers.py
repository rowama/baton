"""The `slow` marker cannot drift (§17, change 2026-11-fast-tests).

A test file that spawns processes must say, for every test, whether it is `slow` or quick (`not_slow` with a reason).
The quick gate leaves out `slow` tests only; the full suite never deselects anything.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

TESTS = Path(__file__).parent
SPAWNING = re.compile(r"\bsubprocess\b|sys\.executable|\b(harnesskit|realkit|versionkit)\b")


def _marks(nodes) -> list[ast.expr]:
    out = []
    for n in nodes:
        out.extend(n.elts if isinstance(n, ast.List) else [n])
    return out


def _mark_names(exprs) -> dict[str, ast.expr]:
    found = {}
    for e in exprs:
        target = e.func if isinstance(e, ast.Call) else e
        if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Attribute) and target.value.attr == "mark":
            found[target.attr] = e
    return found


def _module_marks(tree: ast.Module) -> dict[str, ast.expr]:
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in n.targets):
            return _mark_names(_marks([n.value]))
    return {}


def _tests(body, prefix=""):
    for n in body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test"):
            yield prefix + n.name, n
        elif isinstance(n, ast.ClassDef):
            yield from _tests(n.body, prefix + n.name + "::")


def test_every_test_in_a_process_spawning_file_is_marked_slow_or_not_slow_with_a_reason():
    problems = []
    for path in sorted(TESTS.glob("test_*.py")):
        src = path.read_text(encoding="utf-8")
        if path == Path(__file__) or (not SPAWNING.search(src) and not path.name.startswith("test_live")):
            continue
        tree = ast.parse(src)
        module = _module_marks(tree)
        for name, fn in _tests(tree.body):
            marks = {**module, **_mark_names(fn.decorator_list)}
            if "slow" in marks:
                continue
            nm = marks.get("not_slow")
            if nm is None:
                problems.append(f"{path.name}::{name}: neither slow nor not_slow(reason)")
            elif not (isinstance(nm, ast.Call) and nm.args and isinstance(nm.args[0], ast.Constant) and str(nm.args[0].value).strip()):
                problems.append(f"{path.name}::{name}: not_slow needs a reason")
    assert not problems, "mark these tests (see §17 Test tiers):\n" + "\n".join(problems)
