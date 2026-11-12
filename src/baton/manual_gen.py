"""Generated manual topics (§13.10; decision 0133): one provider page per directory entry.

``python tools/build_manual.py`` writes them; ``tests/test_manual_gen.py`` regenerates and compares, so a new
directory entry (or a changed fact about one) cannot leave the manual stale. The hand-written part of a
provider's page is only its quirks, in ``manual/provider-notes.yaml``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from . import known_workers as kw
from . import manual, vocab


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
    return {f"providers/{slug(n)}.md": render(n, p, notes.get(n), 10 + i) for i, (n, p) in enumerate(_providers().items())}


def write(base: Path | None = None) -> list[str]:
    base = base or manual.root()
    want = render_all(base)
    (base / "providers").mkdir(exist_ok=True)
    for rel, text in want.items():
        (base / rel).write_text(text, encoding="utf-8")
    for old in (base / "providers").glob("*.md"):
        if f"providers/{old.name}" not in want:
            old.unlink()
    return sorted(want)


def stale(base: Path | None = None) -> list[str]:
    base = base or manual.root()
    want = render_all(base)
    out = [f"{rel}: missing or out of date" for rel, text in want.items() if not (base / rel).is_file() or (base / rel).read_text(encoding="utf-8") != text]
    out += [f"providers/{p.name}: no such provider in the directory" for p in sorted((base / "providers").glob("*.md")) if f"providers/{p.name}" not in want]
    return out
