"""Groups at runtime (§5.4, §8.5): paths, expansion, iterations, aggregate state.

Nothing here appends to a log; ``engine.py`` turns what this module computes
into events. Everything is derived from the run's events (and its CAS), so a
``View`` can be rebuilt at any moment.

**Paths.** A step inside a group has the path
``<group>/<instance>/<iteration>/<step>`` (nested groups repeat the pattern:
``outer/<inst>/i1/inner/<inst>/i2/step``). ``<instance>`` is a runtime-assigned
random token (§5.8), also for groups without ``foreach`` and for the single
``foreach_if_source_skipped: once`` instance. ``<iteration>`` is ``i<n>``.

**Iterations.** Iteration 1 runs every step of the group; iteration *n* > 1
starts at ``repeat_from`` and runs it and every step listed after it. Steps
listed before ``repeat_from`` ran once, in ``i1``, and later iterations use
those results (``child_path``).

**Judges.** The steps named in ``repeat_until`` judge an iteration. When one
of a judge's declared blocking gates fails, the judge's result is still kept
(``step_passed`` with ``condition.gates_passed: false``) and the iteration ends:
later steps of that iteration never start, and the next iteration starts at
``repeat_from`` with the open findings and gate reasons
(``group.previous_iteration.findings``). At ``max_iterations`` the instance
escalates instead (``iteration_limit_reached``); the owner decides ``retry`` (a
fresh budget of ``max_iterations``) or ``abandon`` (the instance is abandoned
and the group cannot pass).

**Group events** (``step_path`` is the group's or instance's path; none is a
step transition):

* ``group_expanded`` on the group path: ``mode`` (``foreach`` | ``once`` |
  ``skip`` | ``single``), ``source``, ``source_sha256`` (the source output it
  was built from), ``items`` (each ``{id, sha256, content_sha256, title?}`` in
  order; ``sha256`` is the item blob in CAS with its ``id`` set) and, for a
  re-expansion, ``kept`` / ``changed`` / ``added`` / ``superseded`` ids.
* ``iteration_started`` on the instance path: ``iteration``, ``from``,
  ``budget_base`` (the iteration count when the current budget started).
* ``iteration_limit_reached`` on the instance path: ``iteration``,
  ``max_iterations``, ``judged`` (the judge's step path), ``judged_seq`` (its
  ``step_passed``), ``reasons``.
* The owner's decision is a ``human_decision`` on the instance path with
  ``kind: iteration_limit``.
"""

from __future__ import annotations

import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any, Iterator

from . import refs
from .models import Event, Group, Step
from .recipe import LoadedRecipe
from .state import SATISFIES_DEPS, RunState
from .store import canonical_json

_ITER = re.compile(r"^i([1-9][0-9]*)$")

#: Instance states (aggregate, never stored).
INSTANCE_STATES = ("not_started", "active", "escalated", "passed", "abandoned", "superseded")
#: Step states in which an attempt is in flight (refuse revise around them).
IN_FLIGHT = frozenset({"dispatched", "running", "submitted", "verifying", "awaiting_human"})


def new_instance_id() -> str:
    """An opaque instance id (§5.8): not derived from order or content."""
    return "x" + secrets.token_hex(4)[:7]


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Frame:
    """One enclosing group of a path: which instance, which iteration."""

    group: Group
    group_path: str
    instance: str
    iteration: int

    @property
    def instance_path(self) -> str:
        return f"{self.group_path}/{self.instance}"

    @property
    def prefix(self) -> str:
        return f"{self.instance_path}/i{self.iteration}/"

    def at(self, iteration: int) -> Frame:
        return Frame(self.group, self.group_path, self.instance, iteration)


@dataclass(frozen=True)
class Located:
    node: Step | Group
    path: str
    frames: tuple[Frame, ...]

    @property
    def frame(self) -> Frame | None:
        return self.frames[-1] if self.frames else None


def locate(recipe: LoadedRecipe, path: str) -> Located | None:
    """The recipe node for a step or group path, with its enclosing frames."""
    parts = path.split("/")
    nodes: list[Any] = list(recipe.recipe.steps)
    frames: list[Frame] = []
    prefix = ""
    i = 0
    while True:
        node = next((n for n in nodes if n.id == parts[i]), None)
        if node is None:
            return None
        if i == len(parts) - 1:
            return Located(node, path, tuple(frames))
        if not isinstance(node, Group) or len(parts) < i + 4:
            return None
        m = _ITER.match(parts[i + 2])
        if m is None:
            return None
        frame = Frame(node, prefix + node.id, parts[i + 1], int(m.group(1)))
        frames.append(frame)
        prefix = frame.prefix
        nodes = list(node.steps)
        i += 3


def locate_instance(recipe: LoadedRecipe, path: str) -> tuple[Located, str] | None:
    """``(located group, instance id)`` for an instance path such as ``slices/x7f3a9c2``."""
    if "/" not in path:
        return None
    head, inst = path.rsplit("/", 1)
    loc = locate(recipe, head)
    if loc is None or not isinstance(loc.node, Group) or _ITER.match(inst):
        return None
    return loc, inst


def iterated_ids(group: Group) -> list[str]:
    """Steps an iteration after the first runs: ``repeat_from`` and every step after it."""
    ids = [s.id for s in group.steps]
    if group.repeat_until is None or group.repeat_from is None:
        return ids
    return ids[ids.index(group.repeat_from):]


def judges(group: Group) -> list[str]:
    return refs.parse_condition(group.repeat_until) if group.repeat_until else []


def child_path(frame: Frame | None, child_id: str) -> str:
    """Path of a child of ``frame``'s group as seen from that iteration (top level when no frame)."""
    if frame is None:
        return child_id
    if frame.iteration > 1 and child_id not in iterated_ids(frame.group):
        return f"{frame.instance_path}/i1/{child_id}"
    return frame.prefix + child_id


def walk_groups(nodes: list[Any]) -> Iterator[tuple[Group, Group | None]]:
    """Every group in the recipe, with its enclosing group (``None`` at top level)."""
    for n in nodes:
        if isinstance(n, Group):
            yield n, None
            for inner in n.steps:
                if isinstance(inner, Group):
                    yield inner, n


def is_judge(loc: Located) -> bool:
    return loc.frame is not None and isinstance(loc.node, Step) and loc.node.id in judges(loc.frame.group)


# ---------------------------------------------------------------------------
# The view
# ---------------------------------------------------------------------------


def _walk(value: Any, path: tuple[str, ...]) -> Any:
    for seg in path:
        if isinstance(value, dict) and seg in value:
            value = value[seg]
        elif isinstance(value, list) and seg.isdigit() and int(seg) < len(value):
            value = value[int(seg)]
        else:
            return None
    return value


def _content_sha(item: Any) -> str:
    content = {k: v for k, v in item.items() if k != "id"} if isinstance(item, dict) else item
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


class View:
    """Group state of one run, derived from its events.

    ``rs`` is the run's state; ``cas`` its artifact store (read for outputs and
    items). Queries are memoized for the life of the view, so build a new one
    after appending events.
    """

    def __init__(self, recipe: LoadedRecipe, events: list[Event], rs: RunState, cas: Any):
        self.recipe = recipe
        self.events = events
        self.rs = rs
        self.cas = cas
        self.expansions: dict[str, Event] = {}
        self.iterations: dict[str, list[Event]] = {}
        self.limits: dict[str, list[Event]] = {}
        self.decisions: dict[str, list[Event]] = {}
        self.accepted: dict[str, Event] = {}  # step path -> last step_passed / step_imported
        self.started = events[0].data if events and events[0].type == "run_started" else {}
        self.level: str | None = None
        for ev in events:
            t = ev.type
            if t == "group_expanded":
                self.expansions[ev.step_path] = ev
            elif t == "iteration_started":
                self.iterations.setdefault(ev.step_path, []).append(ev)
            elif t == "iteration_limit_reached":
                self.limits.setdefault(ev.step_path, []).append(ev)
            elif t == "human_decision" and ev.data.get("kind") == "iteration_limit":
                self.decisions.setdefault(ev.step_path, []).append(ev)
            elif t in ("step_passed", "step_imported"):
                self.accepted[ev.step_path] = ev
            elif t in ("complexity_set", "retriage_applied") and "level" in ev.data:
                self.level = ev.data["level"]
        self._memo: dict[tuple[str, str], str] = {}

    # -- small queries ------------------------------------------------------

    def state(self, path: str) -> str:
        """State of any node path: a step's own state, or a group's aggregate state."""
        loc = locate(self.recipe, path)
        if loc is None:
            return "blocked_on_deps"
        return self.node_state(loc.node, path, loc.frame)

    def node_state(self, node: Step | Group, path: str, outer: Frame | None) -> str:
        if isinstance(node, Step):
            return self.rs.step(path).state
        key = ("group", path)
        if key not in self._memo:
            self._memo[key] = self._group_state(node, path, outer)
        return self._memo[key]

    def deps_met(self, node: Step | Group, outer: Frame | None) -> bool:
        for dep in node.depends_on:
            dep_node = self._scope_node(outer, dep)
            if dep_node is None or self.node_state(dep_node, child_path(outer, dep), outer) not in SATISFIES_DEPS:
                return False
        return True

    def _scope_node(self, outer: Frame | None, node_id: str) -> Step | Group | None:
        nodes = outer.group.steps if outer is not None else self.recipe.recipe.steps
        return next((n for n in nodes if n.id == node_id), None)

    def expansion(self, group_path: str) -> dict[str, Any] | None:
        ev = self.expansions.get(group_path)
        return ev.data if ev is not None else None

    def live_items(self, group_path: str) -> list[dict[str, Any]]:
        exp = self.expansion(group_path)
        return list(exp.get("items") or []) if exp else []

    def item_entry(self, group_path: str, instance: str) -> dict[str, Any] | None:
        return next((i for i in self.live_items(group_path) if i["id"] == instance), None)

    def condition(self, path: str) -> dict[str, Any] | None:
        ev = self.accepted.get(path)
        return ev.data.get("condition") if ev is not None else None

    # -- instances ----------------------------------------------------------

    def current_iteration(self, instance_path: str) -> tuple[int, int] | None:
        """``(iteration, budget_base)`` of a started instance, else ``None``."""
        its = self.iterations.get(instance_path)
        if not its:
            return None
        last = its[-1].data
        return int(last["iteration"]), int(last.get("budget_base") or 0)

    def frame(self, group: Group, group_path: str, instance: str) -> Frame | None:
        cur = self.current_iteration(f"{group_path}/{instance}")
        return Frame(group, group_path, instance, cur[0]) if cur else None

    def judged_failed(self, frame: Frame) -> Event | None:
        """The ``step_passed`` of a judge in this iteration whose gates failed, if any."""
        for j in judges(frame.group):
            p = child_path(frame, j)
            if self.rs.step(p).state == "passed":
                cond = self.condition(p)
                if cond is not None and cond.get("gates_passed") is False:
                    return self.accepted[p]
        return None

    def limit_for(self, instance_path: str, judged: Event) -> Event | None:
        for ev in reversed(self.limits.get(instance_path, [])):
            if ev.data.get("judged_seq") == judged.seq:
                return ev
        return None

    def abandoned(self, instance_path: str) -> bool:
        decs = self.decisions.get(instance_path) or []
        return bool(decs) and decs[-1].data.get("decision") == "abandon"

    def pending_limit(self, group: Group, group_path: str, instance: str) -> Event | None:
        """The open ``iteration_limit_reached`` of a live instance, if the owner owes a decision."""
        ipath = f"{group_path}/{instance}"
        if self.abandoned(ipath) or self.item_entry(group_path, instance) is None:
            return None
        f = self.frame(group, group_path, instance)
        failed = self.judged_failed(f) if f else None
        if failed is None:
            return None
        lim = self.limit_for(ipath, failed)
        if lim is None:
            return None
        decided = any(d.seq > lim.seq for d in self.decisions.get(ipath, []))
        return None if decided else lim

    def instance_state(self, group: Group, group_path: str, instance: str) -> str:
        ipath = f"{group_path}/{instance}"
        if self.item_entry(group_path, instance) is None:
            return "superseded"
        if self.abandoned(ipath):
            return "abandoned"
        f = self.frame(group, group_path, instance)
        if f is None:
            return "not_started"
        if self.judged_failed(f) is not None:
            return "escalated" if self.pending_limit(group, group_path, instance) is not None else "active"
        for child in group.steps:
            if self.node_state(child, child_path(f, child.id), f) not in SATISFIES_DEPS:
                return "active"
        return "passed"

    # -- groups -------------------------------------------------------------

    def source(self, group: Group, outer: Frame | None) -> tuple[str, tuple[str, ...]] | None:
        """``(source step path, JSON path)`` of a ``foreach`` group in this scope."""
        if not group.foreach:
            return None
        ref = refs.parse(group.foreach)
        if ref.kind == "sibling_output":
            return child_path(outer, ref.step or ""), ref.path
        return ref.step or "", ref.path

    def needs_expansion(self, group: Group, group_path: str, outer: Frame | None) -> bool:
        exp = self.expansion(group_path)
        if not group.foreach:
            return exp is None
        src = self.source(group, outer)
        assert src is not None
        state = self.rs.step(src[0]).state
        if state == "skipped":
            mode = group.foreach_if_source_skipped or "skip"
            return exp is None or exp.get("mode") != mode
        if state not in SATISFIES_DEPS:
            return False
        reg = self.accepted.get(src[0])
        return reg is not None and (exp is None or exp.get("source_sha256") != reg.data.get("output_sha256"))

    def _group_state(self, group: Group, group_path: str, outer: Frame | None) -> str:
        if not self.deps_met(group, outer):
            return "blocked_on_deps"
        exp = self.expansion(group_path)
        if exp is None:
            return "blocked_on_deps"
        if exp.get("mode") == "skip":
            return "skipped"
        if self.needs_expansion(group, group_path, outer):
            return "active"
        states = [self.instance_state(group, group_path, i["id"]) for i in exp.get("items") or []]
        return "passed" if all(s == "passed" for s in states) else "active"

    def build_expansion(self, group: Group, group_path: str, outer: Frame | None) -> dict[str, Any]:
        """``group_expanded`` data for a group that ``needs_expansion``; stores item blobs in CAS."""
        exp = self.expansion(group_path)
        if not group.foreach:
            return {"mode": "single", "items": [{"id": new_instance_id()}]}
        src = self.source(group, outer)
        assert src is not None
        if self.rs.step(src[0]).state == "skipped":
            mode = group.foreach_if_source_skipped or "skip"
            data: dict[str, Any] = {"mode": mode, "source": group.foreach, "source_sha256": None, "items": []}
            if mode == "once":
                sha = self.started.get("inputs_sha256")
                content = json.loads(self.cas.read(sha)) if sha else {}
                data["items"] = [self._store_item(content, new_instance_id())]
            return data
        reg = self.accepted[src[0]].data
        items = _walk(json.loads(self.cas.read(reg["output_sha256"])), src[1])
        items = items if isinstance(items, list) else []
        prev = {i["id"]: i for i in (exp.get("items") or [])} if exp and exp.get("mode") == "foreach" else {}
        out_items, kept, changed, added = [], [], [], []
        for item in items:
            echoed = item.get("id") if isinstance(item, dict) else None
            if isinstance(echoed, str) and echoed in prev:
                entry = self._store_item(item, echoed)
                (kept if entry["content_sha256"] == prev[echoed].get("content_sha256") else changed).append(echoed)
            else:
                entry = self._store_item(item, new_instance_id())
                added.append(entry["id"])
            out_items.append(entry)
        data = {"mode": "foreach", "source": group.foreach, "source_sha256": reg["output_sha256"], "items": out_items}
        if exp is not None:
            ids = {e["id"] for e in out_items}
            data.update(kept=kept, changed=changed, added=added, superseded=[i for i in prev if i not in ids])
        return data

    def _store_item(self, item: Any, instance: str) -> dict[str, Any]:
        content = {k: v for k, v in item.items() if k != "id"} if isinstance(item, dict) else item
        blob = {**content, "id": instance} if isinstance(content, dict) else content
        entry = {"id": instance, "sha256": self.cas.put(canonical_json(blob).encode("utf-8")), "content_sha256": _content_sha(item)}
        if isinstance(item, dict) and isinstance(item.get("title"), str):
            entry["title"] = item["title"]
        return entry

    def effective_paths(self, frame: Frame) -> list[str]:
        """Step paths that make up an instance as of its current iteration (nested instances included)."""
        out = []
        for child in frame.group.steps:
            p = child_path(frame, child.id)
            if isinstance(child, Step):
                out.append(p)
                continue
            for item in self.live_items(p):
                f = self.frame(child, p, item["id"])
                if f is not None:
                    out += self.effective_paths(f)
        return out

    # -- liveness -----------------------------------------------------------

    def live_reason(self, path: str, *, dispatch: bool = True) -> str | None:
        """Why a path inside groups is not current work, or ``None`` when it is.

        Current work: every enclosing instance is live (not superseded or
        abandoned), started, and the path is the one its current iteration
        uses. For dispatching, also: every enclosing group's dependencies are
        met and its expansion is up to date, and the iteration has not been
        ended by a judge.
        """
        loc = locate(self.recipe, path)
        if loc is None:
            return f"{path} is not a step of {self.recipe.recipe.ref}"
        if not loc.frames:
            return None
        outer: Frame | None = None
        expected = ""
        names = path.split("/")
        k = 0
        for f in loc.frames:
            ipath = f"{f.group_path}/{f.instance}"
            if dispatch and self._group_state(f.group, f.group_path, outer) == "blocked_on_deps":
                return f"group {f.group_path} is waiting for its dependencies"
            if dispatch and self.needs_expansion(f.group, f.group_path, outer):
                return f"group {f.group_path} is waiting to be expanded again"
            st = self.instance_state(f.group, f.group_path, f.instance)
            if st in ("superseded", "abandoned", "not_started"):
                return f"instance {ipath} is {st.replace('_', ' ')}"
            cur = self.frame(f.group, f.group_path, f.instance)
            assert cur is not None
            if dispatch and self.judged_failed(cur) is not None:
                return f"iteration {cur.iteration} of {ipath} has ended"
            nxt = names[k + 3]
            expected = child_path(cur, nxt)
            if not path.startswith(expected) or not (path == expected or path[len(expected)] == "/"):
                return f"{path} is not part of the current iteration of {ipath} (i{cur.iteration})"
            outer = cur
            k += 3
        return None

    def pending_limits(self) -> list[tuple[str, Event]]:
        """``(instance path, iteration_limit_reached)`` for every open iteration-limit escalation."""
        out = []
        for ipath, evs in sorted(self.limits.items()):
            hit = locate_instance(self.recipe, ipath)
            if hit is None:
                continue
            loc, inst = hit
            assert isinstance(loc.node, Group)
            if loc.frames and self.live_reason(loc.path, dispatch=False) is not None:
                continue  # inside a superseded or abandoned outer instance
            lim = self.pending_limit(loc.node, loc.path, inst)
            if lim is not None:
                out.append((ipath, lim))
        return out

    # -- input values -------------------------------------------------------

    def item_value(self, loc: Located) -> Any:
        """The current item of the innermost ``foreach`` (or ``once``) instance enclosing ``loc``."""
        for f in reversed(loc.frames):
            if f.group.foreach:
                entry = self.item_entry(f.group_path, f.instance)
                if entry is None:
                    raise LookupError(f"instance {f.instance_path} has no current item")
                return json.loads(self.cas.read(entry["sha256"]))
        raise LookupError("no enclosing foreach group")

    def previous_findings(self, loc: Located) -> dict[str, Any] | None:
        """Open findings and gate reasons of the previous iteration; ``None`` in iteration 1."""
        f = next((fr for fr in reversed(loc.frames) if fr.group.repeat_until), None)
        if f is None:
            raise LookupError("no enclosing repeat_until group")
        if f.iteration == 1:
            return None
        prev = f.at(f.iteration - 1)
        findings: list[dict[str, Any]] = []
        reasons: list[str] = []
        for j in judges(f.group):
            ev = self.accepted.get(child_path(prev, j))
            if ev is None:
                continue
            out = json.loads(self.cas.read(ev.data["output_sha256"])) if ev.data.get("output_sha256") else None
            if isinstance(out, dict) and isinstance(out.get("findings"), list):
                findings += [{"step": j, **x} for x in out["findings"] if isinstance(x, dict)]
            cond = ev.data.get("condition") or {}
            reasons += cond.get("reasons") or []
        value: dict[str, Any] = {"iteration": prev.iteration, "findings": findings, "gate_reasons": reasons}
        started = next((e for e in reversed(self.iterations.get(f.instance_path, [])) if e.data.get("iteration") == f.iteration), None)
        if started is not None and started.data.get("note"):
            value["owner_note"] = started.data["note"]
        return value

    def group_outputs(self, group: Group, group_path: str) -> list[dict[str, Any]]:
        """``steps.<group>.outputs``: per live instance, in item order, its steps' final outputs."""
        out = []
        for entry in self.live_items(group_path):
            f = self.frame(group, group_path, entry["id"])
            outputs: dict[str, Any] = {}
            if f is not None:
                for child in group.steps:
                    ev = self.accepted.get(child_path(f, child.id))
                    if isinstance(child, Step) and ev is not None and ev.data.get("output_sha256"):
                        outputs[child.id] = json.loads(self.cas.read(ev.data["output_sha256"]))
            item = json.loads(self.cas.read(entry["sha256"])) if group.foreach else None
            out.append({"id": entry["id"], "item": item, "outputs": outputs})
        return out

    # -- foreach sources ----------------------------------------------------

    def fed_groups(self, loc: Located) -> list[tuple[Group, str, tuple[str, ...]]]:
        """``(group, group path, JSON path)`` for every expanded group whose ``foreach`` source is ``loc``."""
        out = []
        for g, parent in walk_groups(self.recipe.recipe.steps):
            if not g.foreach or not self._feeds(g, parent, loc):
                continue
            path = refs.parse(g.foreach).path
            if loc.frame is not None:
                gp = child_path(loc.frame, g.id)
                if gp in self.expansions:
                    out.append((g, gp, path))
                continue
            for gp in self.expansions:
                gl = locate(self.recipe, gp)
                if gl is not None and gl.node is g:
                    out.append((g, gp, path))
        return out

    @staticmethod
    def _feeds(g: Group, parent: Group | None, loc: Located) -> bool:
        """Whether ``loc`` is the foreach source of group ``g`` (enclosed by ``parent``)."""
        ref = refs.parse(g.foreach or "")
        if ref.step != loc.node.id:
            return False
        if ref.kind == "step_output":
            return not loc.frames
        return ref.kind == "sibling_output" and loc.frame is not None and parent is loc.frame.group

    def foreach_id_problems(self, loc: Located, output: Any) -> list[str]:
        """Intake check for a ``foreach`` source: echoed item ids must be known and unique (§5.8)."""
        problems: list[str] = []
        fed = self.fed_groups(loc)
        for g, parent in walk_groups(self.recipe.recipe.steps):
            if not g.foreach or not self._feeds(g, parent, loc):
                continue
            ref = refs.parse(g.foreach)
            known = {i["id"] for g2, gp, _p in fed if g2 is g for i in self.live_items(gp)}
            items = _walk(output, ref.path)
            if not isinstance(items, list):
                continue
            seen: set[str] = set()
            where = ".".join(ref.path)
            for n, item in enumerate(items):
                iid = item.get("id") if isinstance(item, dict) else None
                if iid is None:
                    continue
                if iid not in known:
                    problems.append(
                        f"output.{where}[{n}]: id {iid!r} is not a current item id; echo the id of each item you keep "
                        "and omit id on new items (ids are assigned by the runtime)"
                    )
                elif iid in seen:
                    problems.append(f"output.{where}[{n}]: id {iid!r} is used by more than one item")
                seen.add(iid)
        return problems

    def with_item_ids(self, loc: Located, output: Any) -> Any:
        """A copy of a foreach source's output with each item's runtime id set (for a revision packet)."""
        fed = self.fed_groups(loc)
        if len(fed) != 1:
            return output
        _g, gp, path = fed[0]
        exp = self.expansion(gp) or {}
        if exp.get("mode") != "foreach" or exp.get("source_sha256") is None:
            return output
        value = json.loads(json.dumps(output))
        items = _walk(value, path)
        entries = exp.get("items") or []
        if isinstance(items, list) and len(items) == len(entries):
            for item, entry in zip(items, entries):
                if isinstance(item, dict):
                    item["id"] = entry["id"]
        return value


def describe(view: View, group: Group, group_path: str) -> dict[str, Any]:
    """Plain facts about a group for status and records: instances, iterations, states."""
    exp = view.expansion(group_path)
    out: dict[str, Any] = {"state": view.state(group_path), "instances": []}
    if exp is None:
        return out
    out["mode"] = exp.get("mode")
    for entry in exp.get("items") or []:
        f = view.frame(group, group_path, entry["id"])
        inst: dict[str, Any] = {
            "id": entry["id"],
            "title": entry.get("title"),
            "state": view.instance_state(group, group_path, entry["id"]),
            "iteration": f.iteration if f else None,
        }
        if group.max_iterations:
            cur = view.current_iteration(f"{group_path}/{entry['id']}")
            inst["max_iterations"] = group.max_iterations
            inst["budget_base"] = cur[1] if cur else 0
        if f is not None:
            inst["steps"] = {c.id: view.node_state(c, child_path(f, c.id), f) for c in group.steps}
        out["instances"].append(inst)
    return out


def summary_line(info: dict[str, Any], group: Group) -> str:
    """"3 instances: 2 passed, 1 active (iteration 2 of 3)"."""
    insts = info["instances"]
    if not insts:
        return info["state"]
    counts: dict[str, int] = {}
    for i in insts:
        counts[i["state"]] = counts.get(i["state"], 0) + 1
    parts = [f"{n} {s.replace('_', ' ')}" for s, n in counts.items()]
    line = f"{len(insts)} instance{'s' if len(insts) != 1 else ''}: " + ", ".join(parts)
    loops = [i for i in insts if i["state"] in ("active", "escalated") and i.get("max_iterations")]
    if loops:
        line += "; " + ", ".join(
            f"{i.get('title') or i['id']}: iteration {i['iteration'] - i.get('budget_base', 0)} of {i['max_iterations']}" for i in loops
        )
    return line
