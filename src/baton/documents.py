"""Project documents (§10.4; Decisions 0142, 0146): what one run can build on from another.

A **project document** is a file in the repo, identified by its path, that the
project has accepted: a deliverable an accepted step published (in any run,
whether or not that run has completed), or a file the owner attested. Nothing
here is a hand-kept index. The list is derived each time from

* every run's ``artifact_published`` (not ``kept``) and ``human_revision_ingested``
  with a path: a deliverable's versions, and an owner-accepted revision of one;
* the project log's ``document_attested``: the owner's attestations, with the
  attested bytes in the project CAS (``.baton/project/cas/``);

then the living file is hashed. Versions of one path are ordered by time; the
latest is the document's accepted version. The living file is ``unchanged``
when it holds that version's bytes, ``edited`` when it holds others, and
``deleted`` when it is gone. A moved file is a new document (0146).

Workspace-step output (code) is not a project document automatically; the
owner may attest a file from the tree (0146).
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .packet import EngineError
from .publish import PublishError, check_target, file_sha
from .store import Store


@dataclass
class Version:
    """One accepted version of a project document."""

    path: str
    sha256: str
    kind: str  # "deliverable" | "attested"
    source: dict[str, Any]
    ts: str
    order: tuple[str, str, int]  # (ts, log id, seq): a total order across logs
    media_type: str | None = None


@dataclass
class Document:
    path: str
    versions: list[Version] = field(default_factory=list)

    @property
    def latest(self) -> Version:
        return self.versions[-1]


def guess_media_type(path: str) -> str | None:
    mt, _ = mimetypes.guess_type(PurePosixPath(path).name)
    if mt is None and PurePosixPath(path).suffix.lower() in (".md", ".markdown"):
        return "text/markdown"
    return mt


def _registered_media_type(events: list[Any], passed_seq: Any, artifact: str) -> str | None:
    for e in events:
        if e.seq == passed_seq and e.type in ("step_passed", "step_imported"):
            return ((e.data.get("artifacts") or {}).get(artifact) or {}).get("media_type")
    return None


def collect(store: Store) -> dict[str, Document]:
    """Every project document by path, with its versions in order (oldest first)."""
    found: dict[str, list[Version]] = {}
    for rid in store.run_ids():
        events = store.run(rid).events()
        for e in events:
            d = e.data
            if e.type == "artifact_published" and not d.get("kept") and d.get("path") and d.get("sha256"):
                mt = _registered_media_type(events, d.get("passed_seq"), d.get("artifact") or "")
                src = {"kind": "deliverable", "run": rid, "step": e.step_path, "artifact": d.get("artifact")}
                if d.get("decision_id"):
                    src["decision_id"] = d["decision_id"]
                if d.get("revision"):
                    src["revision"] = d["revision"]
                found.setdefault(d["path"], []).append(Version(d["path"], d["sha256"], "deliverable", src, e.ts, (e.ts, rid, e.seq), mt))
            elif e.type == "human_revision_ingested" and d.get("path") and d.get("sha256") and d.get("source") == "drift":
                # The owner accepted their edit of a published file (§10.5): that edit is the accepted version now.
                src = {"kind": "deliverable", "run": rid, "step": e.step_path, "artifact": d.get("artifact"),
                       "revision": d.get("revision"), "decision_id": d.get("decision_id")}
                found.setdefault(d["path"], []).append(Version(d["path"], d["sha256"], "deliverable", src, e.ts, (e.ts, rid, e.seq)))
    plog = store.project_log()
    if plog.path.is_file():
        for e in plog.events():
            if e.type == "document_attested":
                d = e.data
                src = {"kind": "attested", "decision_id": d.get("decision_id"), "note": d.get("note")}
                found.setdefault(d["path"], []).append(
                    Version(d["path"], d["sha256"], "attested", src, e.ts, (e.ts, "", e.seq), d.get("media_type")))
    out = {}
    for path, vs in found.items():
        vs.sort(key=lambda v: v.order)
        out[path] = Document(path, vs)
    return out


def describe(doc: Document, root: Path) -> dict[str, Any]:
    """One document as ``documents()`` lists it."""
    v = doc.latest
    now = file_sha(root / doc.path)
    state = "deleted" if now is None else ("unchanged" if now == v.sha256 else "edited")
    media_type = v.media_type or next((x.media_type for x in reversed(doc.versions) if x.media_type), None) or guess_media_type(doc.path)
    return {
        "path": doc.path,
        "kind": v.kind,
        "media_type": media_type,
        "version": len(doc.versions),
        "accepted_sha256": v.sha256,
        "sha256": now,
        "state": state,
        "accepted_at": v.ts,
        "source": dict(v.source),
    }


def list_documents(store: Store) -> list[dict[str, Any]]:
    return [describe(doc, store.root) for _, doc in sorted(collect(store).items())]


def project_path(root: Path, raw: str) -> str:
    """``raw`` as a POSIX path relative to the project root, or ``EngineError(document.bad_path)``.

    An absolute path inside the project is accepted; anything outside it, in
    ``.git`` or ``.baton``, is refused.
    """
    text = (raw or "").strip()
    p = Path(text)
    if text and p.is_absolute():
        try:
            text = p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            raise EngineError("document.bad_path", f"{raw!r} is outside the project") from None
    try:
        return check_target(root, text)
    except PublishError as e:
        raise EngineError("document.bad_path", str(e).replace("publish target", "path")) from e


def attest(store: Store, raw_path: str, note: str, *, actor: str = "human", recorded_by: str | None = None) -> dict[str, Any]:
    """Record the owner's attestation of a project file (§10.4): a project decision with the file's hash.

    The bytes go to the project CAS, so a later binding (and any machine that
    resumes a run) can rely on exactly what was attested. Attesting the same
    path again records a newer version.
    """
    if not (note or "").strip():
        raise EngineError("attest.note_required", "attesting a file is the owner's decision; give their words with --note")
    root = store.root
    rel = project_path(root, raw_path)
    full = root / rel
    if not full.is_file():
        raise EngineError("attest.no_file", f"{rel} is not a file in the project" if full.exists() else f"{rel} does not exist")
    content = full.read_bytes()
    sha = store.project_cas.put(content)
    plog = store.project_log()
    previous = collect(store).get(rel)
    decision_id = f"d{len(plog.events()) + 1}"
    plog.append("human_decision", actor=actor, data={
        "kind": "attest", "decision": "attest", "path": rel, "sha256": sha, "note": note, "decision_id": decision_id,
        **({"recorded_by": recorded_by} if recorded_by else {}),
    })
    media_type = guess_media_type(rel)
    plog.append("document_attested", actor=actor, data={
        "path": rel, "sha256": sha, "note": note, "decision_id": decision_id, "size": len(content),
        **({"media_type": media_type} if media_type else {}),
    })
    doc = collect(store)[rel]
    return {"document": describe(doc, root), "decision_id": decision_id, "previous_version": len(previous.versions) if previous else 0}


# ---------------------------------------------------------------------------
# Binding (§8.6; Decisions 0142, 0146)
# ---------------------------------------------------------------------------


def media_fits(want: str | None, have: str | None) -> bool:
    """Whether a document of type ``have`` fits a role asking for ``want`` (``type/*`` matches any subtype)."""
    if not want:
        return True
    if not have:
        return False
    if want.endswith("/*"):
        return have.split("/", 1)[0] == want[:-2]
    return have == want


def check_binding(store: Store, recipe: Any, role_name: str, raw_paths: list[str]) -> tuple[Any, list[dict[str, Any]]]:
    """The role and the documents to bind to it, with their living bytes, or ``EngineError``. Writes nothing.

    Each path must be a project document whose file exists now (the binding takes
    the living file, 0146) and whose type fits the role. A single role takes
    exactly one path; a ``many`` role one or more, in the order given.
    """
    role = recipe.role(role_name)
    if role is None:
        declared = ", ".join(r.role for r in recipe.project_inputs) or "none"
        raise EngineError("bind.unknown_role", f"{recipe.ref} declares no project document role {role_name!r} (declared: {declared})")
    paths = [project_path(store.root, p) for p in raw_paths]
    if not paths:
        raise EngineError("bind.no_document", f"binding {role_name} needs a project document (see `documents`)")
    if not role.many and len(paths) != 1:
        raise EngineError("bind.one_document", f"role {role_name} takes exactly one document, got {len(paths)}")
    if len(set(paths)) != len(paths):
        raise EngineError("bind.duplicate", f"role {role_name}: a document is given more than once")
    docs = collect(store)
    out = []
    for rel in paths:
        doc = docs.get(rel)
        if doc is None:
            raise EngineError("bind.not_a_document", f"{rel} is not a project document: only a published deliverable or a file "
                                                     "the owner attested can be bound (the owner may attest it first)")
        info = describe(doc, store.root)
        if info["state"] == "deleted":
            raise EngineError("bind.deleted", f"{rel} was deleted; restore it, or bind another document")
        if not media_fits(role.media_type, info["media_type"]):
            raise EngineError("bind.media_type", f"role {role_name} takes {role.media_type}; {rel} is {info['media_type'] or 'of unknown type'}")
        content = (store.root / rel).read_bytes()
        out.append({"info": info, "content": content})
    return role, out


def record_binding(ctx: Any, role: Any, entries: list[dict[str, Any]], note: str, *, actor: str = "human",
                   recorded_by: str | None = None) -> dict[str, Any]:
    """Record the owner's binding of a role in this run: ``human_decision {kind: bind}`` then ``project_input_bound``.

    The bound bytes go into the run's CAS, so the run stays self-contained and
    resumable on another machine (§10.3).
    """
    import hashlib

    if not (note or "").strip():
        raise EngineError("bind.note_required", "binding a document is the owner's decision; give their words with --note")
    docs = []
    for e in entries:
        info, content = e["info"], e["content"]
        sha = ctx.log.cas.put(content)
        assert sha == hashlib.sha256(content).hexdigest()
        src = {k: v for k, v in info["source"].items() if k != "note"}
        docs.append({"path": info["path"], "sha256": sha, "accepted_sha256": info["accepted_sha256"], "version": info["version"],
                     "kind": info["kind"], "source": src, "edited_since_accepted": sha != info["accepted_sha256"],
                     **({"media_type": info["media_type"]} if info["media_type"] else {})})
    decision_id = f"d{ctx.log.state().last_seq + 1}"
    ctx.log.append("human_decision", actor=actor, data={
        "kind": "bind", "decision": "bind", "role": role.role, "paths": [d["path"] for d in docs], "note": note, "decision_id": decision_id,
        **({"recorded_by": recorded_by} if recorded_by else {}),
    })
    ctx.log.append("project_input_bound", actor=actor, data={"role": role.role, "many": role.many, "documents": docs, "decision_id": decision_id})
    return {"role": role.role, "documents": docs, "decision_id": decision_id}


def bound(events: list[Any]) -> dict[str, Any]:
    """The latest ``project_input_bound`` event of each role in a run."""
    out: dict[str, Any] = {}
    for e in events:
        if e.type == "project_input_bound":
            out[e.data["role"]] = e
    return out
