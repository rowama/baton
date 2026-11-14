"""Generated manual topics (§13.10; decisions 0127, 0133): one provider page per directory entry, and the parts table of each recipe topic.

``python tools/build_manual.py`` writes them; ``tests/test_manual_gen.py`` regenerates and compares, so a new
directory entry (or a changed fact about one) cannot leave the manual stale. The hand-written part of a
provider's page is only its quirks, in ``manual/provider-notes.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import json
import re
import typing

import yaml
from pydantic import BaseModel

from . import data, manual, recipe, vocab
from . import known_workers as kw


def slug(name: str) -> str:
    return name.replace("_", "-")


def _notes(base: Path) -> dict[str, str]:
    p = base / "provider-notes.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def _providers() -> dict[str, Any]:
    known = kw.load(vocab.load(vocab.DEFAULT))
    return {n: p for n, p in sorted(known.providers.items()) if p.kind != "harness"}


def _local(p: Any) -> bool:
    return bool(p.base_url) and any(h in p.base_url for h in ("localhost", "127.0.0.1")) or p.kind == "local"


def render(name: str, p: Any, notes: str | None, order: int) -> str:
    title = p.display_name or name
    local = _local(p)
    generic = p.kind == "openai_compatible" and not p.base_url
    if local:
        steps = [f"Start {title} on this computer, so it is listening at `{p.base_url}`." if p.base_url else f"Start {title} on this computer.",
                 f"In **Accounts**, find the **{title}** card and choose **Connect**. Leave the key box blank unless you set one up."]
        summary = f"Use {title}, running on this computer, so Baton can use its models."
    elif generic:
        steps = ["Find the address of the service (it ends in `/v1`) and, if it needs one, a key.",
                 f"In **Accounts**, find the **{title}** card, enter the address and the key, and choose **Connect**."]
        summary = "Use any service that speaks the OpenAI interface."
    else:
        get = f"Get a key from [{title}]({p.signup_url}). It opens {title}'s own page for creating one." if p.signup_url else f"Create a key in your {title} account."
        steps = [get, f"In **Accounts**, find the **{title}** card, paste the key into its box and choose **Connect**."]
        summary = f"Get a key for {title} and connect it so its models can do work for you."
    out = ["---", f"id: providers.{slug(name)}", "title: Connect any OpenAI-compatible service" if generic else (f"title: Use {title}" if local else f"title: Connect {title}"), "audience: owner", f"summary: {summary}",
           f"order: {order}", "generated: true", "related: [user.connect-an-account, admin.secrets]", "---", "", "## Here, now {#here-now}", ""]
    out += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    out += ["", "Baton checks the connection with a quick read of the model list, which never asks a model anything and costs nothing. Then the models appear in **Models**.", "",
            "If it does not work, see [what a refusal means](user.connect-an-account#key-refused).", "", f"## About {title} {{#about}}", ""]
    if p.kind == "direct_api":
        out.append(f"{title} sells access to its own models directly. You pay {title}, on your own account with them.")
    elif p.kind == "intermediary":
        out.append(f"{title} hosts models made by several vendors, so one account reaches several makers' models, which is often the quickest way to get more than one working. You pay {title}.")
    elif local:
        out.append(f"{title} runs models on your own computer, so there is no account to pay and no key by default. How fast and how good the models are depends on your hardware.")
    elif generic:
        out.append("Many services copy the OpenAI interface, so Baton can use any of them with just an address and, if the service wants one, a key.")
    else:
        out.append(f"{title} offers models over the OpenAI interface, so Baton needs only a key from {title}. You pay {title}.")
    if p.base_url and not generic:
        out += ["", f"Baton talks to it at `{p.base_url}`."]
    if notes:
        out += ["", f"## Good to know {{#good-to-know}}", "", notes.strip()]
    cmd = f"baton workers connect {name}" + (" --no-key" if local else "")
    out += ["", "## From the command line {#command-line}", "", "The same steps without the page. A key is asked for at a hidden prompt, never typed as an argument:", "",
            "```baton", cmd] + ([f"baton workers connect {name} --base-url https://example.com/v1"] if generic else []) + ["```", ""]
    return "\n".join(out)


def render_all(base: Path | None = None) -> dict[str, str]:
    """Relative path under the manual -> generated text."""
    base = base or manual.root()
    notes = _notes(base)
    out = {f"providers/{slug(n)}.md": render(n, p, notes.get(n), 10 + i) for i, (n, p) in enumerate(_providers().items())}
    out.update(reference_pages(base))
    for rid, root in shipped_recipes().items():
        src = base / "recipe-sources" / f"{rid}.md"
        if src.is_file():
            out[f"recipes/{rid}.md"] = render_recipe(src.read_text(encoding="utf-8"), root)
    return out


# ---- recipe topics: hand-written prose, generated parts table ---------------------------------

def shipped_recipes() -> dict[str, Path]:
    """Every recipe that ships with Baton: the examples and the built-in ones."""
    found: dict[str, Path] = {}
    for top in (data.path("examples") / "recipes", data.path("builtin")):
        for d in sorted(top.glob("*")):
            if (d / "recipe.yaml").is_file():
                found[d.name] = d
    return found


def _human(text: str) -> str:
    return text.replace("|", "/")


def parts_table(root: Path, labels: dict[str, str]) -> str:
    """What the recipe does, step by step, and where the owner is asked: read from the recipe itself (§5.5)."""
    plan = recipe.build_plan(recipe.load_recipe(root))
    levels = [lv.level for lv in plan.levels]
    order: list[str] = []
    for lv in plan.levels:
        for st in lv.steps:
            if st.path not in order:
                order.append(st.path)
    rows = []
    for path in order:
        per = {lv.level: next((st for st in lv.steps if st.path == path), None) for lv in plan.levels}
        here = {lv: st for lv, st in per.items() if st is not None and st.included}
        any_step = next(st for st in per.values() if st is not None)
        title = labels.get(path) or (any_step.title[:1].upper() + any_step.title[1:])
        when = "always" if len(here) == len(levels) else "at " + ", ".join(lv for lv in levels if lv in here)
        if levels == [None]:
            when = "always"
        asks: dict[str, list[str]] = {}
        for lv, st in here.items():
            for g in st.gates:
                if g.type != "human" or g.blocking is False:
                    continue
                note = "Is the size right?" if g.implicit else g.note
                asks.setdefault(note, []).append(lv)
        asked = "; ".join(q if (levels == [None] or len(v) == len(here)) else f"{q} (at {', '.join(v)})" for q, v in asks.items())
        indent = "↳ " if any_step.depth else ""
        rows.append(f"| {indent}{_human(title)} | {when} | {_human(asked) if asked else 'nothing'} |")
    head = ["| Part | When | You are asked |", "|---|---|---|"]
    note = "" if levels == [None] else f"\n\nThe size of the work is {', '.join(f'**{lv}**' for lv in levels)}. The first part works out which one fits, and you confirm it above the smallest."
    return "\n".join(head + rows) + note + documents_table(recipe.load_recipe(root).recipe)


def documents_table(r: Any) -> str:
    """The project documents a recipe can build on, from its ``project_inputs`` (§5.1): empty when it declares none."""
    if not r.project_inputs:
        return ""
    rows = ["| Document | Needed | How many |", "|---|---|---|"]
    for p in r.project_inputs:
        rows.append(f"| {_human(p.description)} | {'yes' if p.required else 'if you have one'} | {'one or more' if p.many else 'one'} |")
    return ("\n\nIt can build on documents your project already has. Before the work that needs one starts, "
            "you are shown the document proposed and asked to confirm it.\n\n" + "\n".join(rows))


def render_recipe(src: str, root: Path) -> str:
    meta, body = manual._split(src)
    labels = dict(meta.pop("step_labels", None) or {})
    meta["generated"] = True
    table = parts_table(root, labels)
    if "%parts%" not in body:
        raise manual.ManualError("a recipe source needs a %parts% line")
    front = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=1000).rstrip("\n")
    return f"---\n{front}\n---\n{body.replace('%parts%', table)}"


def write(base: Path | None = None) -> list[str]:
    base = base or manual.root()
    want = render_all(base)
    (base / "providers").mkdir(exist_ok=True)
    for rel, text in want.items():
        (base / rel).write_text(text, encoding="utf-8")
    for sub in ("recipes", "reference"):
        (base / sub).mkdir(exist_ok=True)
    for sub in ("providers", "recipes", "reference"):
        for old in (base / sub).glob("*.md"):
            if f"{sub}/{old.name}" not in want:
                old.unlink()
    return sorted(want)


def stale(base: Path | None = None) -> list[str]:
    base = base or manual.root()
    want = render_all(base)
    out = [f"{rel}: missing or out of date" for rel, text in want.items() if not (base / rel).is_file() or (base / rel).read_text(encoding="utf-8") != text]
    out += [f"providers/{p.name}: no such provider in the directory" for p in sorted((base / "providers").glob("*.md")) if f"providers/{p.name}" not in want]
    out += [f"reference/{p.name}: not a generated reference page" for p in sorted((base / "reference").glob("*.md")) if f"reference/{p.name}" not in want]
    out += [f"recipes/{p.name}: no recipe source" for p in sorted((base / "recipes").glob("*.md")) if f"recipes/{p.name}" not in want]
    out += [f"shipped recipe {rid} has no manual/recipe-sources/{rid}.md" for rid in shipped_recipes() if not (base / "recipe-sources" / f"{rid}.md").is_file()]
    return out


# ---- the reference: commands, project settings, environment, diagnostics (generated; decision 0133) ----------

def _notes_file(base: Path) -> dict[str, Any]:
    p = base / "reference-notes.yaml"
    return (yaml.safe_load(p.read_text(encoding="utf-8")) or {}) if p.is_file() else {}


def _clean(text: str) -> str:
    """Design references mean nothing to an administrator: take them out."""
    text = re.sub(r"\s*\((?:§|decision )[^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"§\d+(?:\.\d+)?", "", text).strip()
    # `<name>` outside code would read as HTML: put it in code. A pipe in a table cell is escaped.
    parts = text.split("`")
    parts[::2] = [re.sub(r"<([A-Za-z][^<>`]*)>", r"`<\1>`", seg) for seg in parts[::2]]
    return "`".join(parts).replace("|", "\\|")


def _front(tid: str, title: str, summary: str, order: int) -> list[str]:
    return ["---", f"id: reference.{tid}", f"title: {title}", "audience: admin", f"summary: {summary}", f"order: {order}", "generated: true", "---", ""]


def _anchor(words: list[str]) -> str:
    return "-".join(re.sub(r"[^a-z0-9]+", "-", w.lower()).strip("-") for w in words)


def _params(cmd: Any) -> list[str]:
    rows = []
    for p in cmd.params:
        opts = getattr(p, "opts", None) or []
        if opts and "--help" in opts:
            continue
        label = ", ".join(opts) if opts else p.name
        if opts and not getattr(p, "is_flag", False):
            label += f" <{getattr(p.type, 'name', 'value')}>"
        if not opts and p.required:
            label += " (required)"
        rows.append(f"| `{label}` | {_clean(getattr(p, 'help', None) or '')} |")
    return rows


def _command_section(path: list[str], cmd: Any, level: int, topic_of: Any) -> list[str]:
    name = "baton " + " ".join(path)
    out = [f"{'#' * level} {name} {{#{_anchor(['baton'] + path)}}}", ""]
    out += [_clean(cmd.help or ""), ""] if cmd.help else []
    ref = topic_of(path[0])
    if ref:
        out += [f"Explained in the manual: [{ref[1]}]({ref[0]}#here-now).", ""]
    rows = _params(cmd)
    if rows:
        out += ["| Argument or option | What it does |", "|---|---|"] + rows + [""]
    return out


def commands_page(base: Path) -> str:
    from . import manual_cli

    ctx = manual.context(base)
    m = manual.Manual(base)

    def topic_of(name: str) -> tuple[str, str] | None:
        ref = (ctx.get("commands") or {}).get(name)
        return (ref, m.resolve(ref)[0].title) if ref else None

    root = manual_cli._group()
    out = _front("commands", "Command reference", "Every baton command and option.", 10)
    out += ["## Here, now {#here-now}", "", "Every command takes `--json` for machine-readable output. Global options: `--project <path>` (or `BATON_PROJECT`), `--director <id>` (or `BATON_DIRECTOR`). Exit codes are in [setting up an assistant](admin.directors#exit-codes).", ""]
    for name in sorted(root.commands):
        cmd = root.commands[name]
        out += _command_section([name], cmd, 2, topic_of)
        if hasattr(cmd, "commands"):
            for sub in sorted(cmd.commands):
                out += _command_section([name, sub], cmd.commands[sub], 3, topic_of)
    return "\n".join(out).rstrip("\n") + "\n"


def _type_name(ann: Any) -> str:
    origin = typing.get_origin(ann)
    if origin is typing.Literal:
        return ", ".join(str(a) for a in typing.get_args(ann)[:-1]) + " or " + str(typing.get_args(ann)[-1])
    if origin in (typing.Union, getattr(__import__("types"), "UnionType", None)):
        args = [a for a in typing.get_args(ann) if a is not type(None)]
        return _type_name(args[0]) + " (optional)" if len(args) == 1 else " or ".join(_type_name(a) for a in args)
    if origin is dict:
        return "mapping"
    if origin is list:
        return "list"
    return {bool: "yes/no", int: "whole number", float: "number", str: "text"}.get(ann, getattr(ann, "__name__", str(ann)))


def project_settings() -> list[tuple[str, Any, Any]]:
    """Every ``project.yaml`` key, flattened from the model: (key, type, default)."""
    from .models import ProjectConfig

    out: list[tuple[str, Any, Any]] = []

    def walk(model: type[BaseModel], prefix: str) -> None:
        for name, f in model.model_fields.items():
            ann = f.annotation
            if isinstance(ann, type) and issubclass(ann, BaseModel):
                walk(ann, prefix + name + ".")
            else:
                out.append((prefix + name, ann, f.get_default(call_default_factory=True)))

    walk(ProjectConfig, "")
    return out


def _default(v: Any) -> str:
    if v in ("", None, {}, []):
        return "none" if v in (None, {}, []) else "empty"
    return "`" + (json.dumps(v) if not isinstance(v, str) else v).replace("|", "\\|") + "`"


def settings_page(base: Path) -> str:
    notes = _notes_file(base).get("project_settings") or {}
    out = _front("project-settings", "Project settings reference", "Every setting in .baton/project.yaml, its type and default.", 20)
    out += ["## Here, now {#here-now}", "", "These are the keys of `.baton/project.yaml`, which is committed and never holds secrets. For the ones most projects change first, see [project settings](admin.project-settings#here-now).", "",
            "| Key | Type | Default | What it does |", "|---|---|---|---|"]
    for key, ann, default in project_settings():
        out.append(f"| `{key}` | {_type_name(ann)} | {_default(default)} | {_clean(notes.get(key, ''))} |")
    return "\n".join(out) + "\n"


def environment_page(base: Path) -> str:
    env = _notes_file(base).get("environment") or {}
    out = _front("environment", "Environment variables", "The variables Baton reads, and the ones it sets for hooks and helpers.", 30)
    out += ["## Here, now {#here-now}", "", "Variables **you** may set, then the ones **Baton** sets for the programs it starts.", ""]
    for who, head, anchor in (("you", "Variables you set", "you-set"), ("baton", "Variables Baton sets", "baton-sets")):
        out += [f"## {head} {{#{anchor}}}", "", "| Variable | Meaning |", "|---|---|"]
        out += [f"| `{k}` | {_clean(v['text'])} |" for k, v in sorted(env.items()) if v["who"] == who]
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n"


def diagnostics_page(base: Path) -> str:
    codes = _notes_file(base).get("diagnostics") or {}
    out = _front("diagnostics", "Diagnostic codes", "Every condition Baton records in ~/.baton/diag, and what it means.", 40)
    out += ["## Here, now {#here-now}", "", "Read them with `baton diag`. Each is something Baton worked around instead of failing; most are harmless once, and worth a look when they recur.", "",
            "| Code | What happened |", "|---|---|"]
    out += [f"| `{c}` | {_clean(t)} |" for c, t in sorted(codes.items())]
    return "\n".join(out) + "\n"


def reference_pages(base: Path) -> dict[str, str]:
    return {"reference/commands.md": commands_page(base), "reference/project-settings.md": settings_page(base),
            "reference/environment.md": environment_page(base), "reference/diagnostics.md": diagnostics_page(base)}


# ---- coverage: the code's own facts against the hand-written words -------------------------------

def _source_text() -> str:
    pkg = Path(manual.__file__).parent
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(pkg.glob("*.py")) if p.name not in ("manual_gen.py",))


def source_env_vars() -> set[str]:
    names = set(re.findall(r"[\"'](BATON_[A-Z0-9_]+)[\"']", _source_text()))
    return {n + "<NAME>" if n.endswith("_") else n for n in names}


def source_diag_codes() -> set[str]:
    return set(re.findall(r"diag\.note\(\s*\"([a-z_.]+)\"", _source_text()))


def coverage(base: Path | None = None) -> list[str]:
    """What the code has that the reference does not describe, and what it describes that the code no longer has."""
    from . import manual_cli

    base = base or manual.root()
    notes = _notes_file(base)
    out = []
    keys = {k for k, _a, _d in project_settings()}
    have = set(notes.get("project_settings") or {})
    out += [f"project setting {k} has no description in reference-notes.yaml" for k in sorted(keys - have)]
    out += [f"reference-notes.yaml describes project setting {k}, which does not exist" for k in sorted(have - keys)]
    env, found = set(notes.get("environment") or {}), source_env_vars()
    out += [f"environment variable {v} is used in the code but not described in reference-notes.yaml" for v in sorted(found - env)]
    out += [f"reference-notes.yaml describes {v}, which the code no longer uses" for v in sorted(env - found)]
    codes, seen = set(notes.get("diagnostics") or {}), source_diag_codes()
    out += [f"diagnostic code {c} is raised in the code but not described in reference-notes.yaml" for c in sorted(seen - codes)]
    out += [f"reference-notes.yaml describes diagnostic code {c}, which the code no longer raises" for c in sorted(codes - seen)]
    root = manual_cli._group()

    def walk(cmd: Any, path: list[str]) -> None:
        if path and not (cmd.help or "").strip():
            out.append(f"command `baton {' '.join(path)}` has no help text")
        for p in getattr(cmd, "params", []):
            opts = getattr(p, "opts", None) or []
            if opts and "--help" not in opts and not (getattr(p, "help", None) or "").strip():
                out.append(f"option {opts[0]} of `baton {' '.join(path)}` has no help text")
        for name, sub in getattr(cmd, "commands", {}).items():
            walk(sub, path + [name])

    walk(root, [])
    return out
