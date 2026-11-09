"""Phase 1 acceptance: broken recipes are each rejected with a specific error."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baton.recipe import RecipeError, load_recipe

from conftest import step


def _set(path: str, key: str, value):
    def edit(r: dict, _: Path) -> None:
        step(r, path)[key] = value

    return edit


def _model_key(r, _):
    step(r, "triage")["requires"]["model"] = "some-model"


def _unknown_capability(r, _):
    step(r, "plan")["requires"]["capabilities"].append("telepathy")


def _vendor_string(r, _):
    r["description"] = "Use claude-sonnet for everything"


def _bad_foreach_not_array(r, _):
    step(r, "slices")["foreach"] = "steps.plan.output.slices.0.title"


def _bad_foreach_kind(r, _):
    step(r, "slices")["foreach"] = "run.inputs.feature_request"


def _missing_max_iterations(r, _):
    del step(r, "slices")["max_iterations"]


def _item_outside_group(r, _):
    step(r, "triage")["inputs"].append({"name": "x", "from": "item.id", "required": True})


def _cycle(r, _):
    step(r, "triage")["depends_on"] = ["plan"]


def _not_ancestor(r, _):
    step(r, "requirements")["inputs"].append({"name": "d", "from": "steps.design.artifacts.design_doc"})


def _missing_prompt(r, d: Path):
    (d / "prompts" / "design.md").unlink()


def _invalid_schema(r, d: Path):
    (d / "schemas" / "design_out.json").write_text(json.dumps({"type": "nonsense"}), encoding="utf-8")


def _unknown_gate(r, _):
    step(r, "design")["gates"].append({"type": "vibes"})


def _implicit_gate(r, _):
    step(r, "design")["gates"].append({"type": "provenance"})


def _publish_bad_var(r, _):
    step(r, "requirements")["artifacts"][0]["publish"]["to"] = "{{ env.HOME }}/req.md"


def _triage_applies_to(r, _):
    step(r, "triage")["applies_to"] = ["major"]


def _unknown_level(r, _):
    step(r, "design")["applies_to"] = ["gigantic"]


def _level_enum_mismatch(r, d: Path):
    p = d / "schemas" / "triage_out.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["properties"]["level"]["enum"] = ["minor", "major"]
    p.write_text(json.dumps(s), encoding="utf-8")


def _too_deep(r, _):
    inner = {"id": "inner", "steps": [{"id": "deeper", "steps": [{"id": "leaf", "requires": {}, "prompt": "prompts/plan.md"}]}]}
    step(r, "slices")["steps"].append(inner)


def _protect_on_read(r, _):
    step(r, "slices/code_review")["protect"] = ["src/**"]


def _bad_independence(r, _):
    step(r, "slices/code_review")["independence"]["from_step"] = "accept"


def _duplicate_id(r, _):
    step(r, "slices/accept")["id"] = "triage"


def _max_iterations_range(r, _):
    step(r, "slices")["max_iterations"] = 11


def _previous_findings_outside_repeat(r, _):
    del step(r, "slices")["repeat_until"]
    del step(r, "slices")["repeat_from"]
    del step(r, "slices")["max_iterations"]


def _findings_gate_without_schema(r, _):
    step(r, "slices/code_review")["output_schema"] = "schemas/design_out.json"


def _source_skippable(r, _):
    del step(r, "slices")["foreach_if_source_skipped"]


def _unknown_dependency(r, _):
    step(r, "plan")["depends_on"].append("nowhere")


def _unknown_tier(r, _):
    step(r, "plan")["requires"]["tier"] = "legendary"


def _items_without_id(r, d: Path):
    p = d / "schemas" / "plan_out.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    del s["properties"]["slices"]["items"]["properties"]["id"]
    p.write_text(json.dumps(s), encoding="utf-8")


def _items_require_id(r, d: Path):
    p = d / "schemas" / "plan_out.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["properties"]["slices"]["items"]["required"].append("id")
    p.write_text(json.dumps(s), encoding="utf-8")


def _unsupported_format(r, _):
    r["format"] = "baton-recipe/99"


def _unknown_vocab(r, _):
    r["capabilities_vocab"] = "baton-capabilities/99"


def _unknown_key(r, _):
    step(r, "plan")["colour"] = "blue"


def _bad_ref_syntax(r, _):
    step(r, "plan")["inputs"].append({"name": "q", "from": "somewhere.else"})


def _bad_repeat_until(r, _):
    step(r, "slices")["repeat_until"] = "group.steps.plan.gates.passed"


def _unknown_artifact(r, _):
    step(r, "plan")["inputs"][1]["from"] = "steps.design.artifacts.blueprint"


def _unknown_run_input(r, _):
    step(r, "triage")["inputs"][0]["from"] = "run.inputs.wishlist"


def _wrong_draft(r, d: Path):
    p = d / "schemas" / "design_out.json"
    s = json.loads(p.read_text(encoding="utf-8"))
    s["$schema"] = "http://json-schema.org/draft-07/schema#"
    p.write_text(json.dumps(s), encoding="utf-8")


def _block_on_missing(r, _):
    del step(r, "slices/code_review")["gates"][0]["block_on"]


def _unreachable(r, _):
    step(r, "slices")["applies_to"] = ["major"]
    step(r, "slices/accept")["applies_to"] = ["standard", "major"]


def _static_missing(r, _):
    step(r, "plan")["inputs"].append({"name": "s", "from": "static.missing.md"})


def _sibling_not_ancestor(r, _):
    step(r, "slices/implement")["inputs"].append({"name": "r", "from": "group.steps.code_review.output"})


def _inner_step_via_steps(r, _):
    step(r, "plan")["inputs"].append({"name": "c", "from": "steps.implement.output"})


CASES = [
    ("model key", _model_key, "neutrality.forbidden_key"),
    ("unknown capability", _unknown_capability, "vocab.unknown_capability"),
    ("vendor string", _vendor_string, "neutrality.vendor_string"),
    ("foreach not an array", _bad_foreach_not_array, "group.bad_foreach_source"),
    ("foreach wrong kind", _bad_foreach_kind, "group.bad_foreach_source"),
    ("missing max_iterations", _missing_max_iterations, "group.missing_max_iterations"),
    ("item outside group", _item_outside_group, "ref.item_outside_group"),
    ("cycle", _cycle, "graph.cycle"),
    ("reference to non-ancestor", _not_ancestor, "ref.not_ancestor"),
    ("missing prompt file", _missing_prompt, "file.missing"),
    ("invalid JSON schema", _invalid_schema, "schema.invalid"),
    ("unknown gate type", _unknown_gate, "gate.unknown_type"),
    ("explicit implicit gate", _implicit_gate, "gate.implicit_type"),
    ("publish.to bad variable", _publish_bad_var, "publish.bad_variable"),
    ("triage with applies_to", _triage_applies_to, "complexity.triage_has_applies_to"),
    ("unknown level", _unknown_level, "complexity.unknown_level"),
    ("triage level enum mismatch", _level_enum_mismatch, "complexity.level_enum_mismatch"),
    ("groups nested too deep", _too_deep, "group.too_deep"),
    ("protect on read step", _protect_on_read, "step.protect_requires_write"),
    ("independence from non-ancestor", _bad_independence, "independence.bad_from_step"),
    ("duplicate step id", _duplicate_id, "step.duplicate_id"),
    ("max_iterations out of range", _max_iterations_range, "group.max_iterations_range"),
    ("previous_iteration outside repeat", _previous_findings_outside_repeat, "ref.previous_iteration_outside_repeat"),
    ("findings gate without findings schema", _findings_gate_without_schema, "gate.findings_needs_findings_schema"),
    ("skippable foreach source without policy", _source_skippable, "group.foreach_source_skippable"),
    ("unknown dependency", _unknown_dependency, "graph.unknown_dependency"),
    ("unknown tier", _unknown_tier, "vocab.unknown_tier"),
    ("foreach items without id", _items_without_id, "group.foreach_items_need_id"),
    ("foreach items requiring id", _items_require_id, "group.foreach_id_required"),
    ("unsupported format", _unsupported_format, "format.unsupported"),
    ("unknown vocabulary", _unknown_vocab, "vocab.unsupported"),
    ("unknown key", _unknown_key, "recipe.unknown_key"),
    ("bad reference syntax", _bad_ref_syntax, "ref.invalid"),
    ("repeat_until outside group", _bad_repeat_until, "group.bad_repeat_until"),
    ("unknown artifact", _unknown_artifact, "ref.unknown_artifact"),
    ("unknown run input", _unknown_run_input, "ref.unknown_run_input"),
    ("schema of wrong draft", _wrong_draft, "schema.wrong_draft"),
    ("blocking findings gate without block_on", _block_on_missing, "gate.missing_block_on"),
    ("step unreachable at a level", _unreachable, "complexity.unreachable"),
    ("missing static file", _static_missing, "file.missing"),
    ("sibling reference not an ancestor", _sibling_not_ancestor, "ref.not_ancestor"),
    ("steps.<id> naming a nested step", _inner_step_via_steps, "ref.not_ancestor"),
]


@pytest.mark.parametrize("name,edit,code", CASES, ids=[c[0] for c in CASES])
@pytest.mark.slow
def test_broken_recipe_rejected(make_recipe, name, edit, code):
    root = make_recipe(edit)
    with pytest.raises(RecipeError) as exc:
        load_recipe(root)
    assert code in exc.value.codes(), str(exc.value)


def test_duplicate_yaml_key(make_recipe):
    root = make_recipe(text=lambda t: t.replace("version: 1\n", "version: 1\nversion: 2\n", 1))
    with pytest.raises(RecipeError) as exc:
        load_recipe(root)
    assert exc.value.codes() == {"yaml.duplicate_key"}


def test_missing_recipe_file(tmp_path):
    with pytest.raises(RecipeError) as exc:
        load_recipe(tmp_path)
    assert exc.value.codes() == {"file.missing"}


def test_all_errors_reported_together(make_recipe):
    def edit(r, _):
        _model_key(r, _)
        _bad_foreach_kind(r, _)
        _missing_max_iterations(r, _)

    with pytest.raises(RecipeError) as exc:
        load_recipe(make_recipe(edit))
    assert {"neutrality.forbidden_key", "group.bad_foreach_source", "group.missing_max_iterations"} <= exc.value.codes()


def test_forbidden_key_anywhere(make_recipe):
    def edit(r, _):
        step(r, "slices/implement")["gates"][1]["provider"] = "x"

    with pytest.raises(RecipeError) as exc:
        load_recipe(make_recipe(edit))
    assert "neutrality.forbidden_key" in exc.value.codes()


def test_crosswalk_is_linted(make_recipe):
    def edit(r, d: Path):
        (d / "crosswalks").mkdir()
        (d / "crosswalks" / "old.yaml").write_text("maps:\n  spec: { worker: x, note: gpt-4 }\n", encoding="utf-8")

    with pytest.raises(RecipeError) as exc:
        load_recipe(make_recipe(edit))
    assert {"neutrality.forbidden_key", "neutrality.vendor_string"} <= exc.value.codes()


def test_error_locations_name_steps(make_recipe):
    with pytest.raises(RecipeError) as exc:
        load_recipe(make_recipe(_unknown_key))
    (issue,) = [i for i in exc.value.issues if i.code == "recipe.unknown_key"]
    assert issue.where == "steps/plan.colour"


@pytest.mark.parametrize("bad", ["step1", "s2", "p_3", "phase_3", "step01_design", "task_10", "review_2"])
def test_positional_step_id_rejected(make_recipe, bad):
    root = make_recipe(lambda r, _: step(r, "slices/accept").update(id=bad))
    with pytest.raises(RecipeError) as exc:
        load_recipe(root)
    assert exc.value.codes() == {"step.positional_id"}


@pytest.mark.parametrize("good", ["accept", "oauth2_setup", "s3_upload_check", "phase_review", "sha256_verify"])
def test_role_step_id_accepted(make_recipe, good):
    def rename(r, _):
        step(r, "slices/accept").update(id=good)
        step(r, "slices")["repeat_until"] = step(r, "slices")["repeat_until"].replace(".accept.", f".{good}.")
    load_recipe(make_recipe(rename))
