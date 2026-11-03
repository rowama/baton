"""Checkpoint commits (§10.1) and the git plumbing they need.

A checkpoint stages the committing run's directory (and, later, its published
deliverables) and commits exactly those paths on the current branch (§18 #6).
Git runs with explicit settings (``core.autocrlf=false``, §15.1), except the
working-tree snapshot's ``git status``, which uses the repository's own
line-ending settings (see ``tree_snapshot``).

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
# For `git status` in tree_snapshot: the repository's own line-ending settings (§6.3).
GIT_OWN_EOL = ("git", "-c", "core.quotepath=false")


class GitError(Exception):
    pass


def git(root: Path, *args: str, check: bool = True, own_eol: bool = False) -> subprocess.CompletedProcess[str]:
    try:
        proc = subprocess.run([*(GIT_OWN_EOL if own_eol else GIT), "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8", check=False)
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


# ---------------------------------------------------------------------------
# Working-tree snapshots: the runtime check for read and none steps (§6.3)
# ---------------------------------------------------------------------------


@dataclass
class TreeSnapshot:
    head: str | None
    files: dict[str, str]  # changed or untracked path -> content sha256 (or "deleted")


def tree_snapshot(root: Path, exclude: list[str] = ()) -> TreeSnapshot | None:
    """HEAD plus every path git reports as changed or untracked, with content hashes.

    Paths under any ``exclude`` prefix (POSIX, relative to the root) are left
    out. Ignored files are not seen. Returns None outside a git work tree.

    ``git status`` runs with the repository's own line-ending settings, not
    ``core.autocrlf=false``: files committed by the owner's git with
    ``autocrlf=true`` (Git for Windows' default) hold CRLF in the tree and LF
    in the index, and a forced override makes git report them modified only
    when it happens to re-hash them (its index timing), so two snapshots of an
    untouched tree could differ. The hashes are of the raw bytes either way.
    """
    import hashlib

    if not is_repo(root):
        return None
    top = toplevel(root)
    head = git(top, "rev-parse", "--verify", "-q", "HEAD", check=False).stdout.strip() or None
    raw = git(top, "--no-optional-locks", "status", "--porcelain=v1", "-z", "--untracked-files=all", own_eol=True).stdout
    entries = raw.split("\0")
    paths: list[str] = []
    i = 0
    while i < len(entries):
        e = entries[i]
        i += 1
        if len(e) < 4:
            continue
        xy, path = e[:2], e[3:]
        paths.append(path)
        if "R" in xy or "C" in xy:  # the source path follows
            if i < len(entries):
                paths.append(entries[i])
            i += 1
    prefixes = [p.rstrip("/") + "/" for p in exclude]
    files: dict[str, str] = {}
    for path in paths:
        if any(path.startswith(p) for p in prefixes):
            continue
        f = top / path
        if f.is_file():
            files[path] = hashlib.sha256(f.read_bytes()).hexdigest()
        elif f.is_dir():  # e.g. a nested repository
            files[path] = "dir"
        else:
            files[path] = "deleted"
    return TreeSnapshot(head, files)


def only_checkpoints(root: Path, old: str | None, new: str | None) -> bool:
    """True when ``new`` descends from ``old`` through Baton checkpoint commits only (``baton(<run>): …``).

    The runtime commits checkpoints while workers run (this run's or another's), so
    those commits are never a worker's change to the working tree.
    """
    if not old or not new:
        return False
    if git(root, "merge-base", "--is-ancestor", old, new, check=False).returncode != 0:
        return False
    subjects = [x for x in git(root, "log", "--format=%s", f"{old}..{new}").stdout.splitlines() if x]
    return bool(subjects) and all(x.startswith("baton(") and "): " in x for x in subjects)


def tree_changes(before: TreeSnapshot | None, after: TreeSnapshot | None, root: Path | None = None) -> list[str]:
    """What differs between two snapshots: changed paths, and HEAD if it moved.

    With ``root``, HEAD moving only by Baton's own checkpoint commits does not count.
    """
    if before is None or after is None:
        return []
    out = []
    if before.head != after.head and not (root is not None and only_checkpoints(root, before.head, after.head)):
        out.append(f"HEAD moved from {before.head or '(none)'} to {after.head or '(none)'}")
    for path in sorted(set(before.files) | set(after.files)):
        if before.files.get(path) != after.files.get(path):
            out.append(path)
    return out
