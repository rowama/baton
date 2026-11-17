"""The shipped recipe-builder recipe (changes 2026-11-recipe-builder, 2026-11-builder-step-design): it loads, plans at every rating and is wired as designed."""
from __future__ import annotations

import json

import pytest
from jsonschema import Draft202012Validator

from baton.project import catalog
from baton.recipe import build_plan, load_recipe

from conftest import ROOT

BUILDER = ROOT / "examples" / "recipes" / "recipe-builder"


def steps(plan_level):
    return {s.path: s for s in plan_level.steps}


APPROACHES = ["simple", "standard", "complex"]


def at(loaded, approach, software="none"):
    """The plan at one pair of ratings, as {path: step}."""
    [lv] = build_plan(loaded, ratings={"approach": approach, "software": software}).levels
    return steps(lv)


@pytest.fixture(scope="module")
def loaded():
    return load_recipe(BUILDER)


def test_it_loads_cleanly_and_is_a_root_recipe_with_a_scope(loaded):
    r = loaded.recipe
    assert r.ref == "recipe-builder@4" and r.provenance == "scratch"
    assert r.scope is not None and r.scope.covers and r.scope.not_for
    assert not loaded.warnings


def test_it_ships_in_the_catalog():
    cx = catalog()["recipe-builder"].recipe.complexity
    assert cx.levels is None and {a: s.scale for a, s in cx.axes.items()} == {"approach": APPROACHES, "software": ["none", "simple"]}


def test_the_plan_at_each_approach_with_no_software_is_v3s_plan_at_that_level(loaded):

    by_level = {a: at(loaded, a) for a in APPROACHES}
    assert not by_level["simple"]["research"].included
    assert by_level["standard"]["research"].included and by_level["complex"]["research"].included

    def gate(level, path, type_):
        return [g for g in by_level[level][path].gates if g.type == type_]

    assert not gate("simple", "shape/audit", "human")[0].included  # the design is approved only above simple
    assert gate("standard", "shape/audit", "human")[0].included
    assert not gate("standard", "generate", "review")[0].included  # a package review only at complex
    assert gate("complex", "generate", "review")[0].included
    for lv in by_level.values():
        assert [g.type for g in lv["generate"].gates if g.type == "script"] == ["script", "script"]


def test_the_loop_is_bounded_and_audited_by_another_vendor(loaded):
    shape = next(s for s in loaded.recipe.steps if s.id == "shape")
    assert shape.max_iterations == 3 and shape.repeat_from == "design"
    audit = next(s for s in shape.steps if s.id == "audit")
    assert audit.independence.from_step == "design" and audit.independence.level == "different_vendor"
    assert {i.name: i.from_ for i in audit.inputs}["patterns"] == "static.patterns.md"
    design = next(s for s in shape.steps if s.id == "design")
    assert {i.name: i.from_ for i in design.inputs}["patterns"] == "static.patterns.md"


def test_generate_runs_the_deterministic_checks_on_its_own_draft(loaded):
    gen = next(s for s in loaded.recipe.steps if s.id == "generate")
    cmds = [g.run for g in gen.gates if g.type == "script"]
    assert cmds[0] == "baton plan recipes/drafts/{{ run.slug }}"
    assert cmds[1].startswith("baton recipe check recipes/drafts/{{ run.slug }} --ledger recipes/drafts/{{ run.slug }}.ledger.json")
    assert {a.name for a in gen.artifacts} == {"walkthrough", "ledger"}


def test_profile_reads_the_catalog_the_plan_directory_and_publishes_the_process_plan(loaded):
    profile = next(s for s in loaded.recipe.steps if s.id == "profile")
    assert {i.name: i.from_ for i in profile.inputs}["recipes"] == "catalog.summaries"
    assert profile.workspace == "read"
    plan = next(a for a in profile.artifacts if a.name == "process_plan")
    assert plan.publish.to == "recipes/plans/{{ run.slug }}.md" and not plan.required


def test_the_profile_prompt_holds_the_generality_rules():
    text = (BUILDER / "prompts" / "profile.md").read_text(encoding="utf-8")
    assert "narrowest rung" in text and "next wider rung" in text  # Decision 0099
    assert "recipes/plans/" in text  # Decision 0102
    assert "existing_recipe" in text and "base_recipe" in text
    assert "Never\nrecommend a wider rung unless" in text or "recommend a wider rung unless" in text.replace("\n", " ")


def test_every_ledger_in_the_schemas_is_the_ledger_schema():
    entry = json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))["items"]
    for name, path in (("profile_out", ("ledger",)), ("research_out", ("ledger",)), ("design_out", ("ledger",))):
        schema = json.loads((BUILDER / "schemas" / f"{name}.json").read_text(encoding="utf-8"))
        assert schema["properties"][path[0]]["items"] == entry, name


def test_the_ledger_schema_and_the_checker_agree_on_the_vocabulary():
    from baton import recipe_check

    entry = json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))["items"]["properties"]
    assert tuple(entry["status"]["enum"]) == recipe_check.STATUSES
    assert tuple(entry["scope"]["enum"]) == recipe_check.SCOPES


def test_an_example_ledger_is_valid_and_passes_the_check(tmp_path):
    from baton import recipe_check

    ledger = [
        {"id": "G1", "statement": "A plan for planting a flower bed", "kind": "goal", "scope": "class", "status": "confirmed",
         "basis": "the owner's words", "owner_words": "I want to plant a flower bed properly"},
        {"id": "I1", "statement": "The shed is 2 m by 3 m and painted green", "kind": "requirement", "scope": "instance",
         "status": "confirmed", "basis": "the owner's words", "owner_words": "two by three metres, green", "value": "2 m by 3 m, green"},
    ]
    schema = json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))
    assert Draft202012Validator(schema).is_valid(ledger)
    f = tmp_path / "ledger.json"
    f.write_text(json.dumps(ledger), encoding="utf-8")
    assert recipe_check.check(BUILDER, f) == []  # the builder's own prompts hold no instance fact


def test_run_inputs_take_an_idea_and_an_optional_base_recipe():
    v = Draft202012Validator(json.loads((BUILDER / "schemas" / "run_inputs.json").read_text(encoding="utf-8")))
    assert v.is_valid({"title": "Flower bed", "idea": "plant a flower bed"})
    assert v.is_valid({"title": "t", "idea": "i", "base_recipe": "backyard-project@1", "profile": {"a": 1}})
    assert not v.is_valid({"title": "t", "idea": "i", "base_recipe": "backyard-project"})
    assert not v.is_valid({"title": "t"})


def test_the_triage_schema_rates_both_axes_with_reasons_and_carries_more():
    schema = json.loads((BUILDER / "schemas" / "profile_out.json").read_text(encoding="utf-8"))
    axes = schema["properties"]["ratings"]["properties"]
    assert axes["approach"]["properties"]["value"]["enum"] == APPROACHES
    assert axes["software"]["properties"]["value"]["enum"] == ["none", "simple"]
    assert "level" not in schema["properties"]
    assert {"goal", "rung", "ledger", "existing_recipe", "related_parts", "build_now"} <= set(schema["properties"])


def test_no_prompt_names_a_vendor(loaded):
    assert not [w for w in loaded.warnings if w.code.startswith("neutrality")]


# -- implementation discovery (change 2026-11-recipe-implementation-discovery; Decision 0141) ----------------

V2 = ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v2"


def schema_of(name):
    return Draft202012Validator(json.loads((BUILDER / "schemas" / f"{name}.json").read_text(encoding="utf-8")))


NOT_NEEDED = {"id": "D0", "question": "Is there an implementation choice that matters?", "target_status": "none", "timing": "not_needed",
              "timing_reason": "One usual way of doing it", "status": "closed"}
BEFORE = {"id": "D1", "question": "A printed guide or an app?", "target_status": "example", "named_targets": ["a garden app"],
          "timing": "before_design", "timing_reason": "They need different deliverables", "graph_effect": "Layout and proofing vs build and test",
          "status": "to_research"}
COMPARISON = {"criteria": ["no software to maintain"], "uncertainty": "", "recommendation": "A printed guide",
              "options": [{"name": "A printed guide", "kind": "manual_procedure", "requires_of_development": "layout, proof check",
                           "tradeoffs": "no reminders", "sources": [{"title": "A handbook", "read_on": "2026-11-13"}]}]}
DECIDED = {**BEFORE, "status": "decided", "comparison": COMPARISON, "decision": {"ledger_id": "E9"}}
DEFERRED = {"id": "D2", "question": "Which tool does a job use?", "target_status": "none", "timing": "in_generated_recipe",
            "timing_reason": "One shape serves every tool", "status": "deferred",
            "generated": {"research_step": "research_options", "decision_step": "decide", "consumers": ["build"]}}
GOAL = {"id": "G1", "statement": "s", "kind": "goal", "scope": "class", "status": "confirmed", "basis": "b", "owner_words": "w"}
def rated(approach, software="none"):
    return {"approach": {"value": approach, "reason": "r"}, "software": {"value": software, "reason": "r"}}


PROFILE = {"ratings": rated("standard"), "reasons": ["r"], "goal": {"statement": "s", "trigger": "t", "end_state": "e", "success_measure": "m"},
           "existing_recipe": None, "rung": {"label": "l", "covers": ["c"], "next_rung": None}, "ledger": [GOAL], "discovery": [NOT_NEEDED]}


def test_the_profile_must_record_discovery_and_a_shaping_choice_makes_the_work_at_least_standard():
    v = schema_of("profile_out")
    assert v.is_valid(PROFILE)
    assert not v.is_valid({k: x for k, x in PROFILE.items() if k != "discovery"})  # never silently dropped
    assert not v.is_valid({**PROFILE, "discovery": []})
    assert v.is_valid({**PROFILE, "discovery": [BEFORE]})
    assert not v.is_valid({**PROFILE, "ratings": rated("simple"), "discovery": [BEFORE]})  # an early choice cannot hide behind a simple approach
    assert not v.is_valid({**PROFILE, "ratings": rated("simple", "simple"), "discovery": [BEFORE]})  # nor behind software
    assert v.is_valid({**PROFILE, "ratings": rated("simple"), "discovery": [NOT_NEEDED, DEFERRED]})
    assert not v.is_valid({**PROFILE, "ratings": {"approach": {"value": "simple", "reason": ""}, "software": {"value": "none", "reason": "r"}}})
    assert not v.is_valid({**PROFILE, "ratings": {"approach": {"value": "simple", "reason": "r"}}})  # both axes, always  # a deferred one stays proportionate
    assert not v.is_valid({**PROFILE, "discovery": [{**BEFORE, "status": "decided"}]})  # the profile cannot claim a decision
    assert not v.is_valid({**PROFILE, "discovery": [{**NOT_NEEDED, "target_status": "keyword"}]})


def test_research_returns_a_shaping_choice_only_once_the_owner_decided_it():
    v = schema_of("research_out")
    base = {"ledger": [GOAL], "sources": []}
    assert v.is_valid({**base, "discovery": [NOT_NEEDED]})
    assert v.is_valid({**base, "discovery": [DECIDED]})
    assert not v.is_valid({**base, "discovery": [BEFORE]})  # an unanswered choice is `blocked`, not `completed`
    assert not v.is_valid({**base, "discovery": [{**DECIDED, "decision": None}]})
    assert not v.is_valid({**base, "discovery": [{k: x for k, x in DECIDED.items() if k != "comparison"}]})
    undated = {**DECIDED, "comparison": {**COMPARISON, "options": [{**COMPARISON["options"][0], "sources": [{"title": "t"}]}]}}
    assert not v.is_valid({**base, "discovery": [undated]})  # a source carries the date it was read


def test_design_carries_decided_and_deferred_choices_with_their_handoff():
    v = schema_of("design_out")
    base = {"summary": "s", "stages": [AI_STAGE], "ledger": [GOAL]}
    assert v.is_valid({**base, "discovery": [DECIDED, DEFERRED]})
    assert not v.is_valid({**base, "discovery": [BEFORE]})
    assert not v.is_valid({**base, "discovery": [{k: x for k, x in DEFERRED.items() if k != "generated"}]})
    assert not v.is_valid({**base, "discovery": [{**DEFERRED, "generated": {"research_step": "a", "decision_step": "b", "consumers": []}}]})


def test_the_ledger_file_schema_is_the_ledger_and_the_discovery_schemas():
    f = json.loads((BUILDER / "schemas" / "ledger_file.json").read_text(encoding="utf-8"))
    assert f["properties"]["ledger"] == json.loads((BUILDER / "schemas" / "ledger.json").read_text(encoding="utf-8"))
    disc = json.loads((BUILDER / "schemas" / "discovery.json").read_text(encoding="utf-8"))
    assert f["properties"]["discovery"] == disc
    assert Draft202012Validator(f).is_valid({"ledger": [GOAL], "discovery": [DECIDED, DEFERRED]})
    assert not Draft202012Validator(f).is_valid([GOAL])
    design = json.loads((BUILDER / "schemas" / "design_out.json").read_text(encoding="utf-8"))
    assert {k: x for k, x in disc.items() if k not in ("$schema", "title")} == design["properties"]["discovery"]


def test_the_discovery_vocabulary_matches_the_checker():
    from baton import recipe_check

    item = json.loads((BUILDER / "schemas" / "discovery.json").read_text(encoding="utf-8"))["items"]["properties"]
    assert tuple(item["timing"]["enum"]) == recipe_check.TIMINGS
    assert tuple(item["target_status"]["enum"]) == recipe_check.TARGET_STATUSES


def test_generate_requires_discovery_and_research_is_reachable_when_it_is_needed(loaded):
    gen = next(s for s in loaded.recipe.steps if s.id == "generate")
    assert [g.run for g in gen.gates if g.type == "script"][1].endswith("--require-discovery")
    research = next(s for s in loaded.recipe.steps if s.id == "research")
    assert "web_access" in research.requires.capabilities  # current external claims need a research-capable worker
    assert research.applies_to == {"approach": ["standard", "complex"]}  # the profile schema keeps a shaping choice out of a `simple` approach


def test_the_prompts_patterns_and_rubric_carry_the_discovery_rules():
    read = lambda *p: (BUILDER.joinpath(*p)).read_text(encoding="utf-8")  # noqa: E731
    profile, research, design, audit = (read("prompts", f"{n}.md") for n in ("profile", "research", "design", "audit"))
    assert "before_design" in profile and "in_generated_recipe" in profile and "firm_constraint" in profile
    assert "never\npick an answer" in profile or "never pick an answer" in profile.replace("\n", " ")
    assert "read_on" in research and "A recommendation is not a decision" in research and "blocked" in research
    assert "decision.ledger_id" in design and "generated" in design
    assert "checks 16 to 20" in audit
    assert "Discovering implementation options" in read("static", "patterns.md")
    rubric = read("static", "readiness.md")
    for n in range(16, 21):
        assert f"| {n} |" in rubric
    assert "fixed implementation target" in read("prompts", "package_review_rubric.md")
    gen = read("prompts", "generate.md")
    assert "legitimate target" in gen and "never a fixed value" in gen


def test_the_published_v2_still_loads_and_keeps_its_behavior():
    """A project's pinned recipe-builder@2 is never edited (§5.8): v3 is a new version, the v2 package is untouched."""
    old = load_recipe(V2)
    assert old.recipe.ref == "recipe-builder@2" and not old.warnings
    gen = next(s for s in old.recipe.steps if s.id == "generate")
    assert not [g.run for g in gen.gates if g.type == "script" and "--require-discovery" in g.run]
    assert "discovery" not in json.loads((V2 / "schemas" / "profile_out.json").read_text(encoding="utf-8"))["properties"]
    assert [lv.level for lv in build_plan(old).levels] == ["simple", "standard", "complex"]


V3 = ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v3"


def test_the_published_v3_still_loads_with_its_levels():
    """A project's pinned recipe-builder@3 is never edited (§5.8): v4 is a new version, the v3 package is a frozen copy."""
    old = load_recipe(V3)
    assert old.recipe.ref == "recipe-builder@3" and not old.warnings
    assert [lv.level for lv in build_plan(old).levels] == APPROACHES
    assert "level" in json.loads((V3 / "schemas" / "profile_out.json").read_text(encoding="utf-8"))["properties"]


def test_v4_loads_and_plans_at_every_pair_of_ratings(loaded):
    assert loaded.recipe.ref == "recipe-builder@4" and not loaded.warnings
    for a in APPROACHES:
        for sw in ("none", "simple"):
            assert at(loaded, a, sw)["generate"].included


def test_software_shows_the_owner_the_design_and_reviews_the_package_at_every_approach(loaded):
    for a in APPROACHES:
        plan = at(loaded, a, "simple")
        assert [g.included for g in plan["shape/audit"].gates if g.type == "human"] == [True]
        assert [g.included for g in plan["generate"].gates if g.type == "review"] == [True]
        assert plan["research"].included == (a != "simple")  # software adds no research


def test_simple_with_no_software_applies_at_once_and_anything_else_waits_on_the_owner(loaded):
    from baton import tailoring

    cx = loaded.recipe.complexity
    assert tailoring.auto_approves(cx, {"approach": "simple", "software": "none"})
    assert not tailoring.auto_approves(cx, {"approach": "simple", "software": "simple"})
    assert not tailoring.auto_approves(cx, {"approach": "standard", "software": "none"})


def test_existing_recipes_match_only_when_their_process_does_the_discovery_and_the_walkthrough_says_when_the_owner_chooses():
    profile = " ".join((BUILDER / "prompts" / "profile.md").read_text(encoding="utf-8").split())
    assert "its own steps would do any discovery this job needs (a matching subject is not enough)" in profile
    gen = " ".join((BUILDER / "prompts" / "generate.md").read_text(encoding="utf-8").split())
    assert "when and how the owner will choose how the work is done" in gen


# -- step design (change 2026-11-builder-step-design, Slice 3; Decisions 0155, 0161, 0162) ----------------

OPEN = {"rules": "none", "input": "open", "repeatable": "not_required", "effect": "none", "result": "certain", "check": "judgment",
        "basis": "Writing a welcome letter."}
RULES = {"rules": "complete", "input": "structured", "repeatable": "required", "effect": "none", "result": "certain", "check": "mechanical",
         "basis": "Totals are sums of the listed amounts."}
AI_STAGE = {"id": "s", "title": "t", "done_by": "ai", "needs": [], "hands_on": [], "on_failure": "retry", "traits": OPEN,
            "acceptance": {"kind": "judgment", "what": "The owner reads it."}}
TOOL = {"id": "total_lines", "does": "Adds up the amounts.", "input": "a list of amounts", "output": "the total",
        "reach": {"workspace": "none", "network": False, "secrets": []},
        "examples": [{"name": "two-lines", "input": {"amounts": [1, 2]}, "expected": {"total": 3}, "says": "1 and 2 make 3."}]}
TOOL_STAGE = {**AI_STAGE, "done_by": "tool", "traits": RULES, "acceptance": {"kind": "rule", "what": "The total equals the sum."}, "tool": TOOL}
CHOICE = {"could_be": "a small program", "reason": "ceiling", "gives_up": "the same total every time, at no cost per run",
          "would_cost": "writing and checking a program"}
PERSON = {**AI_STAGE, "done_by": "person", "delegation": {"risky": False, "reason": "Only notes are taken."}}


def design_valid(*stages):
    return schema_of("design_out").is_valid({"summary": "s", "stages": list(stages), "ledger": [GOAL], "discovery": [NOT_NEEDED]})


def test_every_stage_says_what_its_work_is_like_and_what_its_check_establishes():
    assert design_valid(AI_STAGE)
    assert not design_valid({k: x for k, x in AI_STAGE.items() if k != "traits"})
    assert not design_valid({k: x for k, x in AI_STAGE.items() if k != "acceptance"})
    assert not design_valid({**AI_STAGE, "traits": {**OPEN, "basis": ""}})
    assert not design_valid({**AI_STAGE, "traits": {k: x for k, x in OPEN.items() if k != "result"}})
    assert not design_valid({**AI_STAGE, "acceptance": {"kind": "looks_fine", "what": "x"}})


def test_a_stage_with_an_effect_or_an_uncertain_result_needs_more_than_a_format_check():
    fmt = {"kind": "format", "what": "It is valid JSON."}
    assert design_valid({**AI_STAGE, "acceptance": fmt})
    assert not design_valid({**AI_STAGE, "acceptance": fmt, "traits": {**OPEN, "effect": "reversible"}})
    assert not design_valid({**AI_STAGE, "acceptance": fmt, "traits": {**OPEN, "result": "uncertain"}})


def test_a_tool_stage_has_its_tool_with_an_example_and_only_a_tool_stage_has_one():
    assert design_valid(TOOL_STAGE)
    assert not design_valid({k: x for k, x in TOOL_STAGE.items() if k != "tool"})
    assert not design_valid({**TOOL_STAGE, "tool": {**TOOL, "examples": []}})
    assert not design_valid({**TOOL_STAGE, "tool": {**TOOL, "id": "Total Lines"}})
    assert not design_valid({**AI_STAGE, "tool": TOOL})


def test_an_ai_stage_software_could_do_carries_why_and_the_owners_choice_names_their_words():
    could = {**AI_STAGE, "traits": RULES}
    assert not design_valid(could)
    assert design_valid({**could, "executor_choice": CHOICE})
    assert not design_valid({**could, "executor_choice": {**CHOICE, "reason": "owner_choice"}})
    assert design_valid({**could, "executor_choice": {**CHOICE, "reason": "owner_choice", "ledger_id": "E4"}})
    assert not design_valid({**could, "executor_choice": {k: x for k, x in CHOICE.items() if k != "gives_up"}})
    # A stage that must repeat needs the record even when its rules are only partial.
    assert not design_valid({**AI_STAGE, "traits": {**OPEN, "repeatable": "required"}})
    assert not design_valid({**TOOL_STAGE, "executor_choice": CHOICE})  # only an AI stage explains itself


def test_a_persons_stage_and_an_owner_decision_say_whether_delegating_them_is_risky():
    assert design_valid(PERSON)
    assert not design_valid({k: x for k, x in PERSON.items() if k != "delegation"})
    assert not design_valid({**AI_STAGE, "owner_decision": "Send it?"})
    assert design_valid({**AI_STAGE, "owner_decision": "Send it?", "delegation": {"risky": False, "reason": "A draft only."}})
    gone = {**PERSON, "traits": {**OPEN, "effect": "irreversible"}}
    assert not design_valid(gone)  # an act that cannot be undone is always marked risky
    assert design_valid({**gone, "delegation": {"risky": True, "reason": "The payment cannot be taken back."}})


def test_the_patterns_rubric_and_prompts_carry_the_step_design_rules():
    read = lambda *p: " ".join(BUILDER.joinpath(*p).read_text(encoding="utf-8").split())  # noqa: E731
    patterns, rubric = read("static", "patterns.md"), read("static", "readiness.md")
    for shape in ("## 8. One kind of work per stage", "## 9. Interpret, then enforce", "## 10. The simplest means that can do the work"):
        assert shape in patterns
    assert "The tool budget." in patterns and "Software before an AI worker." in patterns
    import re

    for n in range(21, 28):
        assert re.search(rf"\| {n} \| [^|]+ \| high \|", rubric), n  # each new check blocks the design
    design, audit = read("prompts", "design.md"), read("prompts", "audit.md")
    assert "`rating_signal`" in design and '{axis: "software", suggested: "simple", reason}' in design
    assert "executor_choice" in design and "delegation" in design and "plan no tool for it" in design
    assert "checks 21 to 27" in audit
