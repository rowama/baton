"""Propose an update to defaults/known-workers.yaml (maintainers only; §6.4, Decision 0083).

    python tools/worker-research/research.py --profile <name> [--home DIR] [--repo DIR] [--reports DIR] [--timeout S]

Runs the one-step ``worker-research`` recipe in a scratch Baton project and
dispatches it to ``--profile`` (a profile on this machine). The proposed file
is validated with ``baton.known_workers``; a proposal that adds or changes a
``verified`` entry is refused too, because research is not a live check. A
valid proposal replaces ``<repo>/defaults/known-workers.yaml`` for review with
``git diff``; the report is written to ``reports/<date>.md`` here. Anything
refused is saved under ``reports/`` and the repository file is left alone.

Exit codes: 0 written, 1 refused or the worker failed, 2 usage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def _baton():
    sys.path.insert(0, str(REPO / "src"))
    from baton import known_workers, vocab
    from baton.adapters import ADAPTERS
    from baton.data import load_yaml
    from baton.engine import Api
    from baton.project import init

    return known_workers, vocab, ADAPTERS, load_yaml, Api, init


def verified_entries(raw: Any) -> dict[tuple, Any]:
    out = {}
    for r in (raw or {}).get("routes") or []:
        if isinstance(r, dict) and r.get("verified") is not None:
            out[(r.get("provider"), r.get("adapter"), r.get("invocation"))] = r["verified"]
    return out


def check(proposal_text: str, current_text: str, repo: Path) -> list[str]:
    """Why a proposal is refused; empty when it may be written."""
    known_workers, vocab, ADAPTERS, _load_yaml, _Api, _init = _baton()
    import yaml

    try:
        raw = yaml.safe_load(proposal_text)
    except yaml.YAMLError as e:
        return [f"not YAML: {e}"]
    kw, issues = known_workers.validate(raw, vocab.load(vocab.DEFAULT), set(ADAPTERS), source="proposal")
    problems = [str(i) for i in issues]
    old = verified_entries(yaml.safe_load(current_text))
    new = verified_entries(raw)
    for key, value in new.items():
        if old.get(key) != value:
            problems.append(f"route {key}: research may not add or change verified (that records a live check)")
    for key in old:
        if key not in new and any((r.get("provider"), r.get("adapter"), r.get("invocation")) == key for r in (raw or {}).get("routes") or []):
            problems.append(f"route {key}: research may not remove verified")
    return problems


def report_markdown(output: dict[str, Any], today: str, profile: str, problems: list[str]) -> str:
    lines = [f"# Worker research, {today}", "", f"Worker profile: `{profile}`.", ""]
    if problems:
        lines += ["**Refused** (the repository file was not changed):", "", *[f"- {p}" for p in problems], ""]
    for key, title in (("inclusion_criteria", "Inclusion criteria"), ("providers_covered", "Providers covered"),
                       ("categories_covered", "Categories covered"), ("coverage_gaps", "Coverage gaps")):
        lines += [f"## {title}", "", *[f"- {x}" for x in output.get(key) or ["(none given)"]], ""]
    lines += ["## Changes", ""]
    for c in output.get("changes") or []:
        lines.append(f"- {c.get('what')}: {c.get('why')} ({', '.join(c.get('sources') or []) or 'no sources'})")
    if output.get("notes"):
        lines += ["", "## Notes", "", output["notes"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="research.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--profile", required=True, help="the worker profile to dispatch to")
    ap.add_argument("--home", help="the Baton home holding the profiles (default: BATON_HOME or ~/.baton)")
    ap.add_argument("--repo", default=str(REPO), help="the source checkout to update (default: this one)")
    ap.add_argument("--reports", default=str(HERE / "reports"), help="where the report goes (default: reports/ here)")
    ap.add_argument("--timeout", type=float, default=None, help="seconds to wait for the worker")
    ap.add_argument("--today", default=dt.date.today().isoformat(), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    known_workers, vocab, ADAPTERS, _load_yaml, Api, init = _baton()

    repo = Path(args.repo).resolve()
    target = repo / "defaults" / "known-workers.yaml"
    current = target.read_text(encoding="utf-8")
    voc = vocab.load(vocab.DEFAULT)
    machine_dependent = (_load_yaml(target) or {}).get("machine_dependent") or []
    inputs = {
        "title": f"Worker research {args.today}",
        "known_workers": current,
        "today": args.today,
        "adapters": sorted(ADAPTERS),
        "capabilities": {"capabilities": voc.capabilities, "tiers": voc.tiers, "machine_dependent": machine_dependent},
    }
    reports = Path(args.reports)
    scratch = Path(tempfile.mkdtemp(prefix="baton-worker-research-"))
    try:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=scratch, check=True)
        for k, v in (("user.email", "research@localhost"), ("user.name", "worker-research")):
            subprocess.run(["git", "config", k, v], cwd=scratch, check=True)
        init(scratch, bare=True)
        api = Api.open(scratch, director_id="worker-research@localhost", home=args.home)
        ref = api.vendor(HERE / "recipe")["recipe"]
        run = api.start(ref, inputs)["run_id"]
        out = api.dispatch(run, "research", args.profile, wait=True)
        if out.get("outcome") is None and args.timeout is not None:
            out = {**out, **api.wait(run, timeout=args.timeout)}
        if out.get("outcome") != "passed":
            print(f"The research step did not pass: {json.dumps({k: out.get(k) for k in ('outcome', 'reasons', 'worker_exit')})}", file=sys.stderr)
            return 1
        result = scratch / ".baton" / "runs" / run / "steps" / "research" / f"attempt-{out['attempt']}" / "result"
        doc = json.loads((result / "result.json").read_text(encoding="utf-8"))
        art = next(a for a in doc["artifacts"] if a["name"] == "known_workers")
        proposal = (result / art["path"]).read_text(encoding="utf-8")
        problems = check(proposal, current, repo)
        reports.mkdir(exist_ok=True)
        (reports / f"{args.today}.md").write_text(report_markdown(doc.get("output") or {}, args.today, args.profile, problems), encoding="utf-8")
        if problems:
            (reports / f"{args.today}.refused-known-workers.yaml").write_text(proposal, encoding="utf-8")
            print(f"Refused; nothing written to {target}. See {reports / (args.today + '.md')}:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        target.write_text(proposal, encoding="utf-8")
        print(f"Wrote {target} and {reports / (args.today + '.md')}. Review with git diff before committing.")
        return 0
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
