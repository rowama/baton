"""Generated manual topics (§13.10; decisions 0127, 0133): one provider page per directory entry, and the parts table of each recipe topic.

``python tools/build_manual.py`` writes them; ``tests/test_manual_gen.py`` regenerates and compares, so a new
directory entry (or a changed fact about one) cannot leave the manual stale. The hand-written part of a
provider's page is only its quirks, in ``manual/provider-notes.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

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
    return "\n".join(head + rows) + note


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
    (base / "recipes").mkdir(exist_ok=True)
    for sub in ("providers", "recipes"):
        for old in (base / sub).glob("*.md"):
            if f"{sub}/{old.name}" not in want:
                old.unlink()
    return sorted(want)


def stale(base: Path | None = None) -> list[str]:
    base = base or manual.root()
    want = render_all(base)
    out = [f"{rel}: missing or out of date" for rel, text in want.items() if not (base / rel).is_file() or (base / rel).read_text(encoding="utf-8") != text]
    out += [f"providers/{p.name}: no such provider in the directory" for p in sorted((base / "providers").glob("*.md")) if f"providers/{p.name}" not in want]
    out += [f"recipes/{p.name}: no recipe source" for p in sorted((base / "recipes").glob("*.md")) if f"recipes/{p.name}" not in want]
    out += [f"shipped recipe {rid} has no manual/recipe-sources/{rid}.md" for rid in shipped_recipes() if not (base / "recipe-sources" / f"{rid}.md").is_file()]
    return out
