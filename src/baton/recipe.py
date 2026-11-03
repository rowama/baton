"""Recipe loading, validation (§5.3), neutrality lint, and per-level plans.

``load_recipe`` either returns a fully checked recipe or raises ``RecipeError``
carrying *every* problem found, each with a stable ``code``. Checks run in
stages; a stage that fails stops the later ones only when they could not
produce meaningful results (e.g. no structural checks on an unparsable file).
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

import jinja2
from jinja2 import meta as jinja_meta
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import ValidationError

from . import refs, versions
from . import vocab as vocab_mod
from .data import YamlError, load_yaml, read_text
from .models import (
    IMPLICIT_GATE_TYPES,
    FindingsGate,
    Group,
    HumanGate,
    Issue,
    Plan,
    PlanGate,
    PlanLevel,
    PlanStep,
    Recipe,
    Requires,
    ReviewGate,
    ScriptGate,
    Step,
)
from .vocab import Vocabulary

RECIPE_FILE = "recipe.yaml"
FINDINGS_SCHEMA_REF = "baton:findings"
FORBIDDEN_KEYS = frozenset({"worker", "model", "adapter", "provider", "profile", "api_key", "auth"})
PUBLISH_VARIABLES = frozenset({"paths", "run", "project"})
MAX_GROUP_DEPTH = 2  # a group may contain a group, but no deeper (§5.4)
DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
_TEXT_DIRS = ("prompts", "templates", "schemas", "static")
# Ids name roles, never positions (§5.8): "step1", "s2", "phase_3", "step01_design", "review_2".
POSITIONAL_ID = re.compile(r"^(?:step|stage|phase|part|task)_?\d+(?:_|$)|^[sp]_?\d+$|_\d+$")

Node = Step | Group


class RecipeError(Exception):
    def __init__(self, issues: list[Issue]):
        self.issues = issues
        errors = [i for i in issues if i.severity == "error"]
        super().__init__("\n".join(str(i) for i in errors) or "recipe invalid")

    def codes(self) -> set[str]:
        return {i.code for i in self.issues if i.severity == "error"}


@dataclass
class LoadedRecipe:
    recipe: Recipe
    root: Path
    sha256: str
    vocab: Vocabulary
    warnings: list[Issue] = field(default_factory=list)
    schemas: dict[str, dict] = field(default_factory=dict)  # recipe-relative path -> schema


def load_recipe(root: str | Path) -> LoadedRecipe:
    loaded, issues = validate_recipe(root)
    if loaded is None or any(i.severity == "error" for i in issues):
        raise RecipeError(issues)
    return loaded


def validate_recipe(root: str | Path) -> tuple[LoadedRecipe | None, list[Issue]]:
    checker = _Checker(Path(root))
    loaded = checker.run()
    return loaded, checker.issues


# ---------------------------------------------------------------------------
# Scopes: the step lists a step id can be resolved in
# ---------------------------------------------------------------------------


@dataclass
class _Scope:
    """One list of sibling steps (the top level, or one group's steps)."""

    group: Group | None
    nodes: dict[str, Node]
    ancestors: dict[str, set[str]] = field(default_factory=dict)


@dataclass
class _Place:
    """Where a node sits: its scope and its chain of enclosing groups (outermost first)."""

    scope: _Scope
    chain: tuple[Group, ...]

    @property
    def path(self) -> str:
        return "/".join(g.id for g in self.chain)


class _Checker:
    def __init__(self, root: Path):
        self.root = root
        self.issues: list[Issue] = []
        self.schemas: dict[str, dict] = {}
        self.recipe: Recipe
        self.vocab: Vocabulary
        self.places: dict[str, _Place] = {}
        self.top: _Scope

    # -- reporting -------------------------------------------------------

    def error(self, code: str, where: str, message: str) -> None:
        self.issues.append(Issue(code=code, where=where, message=message))

    def warn(self, code: str, where: str, message: str) -> None:
        self.issues.append(Issue(code=code, where=where, message=message, severity="warning"))

    def has_errors(self) -> bool:
        return any(i.severity == "error" for i in self.issues)

    def where(self, node: Node) -> str:
        place = self.places.get(node.id)
        prefix = place.path + "/" if place and place.path else ""
        return f"{prefix}{node.id}"

    # -- driver ----------------------------------------------------------

    def run(self) -> LoadedRecipe | None:
        raw = self._read()
        if raw is None or not self._check_versions(raw):
            return None
        stripped = self._lint_neutrality(raw, RECIPE_FILE)
        try:
            self.recipe = Recipe.model_validate(stripped)
        except ValidationError as e:
            self._translate(e, stripped)
            return None
        n_before = len(self.issues)
        self._index()
        if any(i.severity == "error" for i in self.issues[n_before:]):
            return None
        self._check_graph()
        self._check_run_inputs()
        for node, place in self._walk():
            if isinstance(node, Group):
                self._check_group(node, place)
            else:
                self._check_step(node, place)
        self._check_sme()
        self._check_complexity()
        self._lint_crosswalks()
        self._lint_text_files()
        if self.has_errors():
            return None
        return LoadedRecipe(
            recipe=self.recipe,
            root=self.root,
            sha256=package_sha256(self.root),
            vocab=self.vocab,
            warnings=[i for i in self.issues if i.severity == "warning"],
            schemas=self.schemas,
        )

    def _read(self) -> Any:
        path = self.root / RECIPE_FILE
        if not path.is_file():
            self.error("file.missing", RECIPE_FILE, f"no {RECIPE_FILE} in {self.root}")
            return None
        try:
            raw = load_yaml(path)
        except YamlError as e:
            code = "yaml.duplicate_key" if "duplicate key" in str(e) else "yaml.invalid"
            self.error(code, RECIPE_FILE, str(e))
            return None
        if not isinstance(raw, dict):
            self.error("recipe.not_a_mapping", RECIPE_FILE, "recipe.yaml must be a YAML mapping")
            return None
        return raw

    def _check_versions(self, raw: dict) -> bool:
        ok = True
        fmt = raw.get("format")
        if fmt not in versions.RECIPE_FORMATS:
            self.error(
                "format.unsupported",
                "format",
                f"recipe format {fmt!r} is not supported by this runtime "
                f"(supported: {', '.join(versions.RECIPE_FORMATS)})",
            )
            ok = False
        vocab_id = raw.get("capabilities_vocab")
        try:
            self.vocab = vocab_mod.load(str(vocab_id))
        except vocab_mod.UnknownVocabulary:
            self.error(
                "vocab.unsupported",
                "capabilities_vocab",
                f"capability vocabulary {vocab_id!r} is not known "
                f"(supported: {', '.join(vocab_mod.supported())})",
            )
            ok = False
        return ok

    # -- neutrality ------------------------------------------------------

    def _lint_neutrality(self, raw: dict, filename: str) -> dict:
        """Report vendor-specific keys and values; return a copy without forbidden keys."""
        stripped = copy.deepcopy(raw)

        def visit(value: Any, where: str) -> Any:
            if isinstance(value, dict):
                out = {}
                for k, v in value.items():
                    key = str(k)
                    loc = f"{where}.{key}" if where else key
                    if key in FORBIDDEN_KEYS:
                        self.error(
                            "neutrality.forbidden_key",
                            f"{filename}:{loc}",
                            f"key {key!r} is not allowed in a recipe; recipes declare capabilities, "
                            "never workers, models or vendors",
                        )
                        continue
                    self._vendor_value(key, f"{filename}:{loc}")
                    out[k] = visit(v, loc)
                return out
            if isinstance(value, list):
                return [visit(v, f"{where}[{i}]") for i, v in enumerate(value)]
            if isinstance(value, str):
                self._vendor_value(value, f"{filename}:{where}")
            return value

        return visit(stripped, "")

    def _vendor_value(self, text: str, where: str) -> None:
        hit = self.vocab.find_vendor_string(text)
        if hit:
            self.error(
                "neutrality.vendor_string",
                where,
                f"{text!r} contains vendor string {hit!r}; recipes must be model-neutral",
            )

    def _lint_crosswalks(self) -> None:
        cw_dir = self.root / "crosswalks"
        if not cw_dir.is_dir():
            return
        for f in sorted(cw_dir.glob("*.yaml")):
            rel = f.relative_to(self.root).as_posix()
            try:
                data = load_yaml(f)
            except YamlError as e:
                self.error("yaml.invalid", rel, str(e))
                continue
            if isinstance(data, (dict, list)):
                self._lint_neutrality(data if isinstance(data, dict) else {"_": data}, rel)
            for issue in crosswalk_issues(data, self.recipe, rel):
                self.issues.append(issue)

    def _lint_text_files(self) -> None:
        for d in _TEXT_DIRS:
            base = self.root / d
            if not base.is_dir():
                continue
            for f in sorted(p for p in base.rglob("*") if p.is_file()):
                try:
                    text = read_text(f)
                except (UnicodeDecodeError, OSError):
                    continue
                hit = self.vocab.find_vendor_string(text)
                if hit:
                    self.warn(
                        "neutrality.vendor_mention",
                        f.relative_to(self.root).as_posix(),
                        f"mentions vendor string {hit!r} (allowed in prose, but check it is not an instruction)",
                    )

    # -- pydantic errors -------------------------------------------------

    def _translate(self, exc: ValidationError, raw: dict) -> None:
        for err in exc.errors():
            where = _readable_loc(raw, err["loc"])
            etype = err["type"]
            ctx = err.get("ctx") or {}
            if etype == "union_tag_invalid" and "type" in str(ctx.get("discriminator", "")):
                tag = ctx.get("tag")
                if tag in IMPLICIT_GATE_TYPES:
                    self.error(
                        "gate.implicit_type",
                        where,
                        f"gate type {tag!r} is implicit and enforced automatically; do not declare it",
                    )
                else:
                    self.error(
                        "gate.unknown_type",
                        where,
                        f"unknown gate type {tag!r} (known: {ctx.get('expected_tags')})",
                    )
            elif etype == "extra_forbidden":
                self.error("recipe.unknown_key", where, f"unknown key {str(err['loc'][-1])!r}")
            elif etype == "missing":
                self.error("recipe.missing_key", where, f"required key {str(err['loc'][-1])!r} is missing")
            else:
                self.error("recipe.invalid_value", where, err["msg"])

    # -- index and graph -------------------------------------------------

    def _index(self) -> None:
        self.top = self._scope(None, self.recipe.steps, ())

    def _scope(self, group: Group | None, nodes: list[Node], chain: tuple[Group, ...]) -> _Scope:
        scope = _Scope(group=group, nodes={})
        for node in nodes:
            if node.id in self.places:
                self.error("step.duplicate_id", node.id, f"step id {node.id!r} is used more than once")
                continue
            scope.nodes[node.id] = node
            self.places[node.id] = _Place(scope=scope, chain=chain)
            if POSITIONAL_ID.search(node.id):
                self.error(
                    "step.positional_id",
                    self.where(node),
                    f"step id {node.id!r} looks positional; ids name a role (e.g. 'design', 'code_review') "
                    "so that inserting or reordering steps never renumbers or reuses them (§5.8)",
                )
        for node in nodes:
            if isinstance(node, Group):
                inner = chain + (node,)
                if len(inner) > MAX_GROUP_DEPTH:
                    self.error(
                        "group.too_deep",
                        self.where(node),
                        f"groups nest at most one level; {self.where(node)!r} is nested {len(inner) - 1} levels deep",
                    )
                    continue
                self._scope(node, node.steps, inner)
        return scope

    def _walk(self) -> Iterator[tuple[Node, _Place]]:
        def visit(nodes: list[Node]) -> Iterator[tuple[Node, _Place]]:
            for n in nodes:
                place = self.places.get(n.id)
                if place is None or place.scope.nodes.get(n.id) is not n:
                    continue
                yield n, place
                if isinstance(n, Group) and len(place.chain) < MAX_GROUP_DEPTH:
                    yield from visit(n.steps)

        return visit(self.recipe.steps)

    def _scopes(self) -> Iterator[_Scope]:
        seen = {id(self.top)}
        yield self.top
        for _, place in self._walk():
            if id(place.scope) not in seen:
                seen.add(id(place.scope))
                yield place.scope

    def _check_graph(self) -> None:
        for scope in self._scopes():
            for node in scope.nodes.values():
                for dep in node.depends_on:
                    if dep == node.id:
                        self.error("graph.cycle", self.where(node), f"{node.id!r} depends on itself")
                    elif dep not in scope.nodes:
                        hint = (
                            " (inside a group, depends_on names sibling steps)"
                            if scope.group is not None
                            else (" (it is inside a group; depend on the group)" if dep in self.places else "")
                        )
                        self.error(
                            "graph.unknown_dependency",
                            self.where(node),
                            f"depends_on names unknown step {dep!r}{hint}",
                        )
            self._find_cycles(scope)
            for node_id in scope.nodes:
                scope.ancestors[node_id] = self._closure(scope, node_id)

    def _find_cycles(self, scope: _Scope) -> None:
        state: dict[str, int] = {}  # 1 = visiting, 2 = done
        reported: set[frozenset[str]] = set()

        def dfs(nid: str, stack: list[str]) -> None:
            state[nid] = 1
            stack.append(nid)
            for dep in scope.nodes[nid].depends_on:
                if dep not in scope.nodes or dep == nid:
                    continue
                if state.get(dep) == 1:
                    cycle = stack[stack.index(dep):] + [dep]
                    key = frozenset(cycle)
                    if key not in reported:
                        reported.add(key)
                        self.error(
                            "graph.cycle",
                            self.where(scope.nodes[dep]),
                            "dependency cycle: " + " -> ".join(cycle),
                        )
                elif state.get(dep) is None:
                    dfs(dep, stack)
            stack.pop()
            state[nid] = 2

        for nid in scope.nodes:
            if nid not in state:
                dfs(nid, [])

    @staticmethod
    def _closure(scope: _Scope, node_id: str) -> set[str]:
        seen: set[str] = set()
        todo = list(scope.nodes[node_id].depends_on)
        while todo:
            d = todo.pop()
            if d in seen or d not in scope.nodes or d == node_id:
                continue
            seen.add(d)
            todo.extend(scope.nodes[d].depends_on)
        return seen

    def _top_ancestors(self, place: _Place, node: Node) -> set[str]:
        """Top-level ancestors of a node (via its outermost enclosing group if nested)."""
        top_id = place.chain[0].id if place.chain else node.id
        return self.top.ancestors.get(top_id, set())

    # -- files and schemas -----------------------------------------------

    def _file(self, rel: str, where: str, what: str) -> Path | None:
        p = PurePosixPath(rel.replace("\\", "/"))
        if p.is_absolute() or ".." in p.parts:
            self.error("file.outside_recipe", where, f"{what} {rel!r} must be a path inside the recipe")
            return None
        full = self.root / p
        if not full.is_file():
            self.error("file.missing", where, f"{what} {rel!r} does not exist")
            return None
        return full

    def _schema(self, rel: str, where: str) -> dict | None:
        if rel == FINDINGS_SCHEMA_REF:
            return versions.findings_json_schema()
        if rel in self.schemas:
            return self.schemas[rel]
        full = self._file(rel, where, "schema")
        if full is None:
            return None
        try:
            schema = json.loads(read_text(full))
        except json.JSONDecodeError as e:
            self.error("schema.invalid_json", where, f"{rel}: not valid JSON ({e})")
            return None
        if not isinstance(schema, dict):
            self.error("schema.invalid", where, f"{rel}: a schema must be a JSON object")
            return None
        declared = schema.get("$schema")
        if declared is not None and declared.rstrip("#") != DRAFT_2020_12:
            self.error("schema.wrong_draft", where, f"{rel}: declares {declared!r}; schemas must be JSON Schema 2020-12")
            return None
        try:
            Draft202012Validator.check_schema(schema)
        except SchemaError as e:
            self.error("schema.invalid", where, f"{rel}: not a valid JSON Schema 2020-12 ({e.message})")
            return None
        self.schemas[rel] = schema
        return schema

    # -- requirements ----------------------------------------------------

    def _check_requires(self, req: Requires, where: str) -> None:
        for cap in req.capabilities:
            if cap not in self.vocab.capabilities:
                self.error(
                    "vocab.unknown_capability",
                    where,
                    f"capability {cap!r} is not in {self.vocab.id}",
                )
        if req.tier is not None and req.tier not in self.vocab.tiers:
            self.error(
                "vocab.unknown_tier",
                where,
                f"tier {req.tier!r} is not one of {self.vocab.tiers}",
            )

    def _check_independence(self, node: Step, place: _Place, from_step: str, where: str) -> None:
        if from_step == node.id or from_step in place.scope.ancestors.get(node.id, set()):
            return
        scope_hint = " in the same group" if place.chain else ""
        self.error(
            "independence.bad_from_step",
            where,
            f"independence.from_step {from_step!r} must name this step or one of its ancestors{scope_hint}",
        )

    # -- references ------------------------------------------------------

    def _check_ref(
        self,
        raw: str,
        node: Node,
        place: _Place,
        where: str,
        allowed: Iterable[str] | None = None,
    ) -> refs.Ref | None:
        try:
            ref = refs.parse(raw)
        except refs.RefSyntaxError as e:
            self.error("ref.invalid", where, str(e))
            return None
        if allowed is not None and ref.kind not in allowed:
            return ref  # caller reports a context-specific error
        if ref.kind in refs.GROUP_ONLY and not place.chain:
            code = "ref.item_outside_group" if ref.kind == "item" else "ref.group_outside_group"
            self.error(code, where, f"{raw!r} is only valid inside a group")
            return None
        if ref.kind == "item" and not any(g.foreach for g in place.chain):
            self.error("ref.item_outside_foreach", where, f"{raw!r} needs an enclosing group with foreach")
        elif ref.kind == "previous_findings" and not any(g.repeat_until for g in place.chain):
            self.error(
                "ref.previous_iteration_outside_repeat",
                where,
                f"{raw!r} needs an enclosing group with repeat_until",
            )
        elif ref.kind in ("step_output", "step_artifact", "group_outputs", "human_revision"):
            self._check_steps_ref(ref, node, place, where)
        elif ref.kind in ("sibling_output", "sibling_artifact"):
            self._check_sibling_ref(ref, node, place, where)
        elif ref.kind == "run_input":
            self._check_run_input_ref(ref, where)
        elif ref.kind == "static":
            self._file(f"static/{ref.name}", where, "static file")
        return ref

    def _check_steps_ref(self, ref: refs.Ref, node: Node, place: _Place, where: str) -> None:
        target_id = ref.step or ""
        if target_id not in self.top.nodes:
            if target_id in self.places:
                self.error(
                    "ref.not_ancestor",
                    where,
                    f"{ref.raw!r}: step {target_id!r} is inside a group; refer to the group's "
                    "outputs (steps.<group>.outputs) or, from a sibling, group.steps.<id>",
                )
            else:
                self.error("ref.unknown_step", where, f"{ref.raw!r}: no step {target_id!r}")
            return
        if target_id not in self._top_ancestors(place, node):
            self.error(
                "ref.not_ancestor",
                where,
                f"{ref.raw!r}: {target_id!r} is not an ancestor of {self.where(node)!r} via depends_on",
            )
            return
        self._check_target(ref, self.top.nodes[target_id], where)

    def _check_sibling_ref(self, ref: refs.Ref, node: Node, place: _Place, where: str) -> None:
        target_id = ref.step or ""
        if target_id not in place.scope.nodes:
            self.error("ref.unknown_step", where, f"{ref.raw!r}: no step {target_id!r} in this group")
            return
        if target_id not in place.scope.ancestors.get(node.id, set()):
            self.error(
                "ref.not_ancestor",
                where,
                f"{ref.raw!r}: {target_id!r} is not an ancestor of {node.id!r} within the group",
            )
            return
        self._check_target(ref, place.scope.nodes[target_id], where)

    def _check_target(self, ref: refs.Ref, target: Node, where: str) -> None:
        if ref.kind == "group_outputs":
            if not isinstance(target, Group):
                self.error("ref.not_a_group", where, f"{ref.raw!r}: {target.id!r} is not a group; use .output")
            return
        if isinstance(target, Group):
            self.error("ref.group_has_no_output", where, f"{ref.raw!r}: {target.id!r} is a group; use steps.{target.id}.outputs")
            return
        if ref.kind in ("step_artifact", "sibling_artifact", "human_revision"):
            art = next((a for a in target.artifacts if a.name == ref.name), None)
            if art is None:
                self.error("ref.unknown_artifact", where, f"{ref.raw!r}: step {target.id!r} declares no artifact {ref.name!r}")
            elif ref.kind == "human_revision" and art.publish is None:
                self.error(
                    "ref.unpublished_artifact",
                    where,
                    f"{ref.raw!r}: artifact {ref.name!r} is not published, so it cannot have a human revision",
                )
            return
        if ref.path and target.output_schema:
            schema = self.schemas.get(target.output_schema) or (
                versions.findings_json_schema() if target.output_schema == FINDINGS_SCHEMA_REF else None
            )
            if schema is not None:
                status, key, _ = _subschema(schema, ref.path)
                if status == "missing":
                    self.warn(
                        "ref.unknown_output_field",
                        where,
                        f"{ref.raw!r}: {target.id!r} output schema declares no property {key!r}",
                    )
                elif status == "forbidden":
                    self.error(
                        "ref.unknown_output_field",
                        where,
                        f"{ref.raw!r}: {target.id!r} output schema does not allow property {key!r}",
                    )

    def _check_run_input_ref(self, ref: refs.Ref, where: str) -> None:
        ri = self.recipe.run_inputs
        if ri is None:
            self.error("ref.no_run_inputs", where, f"{ref.raw!r}: the recipe declares no run_inputs")
            return
        schema = self.schemas.get(ri.schema_)
        if schema is None:
            return  # reported when the schema itself is checked
        props = schema.get("properties")
        if isinstance(props, dict) and ref.name not in props:
            self.error("ref.unknown_run_input", where, f"{ref.raw!r}: run_inputs schema has no property {ref.name!r}")

    # -- steps -----------------------------------------------------------

    def _check_step(self, step: Step, place: _Place) -> None:
        w = self.where(step)
        self._file(step.prompt, f"{w}.prompt", "prompt")
        if step.doc_template:
            self._file(step.doc_template, f"{w}.doc_template", "doc template")
        if step.output_schema:
            self._schema(step.output_schema, f"{w}.output_schema")
        self._check_requires(step.requires, f"{w}.requires")

        _dupes(self, [i.name for i in step.inputs], "step.duplicate_input", f"{w}.inputs", "input")
        _dupes(self, [a.name for a in step.artifacts], "step.duplicate_artifact", f"{w}.artifacts", "artifact")
        for inp in step.inputs:
            self._check_ref(inp.from_, step, place, f"{w}.inputs.{inp.name}")

        for art in step.artifacts:
            if art.publish is not None:
                self._check_publish(art.publish.to, f"{w}.artifacts.{art.name}.publish.to")
                if place.chain:
                    self.error(
                        "publish.in_group",
                        f"{w}.artifacts.{art.name}.publish",
                        "publish is not allowed inside a group: its target cannot vary per instance (§10.4)",
                    )

        if step.protect is not None and step.workspace != "write":
            self.error(
                "step.protect_requires_write",
                f"{w}.protect",
                f"protect is only allowed on workspace: write steps (this step is workspace: {step.workspace})",
            )
        if step.effort is not None and step.effort_from is not None:
            self.error("step.effort_conflict", w, "declare effort or effort_from, not both")
        if step.effort_from is not None:
            self._check_ref(step.effort_from, step, place, f"{w}.effort_from")
        if step.independence is not None:
            self._check_independence(step, place, step.independence.from_step, f"{w}.independence")

        for i, gate in enumerate(step.gates):
            self._check_gate(step, place, gate, f"{w}.gates[{i}]")

    def _check_gate(self, step: Step, place: _Place, gate: Any, where: str) -> None:
        if gate.type == "schema" and not step.output_schema:
            self.error("gate.schema_without_output_schema", where, "a schema gate needs the step to declare output_schema")
        if isinstance(gate, FindingsGate) and step.output_schema != FINDINGS_SCHEMA_REF:
            self.error(
                "gate.findings_needs_findings_schema",
                where,
                f"a findings gate needs output_schema: {FINDINGS_SCHEMA_REF}",
            )
        if isinstance(gate, (FindingsGate, ReviewGate)) and not gate.advisory and not gate.block_on:
            self.error("gate.missing_block_on", where, f"a blocking {gate.type} gate needs block_on severities (or advisory: true)")
        if isinstance(gate, ReviewGate):
            self._file(gate.rubric, f"{where}.rubric", "rubric")
            self._check_requires(gate.reviewer_requires, f"{where}.reviewer_requires")
            if gate.independence is not None:
                self._check_independence(step, place, gate.independence.from_step, f"{where}.independence")
        if isinstance(gate, ScriptGate):
            try:
                _jinja.parse(gate.run)
            except jinja2.TemplateSyntaxError as e:
                self.error("gate.bad_template", f"{where}.run", f"template syntax error: {e.message}")

    def _check_publish(self, template: str, where: str) -> None:
        try:
            names = jinja_meta.find_undeclared_variables(_jinja.parse(template))
        except jinja2.TemplateSyntaxError as e:
            self.error("publish.bad_template", where, f"template syntax error: {e.message}")
            return
        bad = sorted(names - PUBLISH_VARIABLES)
        if bad:
            self.error(
                "publish.bad_variable",
                where,
                f"publish.to may use only {sorted(PUBLISH_VARIABLES)} variables; found {bad}",
            )

    # -- groups ----------------------------------------------------------

    def _check_group(self, group: Group, place: _Place) -> None:
        w = self.where(group)
        child_ids = {s.id for s in group.steps}

        if group.foreach is not None:
            self._check_foreach(group, place, w)
        elif group.foreach_if_source_skipped is not None:
            self.error("group.option_without_foreach", f"{w}.foreach_if_source_skipped", "only valid with foreach")

        if group.repeat_until is not None:
            try:
                for sid in refs.parse_condition(group.repeat_until):
                    if sid not in child_ids:
                        self.error(
                            "group.bad_repeat_until",
                            f"{w}.repeat_until",
                            f"condition refers to {sid!r}, which is not a step of this group",
                        )
            except refs.RefSyntaxError as e:
                self.error("group.bad_repeat_until", f"{w}.repeat_until", str(e))
            if group.max_iterations is None:
                self.error("group.missing_max_iterations", w, "repeat_until requires max_iterations (1-10)")
            elif not 1 <= group.max_iterations <= 10:
                self.error("group.max_iterations_range", f"{w}.max_iterations", f"max_iterations must be 1-10, got {group.max_iterations}")
            if group.repeat_from is not None and group.repeat_from not in child_ids:
                self.error("group.bad_repeat_from", f"{w}.repeat_from", f"{group.repeat_from!r} is not a step of this group")
            elif group.repeat_from is not None:
                # Iterations after the first rerun repeat_from and every step listed after it (§5.4).
                ids = [s.id for s in group.steps]
                repeated = set(ids[ids.index(group.repeat_from):])
                try:
                    judged = refs.parse_condition(group.repeat_until)
                except refs.RefSyntaxError:
                    judged = []
                for sid in judged:
                    if sid in child_ids and sid not in repeated:
                        self.error(
                            "group.judge_not_repeated",
                            f"{w}.repeat_until",
                            f"{sid!r} is listed before repeat_from {group.repeat_from!r}, so later iterations would never judge again",
                        )
                for s in group.steps:
                    if s.id not in repeated:
                        for dep in s.depends_on:
                            if dep in repeated:
                                self.error(
                                    "group.depends_on_repeated",
                                    f"{self.where(s)}.depends_on",
                                    f"{s.id!r} runs only in the first iteration (it is listed before repeat_from "
                                    f"{group.repeat_from!r}) but depends on {dep!r}, which repeats",
                                )
        else:
            if group.max_iterations is not None:
                self.error("group.option_without_repeat", f"{w}.max_iterations", "only valid with repeat_until")
            if group.repeat_from is not None:
                self.error("group.option_without_repeat", f"{w}.repeat_from", "only valid with repeat_until")

    def _check_foreach(self, group: Group, place: _Place, w: str) -> None:
        where = f"{w}.foreach"
        ref = self._check_ref(group.foreach or "", group, place, where, allowed=())
        if ref is None:
            return
        allowed = ("step_output",) if not place.chain else ("step_output", "sibling_output")
        if ref.kind not in allowed:
            self.error(
                "group.bad_foreach_source",
                where,
                f"foreach must name an array in an ancestor step's output (steps.<id>.output.<path>); got {ref.raw!r}",
            )
            return
        n_before = len(self.issues)
        if ref.kind == "step_output":
            self._check_steps_ref(ref, group, place, where)
            source = self.top.nodes.get(ref.step or "")
        else:
            self._check_sibling_ref(ref, group, place, where)
            source = place.scope.nodes.get(ref.step or "")
        if len(self.issues) > n_before or not isinstance(source, Step):
            if not any(i.code == "group.bad_foreach_source" for i in self.issues[n_before:]):
                self.error("group.bad_foreach_source", where, f"{ref.raw!r} is not a usable foreach source (see errors above)")
            return
        if not source.output_schema:
            self.error("group.bad_foreach_source", where, f"{source.id!r} declares no output_schema, so {ref.raw!r} cannot be checked to be an array")
            return
        schema = self._schema(source.output_schema, f"{self.where(source)}.output_schema")
        if schema is None:
            return
        status, key, sub = _subschema(schema, ref.path)
        if status != "found" or not _is_array(sub):
            self.error(
                "group.bad_foreach_source",
                where,
                f"{ref.raw!r} must be declared as an array in {source.output_schema}"
                + (f" (no property {key!r})" if key else ""),
            )
            return
        # Instance ids are runtime-assigned; workers only echo them on revision (§5.8).
        items = _resolve_local_ref(schema, sub.get("items")) if isinstance(sub, dict) else None
        props = items.get("properties") if isinstance(items, dict) else None
        id_schema = _resolve_local_ref(schema, props.get("id")) if isinstance(props, dict) else None
        if not (isinstance(id_schema, dict) and id_schema.get("type") == "string"):
            self.error(
                "group.foreach_items_need_id",
                where,
                f"items of {ref.raw!r} must be objects declaring an optional string 'id' property in "
                f"{source.output_schema}; the runtime assigns it and workers echo it on revision (§5.8)",
            )
        elif "id" in (items.get("required") or []):
            self.error(
                "group.foreach_id_required",
                where,
                f"items of {ref.raw!r} must not require 'id' in {source.output_schema}: instance ids are "
                "assigned by the runtime, and new items arrive without one (§5.8)",
            )
        # A source that can be skipped needs an explicit policy.
        if group.foreach_if_source_skipped is None and self._skippable(source):
            self.error(
                "group.foreach_source_skippable",
                w,
                f"foreach source {source.id!r} is skipped at some complexity levels; "
                "declare foreach_if_source_skipped: once | skip",
            )

    def _skippable(self, node: Node) -> bool:
        if self.recipe.complexity is None:
            return False
        levels = set(self.recipe.complexity.levels)
        chain = self.places[node.id].chain
        return any(n.applies_to is not None and not levels <= set(n.applies_to) for n in (*chain, node))

    # -- run inputs and sme ----------------------------------------------

    def _check_run_inputs(self) -> None:
        if self.recipe.run_inputs is not None:
            self._schema(self.recipe.run_inputs.schema_, "run_inputs.schema")

    def _check_sme(self) -> None:
        if self.recipe.sme is None:
            return
        for subject in ("project", "platform", "process"):
            req = getattr(self.recipe.sme, subject)
            if req is not None:
                self._check_requires(req, f"sme.{subject}")

    # -- complexity ------------------------------------------------------

    def _check_complexity(self) -> None:
        cx = self.recipe.complexity
        nodes = [n for n, _ in self._walk()]
        gate_levels = [
            (f"{self.where(n)}.gates[{i}]", g.applies_to)
            for n in nodes
            if isinstance(n, Step)
            for i, g in enumerate(n.gates)
            if g.applies_to is not None
        ]
        uses = [(self.where(n), n.applies_to) for n in nodes if n.applies_to is not None] + gate_levels

        if cx is None:
            for where, _ in uses:
                self.error("complexity.applies_to_without_levels", where, "applies_to needs a complexity: block with levels")
            return

        levels = cx.levels
        if len(set(levels)) != len(levels):
            self.error("complexity.duplicate_level", "complexity.levels", f"levels must be unique: {levels}")
        for where, applies in uses:
            unknown = [lv for lv in applies if lv not in levels]
            if unknown:
                self.error("complexity.unknown_level", f"{where}.applies_to", f"unknown level(s) {unknown}; declared: {levels}")

        triage = self.top.nodes.get(cx.triage_step)
        if not isinstance(triage, Step):
            self.error(
                "complexity.missing_triage_step",
                "complexity.triage_step",
                f"triage_step {cx.triage_step!r} must name a top-level (non-group) step",
            )
        else:
            if triage.applies_to is not None:
                self.error("complexity.triage_has_applies_to", f"{triage.id}.applies_to", "the triage step must run at every level")
            schema = self.schemas.get(triage.output_schema or "")
            level_schema = (schema or {}).get("properties", {}).get("level") if schema else None
            enum = level_schema.get("enum") if isinstance(level_schema, dict) else None
            required = (schema or {}).get("required") or []
            if enum is None or set(enum) != set(levels) or "level" not in required:
                self.error(
                    "complexity.level_enum_mismatch",
                    f"{triage.id}.output_schema",
                    f"the triage output schema must require 'level' with enum exactly {levels} (found enum {enum})",
                )

        # Reachability: a nested step cannot run at a level its enclosing group skips.
        for node, place in self._walk():
            if node.applies_to is None:
                continue
            for g in place.chain:
                if g.applies_to is None:
                    continue
                dead = [lv for lv in node.applies_to if lv not in g.applies_to]
                if dead:
                    self.error(
                        "complexity.unreachable",
                        f"{self.where(node)}.applies_to",
                        f"{self.where(node)!r} applies to {dead}, but its group {g.id!r} does not run at those levels",
                    )

        if not self.has_errors():
            signatures: dict[str, str] = {}
            for lv in levels:
                sig = json.dumps(_level_signature(self.recipe, lv), sort_keys=True)
                for other, other_sig in signatures.items():
                    if other_sig == sig:
                        self.warn(
                            "complexity.levels_identical",
                            "complexity.levels",
                            f"levels {other!r} and {lv!r} run the same steps and gates; keep levels visibly different",
                        )
                signatures[lv] = sig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_jinja = jinja2.Environment(autoescape=False)


def _dupes(checker: _Checker, names: list[str], code: str, where: str, what: str) -> None:
    seen: set[str] = set()
    for n in names:
        if n in seen:
            checker.error(code, where, f"{what} name {n!r} is used more than once")
        seen.add(n)


def _readable_loc(raw: Any, loc: tuple) -> str:
    """Render a pydantic error location using step ids where possible."""
    parts: list[str] = []
    cur = raw
    for item in loc:
        if isinstance(cur, list) and isinstance(item, int) and 0 <= item < len(cur):
            cur = cur[item]
            ident = cur.get("id") if isinstance(cur, dict) else None
            if ident is not None and parts and parts[-1] == "steps":
                parts[-1] = f"steps/{ident}"
            else:
                parts.append(f"[{item}]")
        elif isinstance(cur, dict) and item in cur:
            cur = cur[item]
            parts.append(str(item))
        elif isinstance(cur, dict) and not isinstance(item, int) and item not in ("step", "group") and item not in _GATE_TAGS:
            parts.append(str(item))  # a missing or extra key
        # else: a union tag; skip it
    text = ""
    for p in parts:
        text += p if p.startswith("[") or not text else "." + p
    return text


_GATE_TAGS = frozenset({"schema", "script", "review", "findings", "human"})


def _resolve_local_ref(root: dict, schema: Any) -> Any:
    seen = 0
    while isinstance(schema, dict) and isinstance(schema.get("$ref"), str) and schema["$ref"].startswith("#/") and seen < 20:
        target: Any = root
        for part in schema["$ref"][2:].split("/"):
            target = target.get(part) if isinstance(target, dict) else None
        schema = target
        seen += 1
    return schema


def _subschema(root: dict, path: tuple[str, ...]) -> tuple[str, str | None, Any]:
    """Walk ``path`` through a JSON schema.

    Returns (status, key, subschema): ``found``; ``unknown`` (the schema does not
    say); ``missing`` (properties are declared but not this one); ``forbidden``
    (missing and additionalProperties is false).
    """
    cur: Any = _resolve_local_ref(root, root)
    for seg in path:
        if not isinstance(cur, dict):
            return "unknown", None, None
        props = cur.get("properties")
        if isinstance(props, dict) and seg in props:
            cur = _resolve_local_ref(root, props[seg])
        elif seg.isdigit() and _is_array(cur):
            cur = _resolve_local_ref(root, cur.get("items"))
        elif isinstance(props, dict):
            return ("forbidden" if cur.get("additionalProperties") is False else "missing"), seg, None
        else:
            return "unknown", None, None
    return "found", None, cur


def _is_array(schema: Any) -> bool:
    if not isinstance(schema, dict):
        return False
    t = schema.get("type")
    return t == "array" or (isinstance(t, list) and t == ["array"])


def _included(node: Node, level: str | None, enclosing: bool = True) -> bool:
    return enclosing and (level is None or node.applies_to is None or level in node.applies_to)


def _level_signature(recipe: Recipe, level: str) -> list:
    sig: list = []

    def visit(nodes: list[Node], enclosing: bool) -> None:
        for n in nodes:
            inc = _included(n, level, enclosing)
            gates = []
            if isinstance(n, Step):
                gates = [i for i, g in enumerate(n.gates) if inc and (g.applies_to is None or level in g.applies_to)]
            sig.append((n.id, inc, gates))
            if isinstance(n, Group):
                visit(n.steps, inc)

    visit(recipe.steps, True)
    return sig


def package_sha256(root: Path) -> str:
    """SHA-256 over a recipe package: each file's POSIX relative path and content hash, sorted."""
    h = hashlib.sha256()
    files = sorted(
        (p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    for p in files:
        rel = p.relative_to(root).as_posix()
        h.update(rel.encode("utf-8") + b"\0" + hashlib.sha256(p.read_bytes()).hexdigest().encode() + b"\n")
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Plans
# ---------------------------------------------------------------------------


def build_plan(loaded: LoadedRecipe, level: str | None = None) -> Plan:
    """The structured per-level step and gate table; renderers sit on top (§15.3)."""
    recipe = loaded.recipe
    cx = recipe.complexity
    if cx is None:
        if level is not None:
            raise ValueError(f"{recipe.ref} declares no complexity levels")
        levels: list[str | None] = [None]
    else:
        if level is not None and level not in cx.levels:
            raise ValueError(f"unknown level {level!r}; declared: {cx.levels}")
        levels = [level] if level is not None else list(cx.levels)

    by_id: dict[str, Node] = {}

    def index(nodes: list[Node]) -> None:
        for n in nodes:
            by_id[n.id] = n
            if isinstance(n, Group):
                index(n.steps)

    index(recipe.steps)

    plan_levels = []
    for lv in levels:
        rows: list[PlanStep] = []

        def visit(nodes: list[Node], depth: int, prefix: str, enclosing: bool) -> None:
            for n in nodes:
                inc = _included(n, lv, enclosing)
                reason = ""
                if not inc:
                    reason = "group skipped" if not enclosing else f"applies to {', '.join(n.applies_to or [])}"
                path = f"{prefix}{n.id}"
                if isinstance(n, Group):
                    rows.append(
                        PlanStep(
                            path=path,
                            title=n.title or n.id,
                            kind="group",
                            depth=depth,
                            included=inc,
                            reason=reason,
                            group=_group_details(n, lv, by_id),
                        )
                    )
                    visit(n.steps, depth + 1, path + "/", inc)
                else:
                    rows.append(
                        PlanStep(
                            path=path,
                            title=n.title or n.id,
                            kind="step",
                            depth=depth,
                            included=inc,
                            reason=reason,
                            requires=n.requires,
                            workspace=n.workspace,
                            gates=_plan_gates(n, lv, inc, recipe),
                        )
                    )

        visit(recipe.steps, 0, "", True)
        plan_levels.append(PlanLevel(level=lv, steps=rows))

    return Plan(
        recipe=recipe.ref,
        format=recipe.format,
        capabilities_vocab=recipe.capabilities_vocab,
        recipe_sha256=loaded.sha256,
        description=recipe.description,
        levels=plan_levels,
        warnings=loaded.warnings,
    )


def _plan_gates(step: Step, level: str | None, included: bool, recipe: Recipe) -> list[PlanGate]:
    out = []
    for g in step.gates:
        inc = included and (level is None or g.applies_to is None or level in g.applies_to)
        note = ""
        if isinstance(g, HumanGate):
            note = g.prompt
        elif isinstance(g, ScriptGate):
            note = g.run
        elif isinstance(g, ReviewGate):
            bits = [f"reviewer tier {g.reviewer_requires.tier}" if g.reviewer_requires.tier else "reviewer"]
            if g.independence:
                bits.append(g.independence.level.replace("_", " "))
            if g.block_on:
                bits.append("blocks on " + "/".join(g.block_on))
            note = ", ".join(bits)
        elif isinstance(g, FindingsGate) and g.block_on:
            note = "blocks on " + "/".join(g.block_on)
        out.append(PlanGate(type=g.type, blocking=not g.advisory, included=inc, note=note))
    if step.protect is not None:
        mode = step.protect.on_violation if not isinstance(step.protect, list) else "warn"
        out.append(
            PlanGate(
                type="protected",
                blocking=True,
                included=included,
                implicit=True,
                note=f"{mode}: {', '.join(step.protect_paths())}",
            )
        )
    cx = recipe.complexity
    # §18 #8 (decided): triage auto-accepts at the lowest level; above it the owner approves.
    if cx is not None and step.id == cx.triage_step and level is not None and level != cx.levels[0]:
        out.append(
            PlanGate(
                type="human",
                blocking=True,
                included=included,
                implicit=True,
                note=f"approve triage result (levels above {cx.levels[0]})",
            )
        )
    return out


def _group_details(group: Group, level: str | None, by_id: dict[str, Node]) -> dict[str, Any]:
    d: dict[str, Any] = {"concurrency": group.concurrency}
    if group.foreach:
        d["foreach"] = group.foreach
        source_id = group.foreach.split(".")[1] if group.foreach.count(".") >= 2 else None
        if group.foreach.startswith("group.steps."):
            source_id = group.foreach.split(".")[2]
        source = by_id.get(source_id or "")
        if source is not None and not _included(source, level):
            d["source_skipped"] = group.foreach_if_source_skipped or "skip"
    if group.repeat_until:
        d["repeat_until"] = group.repeat_until
        d["repeat_from"] = group.repeat_from or group.steps[0].id
        d["max_iterations"] = group.max_iterations
    return d


def render_plan(plan: Plan) -> str:
    lines = [f"{plan.recipe}  ({plan.format}, {plan.capabilities_vocab})"]
    if plan.description:
        lines.append(plan.description)
    for lv in plan.levels:
        lines.append("")
        lines.append(f"Level: {lv.level}" if lv.level is not None else "Steps:")
        width = max(len("  " * r.depth + r.path.rsplit("/", 1)[-1]) for r in lv.steps) + 2
        for r in lv.steps:
            name = "  " * r.depth + r.path.rsplit("/", 1)[-1]
            status = "run " if r.included else "skip"
            if not r.included:
                detail = f"({r.reason})"
            elif r.kind == "group":
                detail = _render_group(r.group or {})
            else:
                detail = _render_gates(r.gates)
            lines.append(f"  {name.ljust(width)}{status}  {detail}".rstrip())
    if any(g.implicit for lv in plan.levels for r in lv.steps for g in r.gates):
        lines.append("")
        lines.append("* implicit gate, enforced by the runtime")
    return "\n".join(lines) + "\n"


def _render_gates(gates: list[PlanGate]) -> str:
    on = []
    off = []
    for g in gates:
        label = g.type
        if g.implicit:
            label += "*"
        if not g.blocking:
            label += " (advisory)"
        if g.note:
            label += f": {g.note}"
        (on if g.included else off).append(label)
    text = "gates: " + ("; ".join(on) if on else "none")
    if off:
        text += "  | not at this level: " + "; ".join(g.split(":")[0] for g in off)
    return text


def _render_group(d: dict[str, Any]) -> str:
    bits = []
    if "foreach" in d:
        fe = f"for each {d['foreach']}"
        if "source_skipped" in d:
            fe += " (source skipped: " + ("one instance from run inputs" if d["source_skipped"] == "once" else "group skipped") + ")"
        bits.append(fe)
        bits.append(f"{d['concurrency']} at a time")
    if "repeat_until" in d:
        bits.append(f"repeat from {d['repeat_from']} until {d['repeat_until']}, max {d['max_iterations']}")
    return "group: " + "; ".join(bits) if bits else "group"


# ---------------------------------------------------------------------------
# Crosswalks (§11.3)
# ---------------------------------------------------------------------------


def _capture_count(glob: str) -> int:
    return len(re.findall(r"\*\*|\*", glob))


def crosswalk_issues(raw: Any, recipe: Recipe, where: str) -> list[Issue]:
    """Validate a ``baton-crosswalk/1`` document against the recipe it maps into."""
    from .models import CROSSWALK_FORMATS, Crosswalk

    out: list[Issue] = []

    def err(code: str, loc: str, msg: str) -> None:
        out.append(Issue(code=code, where=f"{where}:{loc}" if loc else where, message=msg))

    if not isinstance(raw, dict):
        err("crosswalk.invalid", "", "a crosswalk must be a mapping")
        return out
    if raw.get("format") not in CROSSWALK_FORMATS:
        err("crosswalk.unknown_format", "format", f"format must be one of {list(CROSSWALK_FORMATS)}, got {raw.get('format')!r}")
        return out
    try:
        cw = Crosswalk.model_validate(raw)
    except ValidationError as e:
        for x in e.errors():
            err("crosswalk.invalid", ".".join(str(p) for p in x["loc"]), x["msg"])
        return out
    for i, m in enumerate(cw.maps):
        loc = f"maps[{i}]"
        ref, _, path = m.step.partition("/")
        if ref != recipe.ref:
            err("crosswalk.other_recipe", f"{loc}.step", f"{m.step!r} names {ref}, not {recipe.ref}")
            continue
        parts = path.split("/")
        nodes: list[Any] = recipe.steps
        node: Any = None
        group: Any = None
        for k, part in enumerate(parts):
            node = next((n for n in nodes if n.id == part), None)
            if node is None:
                break
            if k < len(parts) - 1:
                if not isinstance(node, Group):
                    node = None
                    break
                group, nodes = node, node.steps
        if node is None or isinstance(node, Group):
            err("crosswalk.unknown_step", f"{loc}.step", f"{recipe.ref} has no step {path!r}")
            continue
        targets = [t for t in (m.artifact is not None, m.output, m.gate is not None) if t]
        if len(targets) != 1:
            err("crosswalk.target", loc, "give exactly one of artifact, output: true, or gate")
        if m.artifact is not None and m.artifact not in {a.name for a in node.artifacts}:
            err("crosswalk.unknown_artifact", f"{loc}.artifact", f"step {path!r} declares no artifact {m.artifact!r}")
        if m.gate is not None and m.gate >= len(node.gates):
            err("crosswalk.unknown_gate", f"{loc}.gate", f"step {path!r} has {len(node.gates)} gate(s); no gate {m.gate}")
        n = _capture_count(m.match)
        for tmpl, key in ((m.work_item, "work_item"), (m.item, "item")):
            for ref_n in re.findall(r"\{(\d+)\}", tmpl or ""):
                if not 1 <= int(ref_n) <= n:
                    err("crosswalk.bad_capture", f"{loc}.{key}", f"{{{ref_n}}} but {m.match!r} has {n} capture(s)")
        if m.item is not None and (group is None or not group.foreach):
            err("crosswalk.item_outside_foreach", f"{loc}.item", f"step {path!r} is not inside a foreach group")
        if group is not None and group.foreach and m.item is None:
            err("crosswalk.item_missing", f"{loc}.item", f"step {path!r} is inside the foreach group {group.id!r}; name the item")
    return out
