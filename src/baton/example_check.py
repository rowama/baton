"""``baton programs examples``: an engineered program's examples are enough, and the owner's are exact copies (§5.9; Decision 0164).

Recipe builder's ``examples`` step places each engineered program's examples
before anything is implemented: the owner's files copied byte for byte, and
any example the owner chose not to supply drafted for their approval. Each
example says where it came from in ``about.json`` (``programs.load_examples``).
This check is the step's gate, so the rules are code (§0 rule 2):

- an engineered program (one with ``contract.json``) has at least
  ``MIN_EXAMPLES`` examples, one of them marked ``awkward``, each with
  ``about.json``;
- an example from the owner has every file under ``inputs/`` and
  ``expected/`` listed in ``from``, and each listed file is byte-identical to
  the document of that path the run bound to the role (the sha256 the
  binding recorded, §8.6).

It reports, for the owner's approval gate, the examples that were drafted and
the owner's examples whose JSON (``expected.json``, ``input.json``) was
written from their words rather than copied. It judges nothing else; whether an example is good is the
owner's call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from .programs import EXAMPLE_ARTIFACTS, EXAMPLE_EXPECTED, EXAMPLE_INPUTS, LoadedProgram, file_sha256

#: The fewest examples an engineered program is built to (Decision 0164, item 2).
MIN_EXAMPLES = 3
ROLE = "examples"


@dataclass
class ExamplesReport:
    program: str
    examples: int = 0
    problems: list[str] = field(default_factory=list)
    drafted: list[str] = field(default_factory=list)  # for the owner to approve
    stated: list[str] = field(default_factory=list)  # the owner's examples with JSON (expected.json, input.json) written from their words

    @property
    def ok(self) -> bool:
        return not self.problems

    def as_dict(self) -> dict[str, Any]:
        return {"program": self.program, "ok": self.ok, "examples": self.examples, "problems": self.problems,
                "drafted": self.drafted, "stated": self.stated}


def bound_documents(events: list[Any], role: str = ROLE) -> dict[str, str] | None:
    """``{path: sha256}`` of the documents the run last bound to ``role``, or ``None`` when it bound none."""
    found = None
    for e in events:
        if e.type == "project_input_bound" and e.data.get("role") == role:
            found = e
    if found is None:
        return None
    return {_norm(d["path"]): d["sha256"] for d in found.data.get("documents", [])}


def _norm(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).as_posix()


def check_examples(programs: dict[str, LoadedProgram], bound: dict[str, str] | None, *, only: str | None = None) -> list[ExamplesReport]:
    """A report per engineered program (or ``only`` that program); ``bound`` from ``bound_documents``, ``None`` when unknown."""
    if only is not None and only not in programs:
        raise KeyError(only)
    out: list[ExamplesReport] = []
    for tid, program in sorted(programs.items()):
        if (only is not None and tid != only) or (only is None and not program.engineered):
            continue
        rep = ExamplesReport(tid, len(program.examples))
        out.append(rep)
        if not program.engineered:
            rep.problems.append(f"program {tid!r} has no contract.json: this check is for engineered programs")
            continue
        if len(program.examples) < MIN_EXAMPLES:
            rep.problems.append(f"{len(program.examples)} example{'s' if len(program.examples) != 1 else ''}; "
                                f"at least {MIN_EXAMPLES} are needed, the owner's or drafted and approved")
        if program.examples and not any((ex.about or {}).get("awkward") for ex in program.examples):
            rep.problems.append("no example is marked awkward (\"awkward\": true in about.json)")
        for ex in program.examples:
            where = f"example {ex.name!r}"
            about = ex.about
            if about is None:
                rep.problems.append(f"{where}: no about.json saying where it came from")
                continue
            if about.get("source") == "drafted":
                rep.drafted.append(ex.name)
                continue
            copied = {k: _norm(v) for k, v in (about.get("from") or {}).items()}
            if EXAMPLE_EXPECTED not in copied or ex.values:  # JSON written from the owner's words
                rep.stated.append(ex.name)
            files = sorted(f"{d}/{p.name}" for d in (EXAMPLE_INPUTS, EXAMPLE_ARTIFACTS) if (ex.root / d).is_dir()
                           for p in (ex.root / d).iterdir() if p.is_file())
            for rel in files:
                if rel not in copied:
                    rep.problems.append(f"{where}: {rel} is not listed in about.json `from`; the owner's files are copied, never written")
            for rel, src in sorted(copied.items()):
                if bound is None:
                    rep.problems.append(f"{where}: cannot prove {rel} is the owner's file without the run's binding of "
                                        f"'{ROLE}' (pass --run, or bind the owner's files first)")
                    break
                if src not in bound:
                    rep.problems.append(f"{where}: {rel} names {src}, which is not a document bound to '{ROLE}'")
                elif file_sha256(ex.root / rel) != bound[src]:
                    rep.problems.append(f"{where}: {rel} differs from the bound document {src}; the owner's files are copied byte for byte")
    return out
