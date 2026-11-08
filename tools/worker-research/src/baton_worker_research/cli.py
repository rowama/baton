"""Propose an update to defaults/known-workers.yaml (maintainers only; §6.4, Decision 0083).

    baton-worker-research --profile <name> [--home DIR] [--repo DIR] [--reports DIR] [--timeout S]

Installed from a source checkout with ``uv tool install --editable tools/worker-research``.

Runs the one-step ``worker-research`` recipe in a scratch Baton project and
dispatches it to ``--profile`` (a profile on this machine). The proposed file
is validated with ``baton.known_workers``; a proposal that adds or changes a
``verified`` entry is refused too, because research is not a live check. A
valid proposal replaces ``<repo>/defaults/known-workers.yaml`` for review with
``git diff``; the report is written to ``<repo>/tools/worker-research/reports/<date>.md``.
``--repo`` defaults to the checkout this package was installed from. Anything
refused is saved under ``reports/`` and the repository file is left alone.

``--check FILE`` validates a proposal file the same way and stops; the worker is
given it as a command to run on its own proposal. Exit codes: 0 written (or
accepted), 1 refused or the worker failed, 2 usage.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
RECIPE = HERE / "recipe"
KNOWN_WORKERS = Path("defaults") / "known-workers.yaml"
REPORTS = Path("tools") / "worker-research" / "reports"


def default_checkout() -> Path | None:
    """The source checkout an editable install runs from (tools/worker-research/src/<pkg>)."""
    root = HERE.parents[3] if len(HERE.parents) > 3 else None
    return root if root is not None and (root / KNOWN_WORKERS).is_file() else None


def _baton():
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


def coverage_problems(raw: Any, output: dict[str, Any] | None) -> list[str]:
    """Models of a harness's creators with no pinned route on it and no stated gap (0089).

    A pinned route is a non-alias route of the harness for that model with an
    invocation. A gap is the model's id in ``models_not_routed`` of that harness
    or inside a ``coverage_gaps`` line. Retired models need neither."""
    raw = raw or {}
    output = output or {}
    models = raw.get("models") or {}
    routed = {(r.get("provider"), r.get("model_id")) for r in raw.get("routes") or [] if r.get("model_id") and r.get("invocation")}
    named = {(h.get("provider"), n.get("model_id")) for h in output.get("harnesses") or [] for n in h.get("models_not_routed") or []}
    gap_lines = [g for g in output.get("coverage_gaps") or [] if isinstance(g, str)]
    out = []
    for pname, prov in (raw.get("providers") or {}).items():
        if prov.get("kind") != "harness":
            continue
        creators = set(prov.get("creators") or [])
        for mid, m in models.items():
            if m.get("creator") not in creators or m.get("retired"):
                continue
            if (pname, mid) in routed or (pname, mid) in named or any(mid in g for g in gap_lines):
                continue
            out.append(f"{mid} has no pinned route on {pname} and no stated gap: add a route, or name it in the harness's models_not_routed with the reason")
    return out


def check(proposal_text: str, current_text: str, repo: Path, output: dict[str, Any] | None = None) -> list[str]:
    """Why a proposal is refused; empty when it may be written."""
    known_workers, vocab, ADAPTERS, _load_yaml, _Api, _init = _baton()
    import yaml

    try:
        raw = yaml.safe_load(proposal_text)
    except yaml.YAMLError as e:
        return [f"not YAML: {e}"]
    kw, issues = known_workers.validate(raw, vocab.load(vocab.DEFAULT), set(ADAPTERS), source="proposal", require_basis=True)
    problems = [str(i) for i in issues] + coverage_problems(raw, output)
    old = verified_entries(yaml.safe_load(current_text))
    new = verified_entries(raw)
    for key, value in new.items():
        if old.get(key) != value:
            problems.append(f"route {key}: research may not add or change verified (that records a live check)")
    for key in old:
        if key not in new and any((r.get("provider"), r.get("adapter"), r.get("invocation")) == key for r in (raw or {}).get("routes") or []):
            problems.append(f"route {key}: research may not remove verified")
    return problems


def litellm_entries(raw: Any) -> tuple[str | None, dict[str, dict[str, Any]]]:
    """The installed LiteLLM's model-map entry for every API route in the data (0091).

    Returns (LiteLLM version, {invocation: the catalog fields}); the fields are the
    ones that show a capability (``CATALOG_FIELDS``) plus ``max_input_tokens``.
    A route LiteLLM does not know has an empty entry; no LiteLLM gives (None, {})."""
    try:
        import importlib.metadata as md

        import litellm

        version = md.version("litellm")
        table = litellm.model_cost
    except Exception:
        return None, {}
    known_workers = _baton()[0]
    fields = [*known_workers.CATALOG_FIELDS, "max_input_tokens"]
    providers = (raw or {}).get("providers") or {}
    out: dict[str, dict[str, Any]] = {}
    for r in (raw or {}).get("routes") or []:
        inv = r.get("invocation")
        if not inv or r.get("adapter") != "litellm_api" or providers.get(r.get("provider"), {}).get("kind") == "harness":
            continue
        entry = table.get(inv) or table.get(inv.split("/", 1)[-1]) or {}
        out[inv] = {f: entry[f] for f in fields if f in entry}
    return version, out


def harness_docs(repo: Path) -> dict[str, list[str]]:
    path = repo / "tools" / "worker-research" / "harness-docs.yaml"
    return _baton()[3](path) or {} if path.is_file() else {}


def validator_command(repo: Path) -> str:
    """A command the worker may run to validate a proposal file: ``<command> <file>`` (criterion 6)."""
    import shlex

    return " ".join(shlex.quote(a) for a in (sys.executable, str(Path(__file__).resolve()), "--repo", str(repo), "--check"))


def check_file(path: Path, repo: Path, report: Path | None = None) -> int:
    """``--check FILE``: print why a proposal would be refused; exit 0 when it would be accepted.

    ``--report FILE`` is the worker's draft report (JSON), which can name coverage gaps."""
    if not path.is_file():
        print(f"baton-worker-research: no file {path}", file=sys.stderr)
        return 2
    output = None
    if report is not None:
        try:
            output = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"baton-worker-research: cannot read the report {report}: {e}", file=sys.stderr)
            return 2
    problems = check(path.read_text(encoding="utf-8"), (repo / KNOWN_WORKERS).read_text(encoding="utf-8"), repo, output)
    for p in problems:
        print(f"- {p}")
    print("refused" if problems else "accepted")
    return 1 if problems else 0


def report_markdown(output: dict[str, Any], today: str, profile: str, problems: list[str], litellm_version: str | None = None) -> str:
    lines = [f"# Worker research, {today}", "", f"Worker profile: `{profile}`.", "",
             f"LiteLLM model map: {litellm_version or 'not installed (no catalog facts were given)'}.", ""]
    if problems:
        lines += ["**Refused** (the repository file was not changed):", "", *[f"- {p}" for p in problems], ""]
    for key, title in (("inclusion_criteria", "Inclusion criteria"), ("providers_covered", "Providers covered"),
                       ("categories_covered", "Categories covered"), ("coverage_gaps", "Coverage gaps")):
        lines += [f"## {title}", "", *[f"- {x}" for x in output.get(key) or ["(none given)"]], ""]
    for h in output.get("harnesses") or []:
        lines += [f"## Harness: {h.get('provider')}", "",
                  f"- Models routed: {', '.join(h.get('models_routed') or []) or '(none)'}"]
        for n in h.get("models_not_routed") or []:
            lines.append(f"- Not routed: {n.get('model_id')}: {n.get('reason')}")
        lines.append(f"- Tools proposed: {', '.join(h.get('tools_proposed') or []) or '(none)'}")
        for w in h.get("widens_permissions") or []:
            lines.append(f"- **Widens permissions:** {w}")
        lines.append("")
    lines += ["## Changes", ""]
    for c in output.get("changes") or []:
        lines.append(f"- {c.get('what')}: {c.get('why')} ({', '.join(c.get('sources') or []) or 'no sources'})")
    if output.get("notes"):
        lines += ["", "## Notes", "", output["notes"]]
    return "\n".join(lines) + "\n"


HINTS = {
    "configuration.unknown_profile": "`baton workers status` lists what this machine has and can set up",
    "routing.ineligible": "the research step needs a strong profile with structured_output, web_access, file_write and technical_reasoning",
}


def main(argv: list[str] | None = None) -> int:
    from baton.packet import EngineError

    try:
        return _main(argv)
    except EngineError as e:
        hint = HINTS.get(e.code)
        # The scratch run is gone by now, so its `baton eligible` pointer is no use.
        msg = re.sub(r" \(see `baton eligible [^`]*`\)", "", str(e))
        print(f"baton-worker-research: {msg}" + (f"\n  {hint}" if hint else ""), file=sys.stderr)
        return 2 if e.code.startswith(("configuration.", "routing.")) else 1


def _main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="baton-worker-research", description=__doc__.split("\n\n")[0])
    ap.add_argument("--report", metavar="FILE", help="with --check: the draft report as JSON, so named coverage gaps count")
    ap.add_argument("--profile", help="the worker profile to dispatch to")
    ap.add_argument("--check", metavar="FILE", help="validate a proposal file as the tool would after a run, and stop")
    ap.add_argument("--home", help="the Baton home holding the profiles (default: BATON_HOME or ~/.baton)")
    ap.add_argument("--repo", help="the source checkout to update (default: the one this was installed from)")
    ap.add_argument("--reports", help="where the report goes (default: <repo>/tools/worker-research/reports)")
    ap.add_argument("--timeout", type=float, default=None, help="seconds to wait for the worker")
    ap.add_argument("--today", default=dt.date.today().isoformat(), help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    known_workers, vocab, ADAPTERS, _load_yaml, Api, init = _baton()

    repo = Path(args.repo).resolve() if args.repo else default_checkout()
    if repo is None:
        ap.error("not installed from a Baton checkout; name one with --repo")
    target = repo / KNOWN_WORKERS
    if not target.is_file():
        ap.error(f"{repo} is not a Baton checkout (no {KNOWN_WORKERS})")
    if args.check:
        return check_file(Path(args.check), repo, Path(args.report) if args.report else None)
    if not args.profile:
        ap.error("--profile is required (or --check FILE)")
    current = target.read_text(encoding="utf-8")
    voc = vocab.load(vocab.DEFAULT)
    machine_dependent = (_load_yaml(target) or {}).get("machine_dependent") or []
    from baton.capability_states import TOOLING

    raw_current = _load_yaml(target) or {}
    litellm_version, catalog = litellm_entries(raw_current)
    inputs = {
        "title": f"Worker research {args.today}",
        # YAML dates (a tool map's sources) become ISO strings: run inputs are JSON.
        "tool_maps": json.loads(json.dumps({n: p.get("tools") or {} for n, p in (raw_current.get("providers") or {}).items() if p.get("kind") == "harness"}, default=str)),
        "tooling_capabilities": list(TOOLING),
        "harness_docs": harness_docs(repo),
        "litellm": {"version": litellm_version, "entries": catalog},
        "validator": validator_command(repo),
        "known_workers": current,
        "today": args.today,
        "adapters": sorted(ADAPTERS),
        "capabilities": {"capabilities": voc.capabilities, "tiers": voc.tiers, "machine_dependent": machine_dependent},
    }
    reports = Path(args.reports) if args.reports else repo / REPORTS
    scratch = Path(tempfile.mkdtemp(prefix="baton-worker-research-"))
    try:
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=scratch, check=True)
        for k, v in (("user.email", "research@localhost"), ("user.name", "worker-research")):
            subprocess.run(["git", "config", k, v], cwd=scratch, check=True)
        init(scratch, bare=True)
        api = Api.open(scratch, director_id="worker-research@localhost", home=args.home)
        ref = api.vendor(RECIPE)["recipe"]
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
        problems = check(proposal, current, repo, doc.get("output") or {})
        reports.mkdir(parents=True, exist_ok=True)
        (reports / f"{args.today}.md").write_text(report_markdown(doc.get("output") or {}, args.today, args.profile, problems, litellm_version), encoding="utf-8")
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
