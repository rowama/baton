"""The manual: topics, stable anchors, a checked Markdown subset, search (§13.10).

The manual is shipped data (``baton/_data/manual``; ``manual/`` in a source checkout) read three ways: in
context from the setup page, as a guide, and as an administrator's reference. This module is the one reader
for all of them, and its ``validate`` is what the tests run, so the manual cannot drift from the code.

Nothing here imports the UI, and nothing in the runtime needs the manual to exist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from . import data

PARTS = ("user", "providers", "recipes", "admin", "reference")
AUDIENCE = {"user": "owner", "providers": "owner", "recipes": "owner", "admin": "admin", "reference": "admin"}
PART_TITLES = {"user": "User guide", "providers": "Providers", "recipes": "Recipes", "admin": "Admin guide", "reference": "Reference"}
PART_BLURBS = {
    "user": "What you can do with Baton, and how, step by step.",
    "providers": "Getting each provider working: where to get a key and what to expect. Generated from Baton's provider directory.",
    "recipes": "The processes that ship with Baton: what each is for, what you will be asked, what it makes.",
    "admin": "Installing, configuring and securing Baton on a machine.",
    "reference": "Every command, setting, path and message, generated from Baton itself.",
}
HERE_NOW = "here-now"  # the short, in-context answer every guide topic opens with
SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{#([^}\s]*)\})?\s*$")
LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]*)\)")
FENCE = re.compile(r"^```\s*([a-z]*)\s*$")
NOTE = re.compile(r"^> \*\*(Note|Warning):\*\* ")
REQUIRED = ("id", "title", "audience", "summary")


class ManualError(ValueError):
    pass


@dataclass
class Heading:
    level: int
    text: str
    anchor: str
    line: int


@dataclass
class Topic:
    id: str
    part: str
    slug: str
    path: Path
    title: str
    audience: str
    summary: str
    related: list[str]
    aliases: list[str]
    anchor_aliases: dict[str, str]
    body: str
    order: int = 100
    headings: list[Heading] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def anchors(self) -> list[str]:
        return [h.anchor for h in self.headings]


def root() -> Path:
    return data.path("manual")


def _split(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        raise ManualError("no front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ManualError("front matter is not closed")
    meta = yaml.safe_load(text[4:end]) or {}
    if not isinstance(meta, dict):
        raise ManualError("front matter is not a mapping")
    return meta, text[end + 5:]


def _body_lines(body: str):
    """(line number, text, in_code) for each body line; the fence lines themselves count as code."""
    in_code = False
    for n, line in enumerate(body.split("\n"), 1):
        if line.startswith("```"):
            yield n, line, True
            in_code = not in_code
        else:
            yield n, line, in_code


class Manual:
    def __init__(self, base: Path | None = None) -> None:
        self.base = base or root()
        self.topics: dict[str, Topic] = {}
        self.problems: list[str] = []
        self._load()

    def _load(self) -> None:
        for part in PARTS:
            for path in sorted((self.base / part).glob("*.md")):
                rel = f"{part}/{path.name}"
                try:
                    meta, body = _split(path.read_text(encoding="utf-8"))
                except (ManualError, yaml.YAMLError, OSError) as e:
                    self.problems.append(f"{rel}: {e}")
                    continue
                slug = path.stem
                tid = f"{part}.{slug}"
                t = Topic(id=str(meta.get("id", "")), part=part, slug=slug, path=path, title=str(meta.get("title", "")),
                          audience=str(meta.get("audience", "")), summary=str(meta.get("summary", "")),
                          related=list(meta.get("related") or []), aliases=list(meta.get("aliases") or []),
                          anchor_aliases=dict(meta.get("anchor_aliases") or {}), body=body,
                          order=int(meta.get("order", 100)))
                for key in REQUIRED:
                    if not meta.get(key):
                        t.problems.append(f"{rel}: front matter lacks {key}")
                if t.id != tid:
                    t.problems.append(f"{rel}: id {t.id!r} must be {tid!r}")
                if not SLUG.fullmatch(slug):
                    t.problems.append(f"{rel}: the file name must be lowercase words joined by hyphens")
                if t.audience != AUDIENCE[part]:
                    t.problems.append(f"{rel}: audience must be {AUDIENCE[part]!r} in {part}/")
                self.topics[tid] = t
                self._scan(t, rel)
        ordered = sorted(self.topics.values(), key=lambda t: (PARTS.index(t.part), t.order, t.slug))
        self.topics = {t.id if False else f"{t.part}.{t.slug}": t for t in ordered}
        self.aliases = {a: t.id for t in self.topics.values() for a in t.aliases}

    def _scan(self, t: Topic, rel: str) -> None:
        for n, line, in_code in _body_lines(t.body):
            if in_code:
                continue
            m = HEADING.match(line)
            if not m:
                continue
            level, text, anchor = len(m.group(1)), m.group(2), m.group(3)
            if level == 1:
                t.problems.append(f"{rel}:{n}: the title is in the front matter; start headings at ##")
            elif level > 3:
                t.problems.append(f"{rel}:{n}: headings go no deeper than ###")
            if not anchor or not SLUG.fullmatch(anchor):
                t.problems.append(f"{rel}:{n}: heading {text!r} needs an explicit lowercase anchor, like {{#where-keys-are-kept}}")
                continue
            if anchor in t.anchors:
                t.problems.append(f"{rel}:{n}: anchor #{anchor} is used twice")
            t.headings.append(Heading(level, text, anchor, n))
        if t.part != "reference" and (not t.headings or t.headings[0].anchor != HERE_NOW):
            t.problems.append(f"{rel}: a guide topic opens with '## Here, now {{#{HERE_NOW}}}', the short answer for the place you are")

    # ---- reading -------------------------------------------------------

    def resolve(self, ref: str) -> tuple[Topic, str | None]:
        """A topic id (or alias), optionally with ``#anchor`` (or an old anchor, through ``anchor_aliases``)."""
        tid, _, anchor = ref.partition("#")
        t = self.topics.get(tid) or self.topics.get(self.aliases.get(tid, ""))
        if t is None:
            raise KeyError(ref)
        if not anchor:
            return t, None
        anchor = t.anchor_aliases.get(anchor, anchor)
        if anchor not in t.anchors:
            raise KeyError(ref)
        return t, anchor

    def section(self, t: Topic, anchor: str | None) -> str:
        """The topic's Markdown, or one section of it (a heading to the next of the same or a higher level)."""
        if anchor is None:
            return t.body.strip("\n")
        lines = t.body.split("\n")
        idx = next(i for i, h in enumerate(t.headings) if h.anchor == anchor)
        start, level = t.headings[idx].line - 1, t.headings[idx].level
        end = len(lines)
        for h in t.headings[idx + 1:]:
            if h.level <= level:
                end = h.line - 1
                break
        return "\n".join(lines[start:end]).strip("\n")

    def listing(self) -> list[dict[str, str]]:
        return [{"id": t.id, "part": t.part, "title": t.title, "summary": t.summary} for t in self.topics.values()]

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        words = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) > 1]
        if not words:
            return []
        out = []
        for t in self.topics.values():
            score, where = 0, None
            for w in words:
                score += 5 * (w in t.title.lower()) + 3 * (w in t.summary.lower()) + (w in t.body.lower())
            for h in t.headings:
                if any(w in h.text.lower() for w in words):
                    score += 2
                    where = where or h.anchor
            if score:
                out.append({"id": t.id, "anchor": where, "title": t.title, "summary": t.summary, "score": score})
        return sorted(out, key=lambda r: (-r["score"], r["id"]))[:limit]

    def tree(self) -> list[dict[str, Any]]:
        """The reader's navigation: parts in order, each with its topics and their headings."""
        out = []
        for part in PARTS:
            topics = [t for t in self.topics.values() if t.part == part]
            if topics:
                out.append({"part": part, "title": PART_TITLES[part], "blurb": PART_BLURBS[part], "topics": [
                    {"id": t.id, "slug": t.slug, "title": t.title, "summary": t.summary,
                     "headings": [{"level": h.level, "text": h.text, "anchor": h.anchor} for h in t.headings]} for t in topics]})
        return out

    def page(self, tid: str, anchor: str | None = None) -> dict[str, Any]:
        """One topic for the reader (or one section of it, for the context panel): Markdown, neighbours, related topics."""
        t, found = self.resolve(tid if anchor is None else f"{tid.partition('#')[0]}#{anchor}")
        anchor = found if anchor is not None else None
        order = list(self.topics.values())
        i = order.index(t)
        brief = lambda x: {"id": x.id, "part": x.part, "slug": x.slug, "title": x.title}  # noqa: E731
        return {"id": t.id, "part": t.part, "slug": t.slug, "part_title": PART_TITLES[t.part], "title": t.title,
                "summary": t.summary, "anchor": anchor, "markdown": self.section(t, anchor),
                "headings": [{"level": h.level, "text": h.text, "anchor": h.anchor} for h in t.headings],
                "prev": brief(order[i - 1]) if i > 0 else None, "next": brief(order[i + 1]) if i + 1 < len(order) else None,
                "related": [brief(self.resolve(r)[0]) for r in t.related if r.partition("#")[0] in self.topics]}

    # ---- the registry of published anchors -----------------------------

    def anchors(self) -> list[str]:
        return sorted([t.id for t in self.topics.values()] + [f"{t.id}#{a}" for t in self.topics.values() for a in t.anchors])

    def published(self) -> list[str]:
        p = self.base / "anchors.yaml"
        return list((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("published") or []) if p.is_file() else []

    def write_anchors(self) -> Path:
        """Record every current anchor as published; a published anchor must keep resolving (directly or by alias)."""
        keep = sorted(set(self.published()) | set(self.anchors()))
        p = self.base / "anchors.yaml"
        p.write_text("# Every anchor ever published. One may be renamed only by leaving the old name as an alias.\n"
                     "# Refresh with: python tools/manual_anchors.py\n" + yaml.safe_dump({"published": keep}, sort_keys=False), encoding="utf-8")
        return p


# ---- validation (what the tests run) -----------------------------------

def _prose(line: str) -> str:
    return re.sub(r"`[^`]*`", "", line)


def validate(m: Manual | None = None, *, cli: Any = None) -> list[str]:
    """Every problem in the manual: the Markdown subset, links, anchors, context map, examples, vocabulary."""
    m = m or Manual()
    problems = list(m.problems)
    terms = _terms(m.base)
    for t in m.topics.values():
        problems += t.problems
        rel = f"{t.part}/{t.path.name}"
        for ref in t.related:
            try:
                m.resolve(ref)
            except KeyError:
                problems.append(f"{rel}: related {ref!r} does not resolve")
        problems += _check_body(m, t, rel, terms if t.audience == "owner" else [], cli)
    for a in m.published():
        try:
            m.resolve(a)
        except KeyError:
            problems.append(f"anchors.yaml: published anchor {a} no longer resolves (rename leaves an alias: aliases / anchor_aliases)")
    missing = sorted(set(m.anchors()) - set(m.published()))
    if missing:
        problems.append("anchors.yaml lacks current anchors (run python tools/manual_anchors.py): " + ", ".join(missing[:5]) + (" ..." if len(missing) > 5 else ""))
    problems += validate_context(m, cli)
    return problems


def _terms(base: Path) -> list[str]:
    p = base / "terms.yaml"
    return list((yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("internal") or []) if p.is_file() else []


def _check_body(m: Manual, t: Topic, rel: str, terms: list[str], cli: Any) -> list[str]:
    out: list[str] = []
    lines = list(_body_lines(t.body))
    fence_open = None
    block: list[str] = []
    table_cols = None
    for n, line, in_code in lines:
        where = f"{rel}:{n}"
        if in_code:
            if line.startswith("```"):
                if fence_open is None:
                    f = FENCE.match(line)
                    if f is None:
                        out.append(f"{where}: a code fence is either bare or has one lowercase language")
                    fence_open, block = ((f.group(1) if f else ""), n), []
                else:
                    if fence_open[0] == "baton":
                        out += _check_example(block, f"{rel}:{fence_open[1]}", cli)
                    fence_open = None
            else:
                block.append(line)
            continue
        if re.search(r"</?[A-Za-z!][^>]*>", _prose(line)):
            out.append(f"{where}: raw HTML is not part of the manual's Markdown subset")
        if line.startswith(">") and not NOTE.match(line) and not _in_note(lines, n):
            out.append(f"{where}: a quote is a note: '> **Note:** ...' or '> **Warning:** ...'")
        if line.startswith("|"):
            cols = len(re.findall(r"(?<!\\)\|", line))
            if table_cols not in (None, cols):
                out.append(f"{where}: table rows have different numbers of columns")
            table_cols = cols
        else:
            table_cols = None
        for text, target in LINK.findall(_prose(line)):
            out += _check_link(m, t, target, where)
        for term in terms:
            if re.search(rf"(?<![\w-]){re.escape(term)}(?![\w-])", _prose(line), re.IGNORECASE):
                out.append(f"{where}: internal term {term!r} in owner-facing text (manual/terms.yaml); say it in the owner's words")
    if fence_open is not None:
        out.append(f"{rel}:{fence_open[1]}: code fence is never closed")
    return out


def _in_note(lines, n) -> bool:
    for k in range(n - 2, -1, -1):
        text = lines[k][1]
        if not text.startswith(">"):
            return False
        if NOTE.match(text):
            return True
    return False


def _check_link(m: Manual, t: Topic, target: str, where: str) -> list[str]:
    if target.startswith("https://"):
        return []
    if target.startswith(("http://", "//", "/", "mailto:", "javascript:", "data:")) or "/" in target.split("#")[0] or ".md" in target:
        return [f"{where}: link {target!r}: use https://, or a topic id like user.connect-an-account#here-now"]
    if target.startswith("#"):
        return [] if target[1:] in t.anchors or target[1:] in t.anchor_aliases else [f"{where}: no anchor {target} in this topic"]
    try:
        m.resolve(target)
    except KeyError:  # expected: an unresolved link is the problem being reported
        return [f"{where}: link {target!r} does not resolve to a topic or anchor"]
    return []


def _check_example(block: list[str], where: str, cli: Any) -> list[str]:
    """Each ``baton ...`` line must use a command, and options, the CLI really has."""
    from . import manual_cli

    return [f"{where}: {p}" for p in manual_cli.check_example(block, cli)]


# ---- the context map ---------------------------------------------------

def context(base: Path | None = None) -> dict[str, Any]:
    p = (base or root()) / "context.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {} if p.is_file() else {}


def validate_context(m: Manual, cli: Any = None) -> list[str]:
    """Where in the page and CLI each topic opens: every pointer resolves, every command is covered or listed as pending."""
    from . import manual_cli

    c = context(m.base)
    out = []
    for kind in ("ui", "commands"):
        for key, ref in (c.get(kind) or {}).items():
            try:
                m.resolve(ref)
            except KeyError:
                out.append(f"context.yaml: {kind} {key}: {ref!r} does not resolve")
    commands = manual_cli.commands(cli)
    mapped = set((c.get("commands") or {}))
    pending = set(c.get("pending_commands") or [])
    for name in sorted(mapped - commands):
        out.append(f"context.yaml: commands lists {name!r}, which is not a baton command")
    for name in sorted(pending - commands):
        out.append(f"context.yaml: pending_commands lists {name!r}, which is not a baton command")
    for name in sorted(pending & mapped):
        out.append(f"context.yaml: {name!r} is both mapped and pending")
    for name in sorted(commands - mapped - pending):
        out.append(f"context.yaml: command {name!r} has no manual topic (map it under commands:)")
    return out


def manual_for_command(name: str) -> str | None:
    """The topic id a command's ``--help`` points to, or None."""
    try:
        ref = (context().get("commands") or {}).get(name)
    except (OSError, yaml.YAMLError):  # expected: a missing or unreadable context map just means no pointer is shown
        return None
    return str(ref) if ref else None


def for_error(code: str, base: Path | None = None) -> str | None:
    """The topic that explains a refusal code (``context.yaml``'s ``errors``), as ``topic#anchor``."""
    try:
        ref = (context(base).get("errors") or {}).get(code)
    except (OSError, yaml.YAMLError):  # expected: no context map just means no pointer
        return None
    return str(ref) if ref else None


class NoTopic(ManualError):
    """``baton help <x>`` where nothing matches; the message says what to try."""


def help_payload(topic: str | None = None, search: str | None = None, base: Path | None = None) -> dict[str, Any]:
    """What the CLI's ``help`` prints and the Director's ``help`` returns: the topics, a search, or one topic or section."""
    m = Manual(base)
    if search is not None:
        return {"ok": True, "results": m.search(search)}
    if topic is None:
        return {"ok": True, "topics": m.listing()}
    try:
        t, anchor = m.resolve(topic)
    except KeyError:
        near = [h["id"] for h in m.search(topic.replace(".", " ").replace("-", " "), 3)]
        raise NoTopic(f"no manual topic {topic!r}" + (f"; did you mean {', '.join(near)}?" if near else "; list them with: baton help")) from None
    return {"ok": True, "id": t.id, "anchor": anchor, "title": t.title, "summary": t.summary, "markdown": m.section(t, anchor)}
