"""The manual cannot drift: format, anchors, links, examples, context map, `baton help` (§13.10; decisions 0126, 0128)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from baton import cli, manual

ROOT = Path(__file__).resolve().parents[1]
runner = CliRunner()


def test_the_shipped_manual_is_valid():
    assert manual.validate() == []


def test_the_manual_ships_in_the_wheel():
    assert '"manual" = "baton/_data/manual"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


@pytest.fixture
def mini(tmp_path):
    """A copy of the manual to break one thing at a time."""
    dest = tmp_path / "manual"
    shutil.copytree(ROOT / "manual", dest)
    return dest


def problems(base: Path) -> list[str]:
    return manual.validate(manual.Manual(base))


def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.mark.parametrize("old,new,fragment", [
    ("{#what-connecting-does}", "", "needs an explicit lowercase anchor"),
    ("{#key-refused}", "{#what-connecting-does}", "used twice"),
    ("## Key refused", "# Key refused", "title is in the front matter"),
    ("(user.connect-an-account#key-refused)", "(user.connect-an-account#nope)", "does not resolve"),
    ("(admin.secrets#where-keys-are-kept)", "(http://example.com)", "use https://"),
    ("copied whole", "copied <b>whole</b>", "raw HTML"),
    ("- **Replace key**", "> a quote\n\n- **Replace key**", "a quote is a note"),
    ("baton workers connect openrouter\n", "baton workers connectt openrouter\n", "is not a command"),
    ("--key-stdin\n", "--key-stdn\n", "is not an option"),
    ("Baton checks the key", "Baton checks the packet", "internal term 'packet'"),
    ("| Model |", "| Model | extra |", "different numbers of columns"),
])
def test_each_break_in_the_format_is_reported(mini, old, new, fragment):
    target = mini / "user" / "connect-an-account.md"
    if old.startswith("| Model"):
        target = mini / "user" / "choose-models.md"
    edit(target, old, new)
    found = problems(mini)
    assert any(fragment in p for p in found), found


def test_a_topic_must_open_with_the_in_context_answer(mini):
    edit(mini / "admin" / "secrets.md", "## Here, now {#here-now}", "## Overview {#overview}")
    assert any("opens with '## Here, now" in p for p in problems(mini))


def test_a_published_anchor_that_stops_resolving_is_reported_and_an_alias_fixes_it(mini):
    edit(mini / "user" / "connect-an-account.md", "## Key refused {#key-refused}", "## Key not accepted {#key-not-accepted}")
    edit(mini / "user" / "connect-an-account.md", "(user.connect-an-account#key-refused)", "(user.connect-an-account#key-not-accepted)")
    found = problems(mini)
    assert any("published anchor user.connect-an-account#key-refused no longer resolves" in p for p in found)
    edit(mini / "user" / "connect-an-account.md", "related:", "anchor_aliases: {key-refused: key-not-accepted}\nrelated:")
    found = [p for p in problems(mini) if "no longer resolves" in p]
    assert found == []


def test_a_new_anchor_must_be_recorded(mini):
    edit(mini / "admin" / "secrets.md", "## Replacing and removing {#replacing-and-removing}", "## Replacing and removing {#replacing-and-removing}\n\nx\n\n## Another {#another}")
    assert any("anchors.yaml lacks current anchors" in p for p in problems(mini))
    manual.Manual(mini).write_anchors()
    assert problems(mini) == []


def test_a_command_with_no_topic_is_reported_and_pending_is_honest(mini):
    ctx = mini / "context.yaml"
    data = yaml.safe_load(ctx.read_text(encoding="utf-8"))
    data["pending_commands"].remove("trace")
    ctx.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert any("command 'trace' has no manual topic" in p for p in problems(mini))
    data["pending_commands"] += ["trace", "nonesuch"]
    ctx.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert any("'nonesuch', which is not a baton command" in p for p in problems(mini))


def test_a_context_pointer_must_resolve(mini):
    edit(mini / "context.yaml", "user.choose-models#here-now", "user.choose-models#gone")
    assert any("ui.models" in p for p in problems(mini))


def test_search_resolve_and_sections():
    m = manual.Manual()
    assert m.search("openrouter")[0]["id"] == "providers.openrouter"
    t, a = m.resolve("user.connect-an-account#key-refused")
    section = m.section(t, a)
    assert section.startswith("## Key refused") and "## Replace or remove" not in section
    with pytest.raises(KeyError):
        m.resolve("user.nope")


def test_help_lists_prints_and_searches():
    out = runner.invoke(cli.app, ["help"])
    assert out.exit_code == 0 and "user.connect-an-account" in out.output and "Admin guide" in out.output
    out = runner.invoke(cli.app, ["help", "user.connect-an-account#key-refused"])
    assert out.exit_code == 0 and "A refused key is never stored" in out.output and "{#" not in out.output
    out = runner.invoke(cli.app, ["help", "--search", "keyring", "--json"])
    assert any(r["id"] == "admin.secrets" for r in json.loads(out.output)["results"])
    out = runner.invoke(cli.app, ["help", "user.nope"])
    assert out.exit_code == 1


def test_a_command_s_help_names_its_manual_topic():
    out = runner.invoke(cli.app, ["ui", "--help"])
    assert "baton help user.connect-an-account" in out.output.replace("\n", " ")
