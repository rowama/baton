"""Checkpoint commits (§10.1) and the git plumbing they need.

A checkpoint stages the committing run's directory (and, later, its published
deliverables) and commits exactly those paths on the current branch (§18 #6).
Git runs with explicit settings (``core.autocrlf=false``, §15.1).

**Unrelated changes.** The commit names its paths (``git commit --only``), so
unstaged or untracked work elsewhere in the tree is never swept in. Changes
*staged* for other paths mean someone is mid-commit; the checkpoint is then
refused and reported rather than committing around them.

**Commit SHAs** are not written into events; ``last_checkpoint`` reads them
back from ``git log`` by the ``baton(<run_id>):`` subject prefix.

**Git LFS** (§18 #7) is optional: when ``git lfs`` is installed, stored blobs
at or above the project's threshold are listed in the run's own
``.gitattributes`` before staging, so they are committed through LFS.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

GIT = ("git", "-c", "core.autocrlf=false", "-c", "core.quotepath=false")


class GitError(Exception):
    pass


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run([*GIT, "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", check=False)
    except FileNotFoundError as e:  # pragma: no cover - git missing
        raise GitError("git is not installed") from e
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {(proc.stderr or proc.stdout).strip()}")
    return proc


def is_repo(root: Path) -> bool:
    try:
        return git(root, "rev-parse", "--is-inside-work-tree", check=False).stdout.strip() == "true"
    except GitError:  # pragma: no cover
        return False


def toplevel(root: Path) -> Path:
    return Path(git(root, "rev-parse", "--show-toplevel").stdout.strip())


def lfs_available(root: Path) -> bool:
    try:
        return git(root, "lfs", "version", check=False).returncode == 0
    except GitError:  # pragma: no cover
        return False


@dataclass
class Checkpoint:
    committed: bool
    sha: str | None = None
    subject: str | None = None
    reason: str | None = None  # why nothing was committed

    def as_dict(self) -> dict[str, object]:
        return {"committed": self.committed, "sha": self.sha, "subject": self.subject, "reason": self.reason}


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def preflight(root: Path, paths: list[Path]) -> tuple[Path, list[str]] | str:
    """(git toplevel, paths relative to it) when a checkpoint can be committed, else the reason it cannot."""
    if not is_repo(root):
        return "not a git repository"
    top = toplevel(root).resolve()
    rels = [PurePosixPath(p.resolve().relative_to(top)).as_posix() for p in paths]
    if git(top, "var", "GIT_COMMITTER_IDENT", check=False).returncode != 0:
        return "git has no committer identity (set user.name and user.email)"
    for marker in ("MERGE_HEAD", "REBASE_HEAD", "CHERRY_PICK_HEAD"):
        if git(top, "rev-parse", "-q", "--verify", marker, check=False).returncode == 0:
            return f"the repository is in the middle of an operation ({marker})"
    staged = [p for p in git(top, "diff", "--cached", "--name-only", "-z").stdout.split("\0") if p]
    unrelated = sorted(p for p in staged if not _under(p, rels))
    if unrelated:
        shown = ", ".join(unrelated[:5]) + (f" and {len(unrelated) - 5} more" if len(unrelated) > 5 else "")
        return f"unrelated changes are staged ({shown}); commit or unstage them first"
    return top, rels


def lfs_attributes(run_dir: Path, threshold_bytes: int) -> bool:
    """List CAS blobs at or above the threshold in ``<run_dir>/.gitattributes``. True if it changed."""
    cas = run_dir / "cas"
    big = sorted(
        p.relative_to(run_dir).as_posix()
        for p in (cas.rglob("*") if cas.is_dir() else [])
        if p.is_file() and not p.name.startswith(".") and p.stat().st_size >= threshold_bytes
    )
    if not big:
        return False
    ga = run_dir / ".gitattributes"
    lines = ga.read_text(encoding="utf-8").splitlines() if ga.is_file() else []
    want = [f"{rel} filter=lfs diff=lfs merge=lfs -text" for rel in big]
    merged = sorted(set(lines) | set(want))
    if merged == lines:
        return False
    ga.write_bytes(("\n".join(merged) + "\n").encode("utf-8"))
    return True


def commit(top: Path, rels: list[str], subject: str, body: list[str]) -> str | None:
    """Stage and commit exactly ``rels``; the new commit's SHA, or None when nothing changed."""
    git(top, "add", "-A", "--", *rels)
    if git(top, "diff", "--cached", "--quiet", "--", *rels, check=False).returncode == 0:
        return None
    message = subject + ("\n\n" + "\n".join(body) if body else "") + "\n"
    git(top, "commit", "-q", "--only", "-m", message, "--", *rels)
    return git(top, "rev-parse", "HEAD").stdout.strip()


def last_checkpoint(root: Path, run_id: str) -> str | None:
    """SHA of the newest checkpoint commit for this run on the current branch."""
    if not is_repo(root):
        return None
    proc = git(root, "log", "-1", "--format=%H", "--fixed-strings", f"--grep=baton({run_id}):", check=False)
    return proc.stdout.strip() or None
