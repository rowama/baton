"""Action permissions (§13.7).

``project.yaml`` ``permissions`` says, per action, ``allow``, ``ask`` or
``deny``. The runtime enforces them for its own git operations (``push``) and
the Director checks them before acting outside the runtime (``permission``).

**Push categories.** The commits a push would send (``<upstream>..HEAD``, or
every commit no ref of the remote has when the branch has no upstream) are
sorted into one category, the least privileged that covers them all:

* ``docs_only``: every path any of them changes matches ``docs_only_globs``;
* ``after_verified``: every commit that is not docs-only is a Baton checkpoint
  (``baton(<run>): …`` / ``baton(project): …``) or the ``commit_sha`` of a
  passed step (``step_passed`` in any run), so a recipe's gates vouched for it;
* ``other``: anything else.

``deny`` is refused and never attempted. ``ask`` is recorded as
``permission_requested`` and returns to the Director, who asks the owner; the
owner's approval comes back as the same call with ``approved`` and the owner's
words, recorded as ``human_decision {kind: permission}`` before
``permission_used``. An allowed action records ``permission_used``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import diag
from .gitops import GitError, git
from .reviews import matches

#: Actions with a rule of their own; ``push`` has one per category.
ACTIONS: tuple[str, ...] = ("push", "tag", "force_push", "merge", "deploy")
CATEGORIES: tuple[str, ...] = ("docs_only", "after_verified", "other")


def rule_for(config: Any, action: str, category: str | None = None) -> str:
    """The rule (``allow`` | ``ask`` | ``deny``) for an action (and, for ``push``, its category)."""
    perms = config.permissions
    if action == "push":
        return getattr(perms.push, category or "other")
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}; known: {', '.join(ACTIONS)}")
    return getattr(perms, action)


@dataclass
class PushPlan:
    remote: str
    branch: str
    upstream: str | None                   # e.g. origin/main; None: the branch is new on the remote
    commits: list[str] = field(default_factory=list)   # oldest first
    paths: list[str] = field(default_factory=list)     # every path the commits change
    category: str = "docs_only"
    unverified: list[str] = field(default_factory=list)  # commits that made it "other"
    outside_docs: list[str] = field(default_factory=list)  # paths outside docs_only_globs

    def summary(self) -> dict[str, Any]:
        return {
            "remote": self.remote, "branch": self.branch, "upstream": self.upstream, "category": self.category,
            "commits": self.commits, "paths": len(self.paths),
            **({"outside_docs": self.outside_docs[:20]} if self.outside_docs else {}),
            **({"unverified": self.unverified} if self.unverified else {}),
        }


def _lines(proc: Any) -> list[str]:
    return [x for x in proc.stdout.splitlines() if x.strip()]


def current_branch(root: Path) -> str:
    proc = git(root, "symbolic-ref", "--short", "-q", "HEAD", check=False)
    if proc.returncode != 0 or not proc.stdout.strip():
        raise GitError("HEAD is detached; check out a branch to push")
    return proc.stdout.strip()


def resolve_remote(root: Path, branch: str) -> tuple[str, str | None]:
    """(remote, upstream ref or None). The branch's configured remote, else ``origin``, else the only remote."""
    up = git(root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}", check=False)
    if up.returncode == 0 and up.stdout.strip():
        upstream = up.stdout.strip()
        remote = git(root, "config", f"branch.{branch}.remote", check=False).stdout.strip() or upstream.split("/", 1)[0]
        return remote, upstream
    remotes = _lines(git(root, "remote"))
    if not remotes:
        raise GitError("the repository has no remote to push to")
    return ("origin" if "origin" in remotes else remotes[0]) if len(remotes) != 1 else remotes[0], None


def verified_commits(root: Path, store: Any) -> set[str]:
    """Full SHAs named by ``commit_sha`` in a passed step's output, across every run."""
    out: set[str] = set()
    for rid in store.run_ids():
        try:
            log = store.run(rid)
            events = log.events()
        except Exception as e:  # an unreadable run vouches for nothing
            diag.note("permissions.run_unreadable", "permissions:verified_commits", error=f"{type(e).__name__}: {e}", run=rid)
            continue
        for e in events:
            if e.type != "step_passed":
                continue
            sha = _commit_sha(store, rid, e.data)
            if not sha:
                continue
            full = git(root, "rev-parse", "-q", "--verify", f"{sha}^{{commit}}", check=False).stdout.strip()
            if full:
                out.add(full)
    return out


def _commit_sha(store: Any, run_id: str, data: dict[str, Any]) -> str | None:
    out = None
    if data.get("output_sha256"):
        try:
            import json

            out = json.loads(store.run(run_id).cas.read(data["output_sha256"]))
        except Exception as e:
            diag.note("permissions.output_unreadable", "permissions:_commit_sha", error=f"{type(e).__name__}: {e}", run=run_id)
            return None
    sha = out.get("commit_sha") if isinstance(out, dict) else None
    return sha if isinstance(sha, str) and sha.strip() else None


def plan_push(root: Path, store: Any, globs: list[str]) -> PushPlan:
    branch = current_branch(root)
    remote, upstream = resolve_remote(root, branch)
    if upstream:
        commits = _lines(git(root, "rev-list", "--reverse", f"{upstream}..HEAD"))
    else:
        commits = _lines(git(root, "rev-list", "--reverse", "HEAD", "--not", f"--remotes={remote}"))
    plan = PushPlan(remote=remote, branch=branch, upstream=upstream, commits=commits)
    if not commits:
        return plan
    verified: set[str] | None = None
    paths: set[str] = set()
    for sha in commits:
        changed = _lines(git(root, "diff-tree", "--no-commit-id", "--name-only", "-r", "-m", "--root", sha))
        paths.update(changed)
        outside = [p for p in changed if not matches(p, globs)]
        if not outside:
            continue
        plan.outside_docs.extend(p for p in outside if p not in plan.outside_docs)
        subject = git(root, "log", "-1", "--format=%s", sha).stdout.strip()
        if subject.startswith("baton(") and "):" in subject:
            continue  # a checkpoint: the run's records and its deliverables
        if verified is None:
            verified = verified_commits(root, store)
        if sha not in verified:
            plan.unverified.append(sha)
    plan.paths = sorted(paths)
    plan.category = "other" if plan.unverified else ("after_verified" if plan.outside_docs else "docs_only")
    return plan
