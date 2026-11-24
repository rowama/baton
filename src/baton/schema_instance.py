"""Find one instance of a JSON Schema, or report that none was found (§5.3; Decision 0190).

The loader warns (``schema.no_instance``) about a step's output schema that no output can satisfy: such a step
can't be passed by an honest worker. The search builds a few candidates at each node from the keywords shipped
recipes use, and keeps a candidate only when the JSON Schema validator (with the format checker intake uses)
accepts it, so an instance returned is always valid. Finding none is not a proof: a keyword the search does not
build from (``not``, ``uniqueItems`` across complex items, an unusual ``pattern``) can hide an instance. That is why
the loader warns and never refuses.

Construction, per node: a node is flattened into a few *alternatives*, each a merge of the node's own keywords
with one choice from each ``allOf`` member, ``anyOf``/``oneOf`` branch, and ``if``+``then`` or ``else``. Each
alternative yields candidates (``const`` and ``enum`` values; an object of its required properties; an array of
``minItems`` items; a string from a fixed list or padded to ``minLength``; a number at its bound), and the
validator judges each against the whole node. The search is bounded per node and in all.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterator

from jsonschema import Draft202012Validator

#: Candidates kept per node, alternatives per node, and nodes visited in all.
PER_NODE = 4
MAX_ALTERNATIVES = 32
MAX_NODES = 20000
MAX_DEPTH = 24

#: Strings tried for a ``pattern`` or ``format``, in order; the first the validator accepts is kept.
STRING_CANDIDATES = (
    "x", "a", "abc", "a1", "a-b", "a_b", "abcdef0", "abcdef0123456789abcdef0123456789abcdef01",
    "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789", "a@1", "ir_0123456789abcdef0123",
    "2026-01-01", "2026-01-01T00:00:00Z", "00:00:00Z", "https://example.org/", "a@example.org",
    "P1D", "1", "0", "A", "Ab", "x.md", "a/b",
)
_MISSING = object()
_cache: dict[str, Any] = {}


class _Budget(Exception):
    pass


def find_instance(schema: Any) -> tuple[bool, Any]:
    """``(True, instance)`` for an instance the validator accepts, or ``(False, None)`` when none was found."""
    key = hashlib.sha256(json.dumps(schema, sort_keys=True, default=str).encode()).hexdigest()
    if key not in _cache:
        _cache[key] = _Search(schema).run()
    found = _cache[key]
    return (found is not _MISSING, None if found is _MISSING else found)


class _Search:
    def __init__(self, root: Any) -> None:
        self.root = root
        self.validator = Draft202012Validator(root, format_checker=Draft202012Validator.FORMAT_CHECKER)
        self.nodes = 0

    def run(self) -> Any:
        try:
            for c in self.gen(self.root, 0):
                return c
        except _Budget:  # expected: the search bound was reached; no instance found is the warning itself
            pass
        return _MISSING

    def valid(self, schema: Any, value: Any) -> bool:
        return self.validator.evolve(schema=schema).is_valid(value) if schema is not self.root else self.validator.is_valid(value)

    def resolve(self, ref: str) -> Any:
        if not ref.startswith("#"):
            return True  # outside the schema: not followed; the validator judges
        node: Any = self.root
        for part in [p for p in ref[1:].split("/") if p]:
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(node, list) and part.isdigit():
                node = node[int(part)]
            elif isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return True
        return node

    # -- generation --------------------------------------------------------

    def gen(self, schema: Any, depth: int) -> list[Any]:
        """Up to PER_NODE values valid against ``schema`` (in the root's context)."""
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise _Budget
        if schema is False or depth > MAX_DEPTH:
            return []
        if schema is True or schema == {}:
            return ["x"]
        if not isinstance(schema, dict):
            return []
        out: list[Any] = []
        seen: set[str] = set()
        for alt in self.alternatives(schema, depth):
            for c in self.build(alt, depth):
                k = json.dumps(c, sort_keys=True, default=str)
                if k in seen:
                    continue
                seen.add(k)
                if self.valid(schema, c):
                    out.append(c)
                    if len(out) >= PER_NODE:
                        return out
        return out

    def alternatives(self, schema: dict[str, Any], depth: int) -> list[list[dict[str, Any]]]:
        """Each alternative is a list of schema dicts whose constraints all apply (a flattened ``allOf``)."""
        alts: list[list[dict[str, Any]]] = [[schema]]

        def times(options: list[list[dict[str, Any]]]) -> None:
            nonlocal alts
            alts = [a + o for a in alts for o in options if not _clash(a + o)][:MAX_ALTERNATIVES]

        if "$ref" in schema and depth <= MAX_DEPTH:
            target = self.resolve(schema["$ref"])
            if isinstance(target, dict):
                times(self.alternatives(target, depth + 1))
        for sub in schema.get("allOf") or []:
            if isinstance(sub, dict):
                times(self.alternatives(sub, depth + 1))
            elif sub is False:
                return []
        for key in ("anyOf", "oneOf"):
            branches = [b for b in schema.get(key) or [] if isinstance(b, dict) or b is True]
            if branches:
                options = [o for b in branches for o in (self.alternatives(b, depth + 1) if isinstance(b, dict) else [[]])]
                times(options)
        if isinstance(schema.get("if"), dict):
            then = schema.get("then") if isinstance(schema.get("then"), dict) else {}
            other = schema.get("else") if isinstance(schema.get("else"), dict) else {}
            times([o + t for o in self.alternatives(schema["if"], depth + 1) for t in self.alternatives(then, depth + 1)]
                  + self.alternatives(other, depth + 1))
        return alts

    def build(self, alt: list[dict[str, Any]], depth: int) -> Iterator[Any]:
        c = _merge(alt)
        if c["values"] is not None:
            yield from c["values"]
            return
        types = c["types"] if c["types"] is not None else _implied_types(c)
        for t in types:
            if t == "object":
                yield from self.build_object(c, depth)
            elif t == "array":
                yield from self.build_array(c, depth)
            elif t == "string":
                yield from _strings(c)
            elif t in ("integer", "number"):
                yield from _numbers(c, t)
            elif t == "boolean":
                yield from (True, False)
            elif t == "null":
                yield None

    def value_for(self, schemas: list[Any], depth: int) -> list[Any]:
        if not schemas:
            return ["x"]
        return self.gen(schemas[0] if len(schemas) == 1 else {"allOf": schemas}, depth + 1)

    def build_object(self, c: dict[str, Any], depth: int) -> Iterator[Any]:
        names = sorted(c["required"], key=lambda n: (n not in c["properties"], n))
        options: dict[str, list[Any]] = {}
        for n in names:
            schemas = c["properties"].get(n)
            if schemas is None:
                if any(a is False for a in c["additional"]):
                    return
                schemas = [a for a in c["additional"] if isinstance(a, dict)]
            vals = self.value_for(schemas, depth)
            if not vals:
                return
            options[n] = vals
        base = {n: v[0] for n, v in options.items()}
        yield dict(base)
        for n, vals in options.items():  # vary one property at a time
            for v in vals[1:]:
                yield {**base, n: v}

    def build_array(self, c: dict[str, Any], depth: int) -> Iterator[Any]:
        n = max(c["min_items"], 1 if c["contains"] else 0)
        if c["max_items"] is not None and n > c["max_items"]:
            return
        items = self.value_for(c["items"], depth) if n else []
        if n and not items:
            return
        if c["contains"]:
            first = self.value_for(c["contains"] + c["items"], depth)
            if not first:
                return
            yield [first[0]] + [items[0]] * (n - 1)
            return
        if n == 0:
            yield []
            if c["items"]:
                one = self.value_for(c["items"], depth)
                if one:
                    yield [one[0]]
            return
        yield [items[0]] * n
        if len(items) >= n:
            yield items[:n]  # distinct items, for uniqueItems


def _merge(alt: list[dict[str, Any]]) -> dict[str, Any]:
    """The constraints of an alternative's schemas, combined."""
    c: dict[str, Any] = {"types": None, "values": None, "properties": {}, "required": set(), "additional": [],
                         "items": [], "contains": [], "min_items": 0, "max_items": None, "min_length": 0,
                         "max_length": None, "patterns": [], "minimum": None, "maximum": None, "keys": set()}
    for s in alt:
        c["keys"] |= set(s)
        if "type" in s:
            t = set(s["type"] if isinstance(s["type"], list) else [s["type"]])
            if "number" in t:
                t.add("integer")
            c["types"] = t if c["types"] is None else (c["types"] & t) | ({"integer"} if "number" in c["types"] & t else set())
        vals = [s["const"]] if "const" in s else (list(s["enum"]) if "enum" in s else None)
        if vals is not None:
            c["values"] = vals if c["values"] is None else [v for v in c["values"] if any(v == w and type(v) is type(w) for w in vals)]
        for n, sub in (s.get("properties") or {}).items():
            c["properties"].setdefault(n, []).append(sub)
        c["required"] |= set(s.get("required") or [])
        if "additionalProperties" in s:
            c["additional"].append(s["additionalProperties"])
        if "items" in s:
            c["items"].append(s["items"])
        if "contains" in s:
            c["contains"].append(s["contains"])
        c["min_items"] = max(c["min_items"], int(s.get("minItems") or 0))
        if "maxItems" in s:
            c["max_items"] = s["maxItems"] if c["max_items"] is None else min(c["max_items"], s["maxItems"])
        c["min_length"] = max(c["min_length"], int(s.get("minLength") or 0))
        if "maxLength" in s:
            c["max_length"] = s["maxLength"] if c["max_length"] is None else min(c["max_length"], s["maxLength"])
        if "pattern" in s:
            c["patterns"].append(s["pattern"])
        if "format" in s:
            c["keys"].add("format:" + str(s["format"]))
        for key, pick in (("minimum", max), ("exclusiveMinimum", max)):
            if key in s:
                v = s[key] + (1 if key.startswith("exclusive") else 0)
                c["minimum"] = v if c["minimum"] is None else pick(c["minimum"], v)
        for key in ("maximum", "exclusiveMaximum"):
            if key in s:
                v = s[key] - (1 if key.startswith("exclusive") else 0)
                c["maximum"] = v if c["maximum"] is None else min(c["maximum"], v)
    if c["types"] is not None:
        c["types"] = [t for t in ("object", "array", "string", "integer", "number", "boolean", "null") if t in c["types"]]
        if "integer" in c["types"] and "number" in c["types"]:
            c["types"].remove("number")
    return c


def _clash(schemas: list[Any], depth: int = 0) -> bool:
    """Whether the schemas plainly contradict: no ``const``/``enum`` value or type in common, here or in a property."""
    dicts = [s for s in schemas if isinstance(s, dict)]
    if any(s is False for s in schemas):
        return True
    c = _merge(dicts)
    if c["values"] == [] or c["types"] == []:
        return True
    if depth >= 3:
        return False
    return any(_clash(subs, depth + 1) for subs in c["properties"].values() if len(subs) > 1)


def _implied_types(c: dict[str, Any]) -> list[str]:
    k = c["keys"]
    if k & {"properties", "required", "additionalProperties"}:
        return ["object"]
    if k & {"items", "minItems", "maxItems", "contains", "prefixItems", "uniqueItems"}:
        return ["array"]
    if k & {"minLength", "maxLength", "pattern"} or any(x.startswith("format:") for x in k):
        return ["string"]
    if k & {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"}:
        return ["integer"]
    return ["string", "object", "integer", "array", "boolean", "null"]


def _strings(c: dict[str, Any]) -> Iterator[str]:
    lo, hi = c["min_length"], c["max_length"]
    padded = "x" * max(lo, 1)
    for s in (*STRING_CANDIDATES, padded):
        if len(s) < lo:
            s = s + "x" * (lo - len(s))
        if hi is not None and len(s) > hi:
            continue
        if all(re.search(p, s) for p in c["patterns"]):
            yield s


def _numbers(c: dict[str, Any], t: str) -> Iterator[Any]:
    lo, hi = c["minimum"], c["maximum"]
    for v in ([lo] if lo is not None else []) + ([hi] if hi is not None else []) + [0, 1]:
        if t == "integer":
            v = int(v) if float(v).is_integer() else int(v) + 1
        if (lo is None or v >= lo) and (hi is None or v <= hi):
            yield v
