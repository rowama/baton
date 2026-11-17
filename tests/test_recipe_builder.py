"""The shipped recipe-builder recipe (changes 2026-11-recipe-builder, 2026-11-builder-step-design, 2026-11-quick-runs): it loads, plans at every rating and is wired as designed."""
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


APPROACHES = ["simple", "standard", "complex"]  # the full process (recipe-builder@4's whole scale)
SCALE = ["quick", *APPROACHES]                   # recipe-builder@5 (2026-11-quick-runs)
SOFTWARE = ["none", "simple", "engineered"]       # recipe-builder@6 (2026-11-builder-engineered-tools)


def at(loaded, approach, software="none"):
    """The plan at one pair of ratings, as {path: step}."""
    [lv] = build_plan(loaded, ratings={"approach": approach, "software": software}).levels
    return steps(lv)


@pytest.fixture(scope="module")
def loaded():
    return load_recipe(BUILDER)


def test_it_loads_cleanly_and_is_a_root_recipe_with_a_scope(loaded):
    r = loaded.recipe
    assert r.ref == "recipe-builder@6" and r.provenance == "scratch"
    assert r.scope is not None and r.scope.covers and r.scope.not_for
    assert not loaded.warnings


def test_it_ships_in_the_catalog():
    cx = catalog()["recipe-builder"].recipe.complexity
    assert cx.levels is None and {a: s.scale for a, s in cx.axes.items()} == {"approach": SCALE, "software": SOFTWARE}
    assert cx.axes["approach"].confirm_lowest is True and not cx.axes["software"].confirm_lowest


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
        assert [g.type for g in lv["generate"].gates if g.type == "script"] == ["script", "script", "script"]


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
    assert {i.name: (i.from_, i.required) for i in profile.inputs}["guides"] == ("catalog.guides", False)
    assert [g.type for g in profile.gates] == ["schema"]  # the ratings' approval is its one owner question (Decision 0163)
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
    assert axes["approach"]["properties"]["value"]["enum"] == SCALE
    assert axes["software"]["properties"]["value"]["enum"] == SOFTWARE
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


def test_v6_loads_and_plans_at_every_pair_of_ratings(loaded):
    assert loaded.recipe.ref == "recipe-builder@6" and not loaded.warnings
    for a in APPROACHES:
        for sw in SOFTWARE:
            plan = at(loaded, a, sw)
            assert plan["generate"].included and plan["accept"].included and not plan["guide"].included


def test_the_quick_path_runs_only_the_profile_and_the_guide(loaded):
    plan = at(loaded, "quick")
    assert {p for p, st in plan.items() if st.included} == {"profile", "guide"}
    guide = next(s for s in loaded.recipe.steps if s.id == "guide")
    assert guide.depends_on == ["profile"] and guide.workspace == "none"
    assert {i.name: (i.from_, i.required) for i in guide.inputs} == {
        "idea": ("run.inputs.idea", True), "profile": ("steps.profile.output", True), "guides": ("catalog.guides", True)}
    (art,) = guide.artifacts
    assert (art.name, art.required, art.media_type, art.publish.to) == ("guide", True, "text/markdown", "guides/{{ run.slug }}.md")
    assert [g.type for g in guide.gates] == ["schema", "script", "human"]
    assert guide.gates[1].run == "baton guides check --artifact guide" and guide.gates[2].prompt == "Use this guide?"


QUICK = {"action": "adapt", "base": "lean-business-plan", "why": "a plan to start on, for a water stand"}


def test_a_quick_rating_names_its_guide_and_never_allows_software():
    v = schema_of("profile_out")
    q = {**PROFILE, "ratings": rated("quick"), "guide_choice": QUICK}
    assert v.is_valid(q)
    assert not v.is_valid({k: x for k, x in q.items() if k != "guide_choice"})  # quick names its guide
    assert not v.is_valid({**q, "guide_choice": None})
    assert not v.is_valid({**q, "ratings": rated("quick", "simple")})  # quick requires software: none (Decision 0162, item 3)
    assert not v.is_valid({**q, "discovery": [BEFORE]})  # a choice that shapes a process is never quick
    assert v.is_valid({**q, "guide_choice": {"action": "write", "base": None, "why": "none fits"}})
    assert not v.is_valid({**q, "guide_choice": {"action": "write", "base": "lean-business-plan", "why": "w"}})
    assert not v.is_valid({**q, "guide_choice": {"action": "adopt", "base": None, "why": "w"}})
    assert not v.is_valid({**PROFILE, "guide_choice": QUICK})  # the full process names no guide
    assert v.is_valid({**PROFILE, "guide_choice": None})


def test_the_guide_output_says_what_was_done_to_which_guide():
    v = schema_of("guide_out")
    base = {"id": "water-stand-plan", "summary": "s", "changes": []}
    assert v.is_valid({**base, "action": "written", "base": None})
    assert v.is_valid({**base, "action": "adopted", "base": "lean-business-plan"})
    assert not v.is_valid({**base, "action": "adapted", "base": "lean-business-plan"})  # an adaptation lists its changes
    assert v.is_valid({**base, "action": "adapted", "base": "lean-business-plan", "changes": ["a section on water quality"]})
    assert not v.is_valid({**base, "action": "written", "base": "lean-business-plan"})
    assert not v.is_valid({**base, "id": "Water Plan", "action": "written", "base": None})


def test_the_profile_and_guide_prompts_carry_the_quick_path_rules():
    def read(*p):
        return BUILDER.joinpath(*p).read_text(encoding="utf-8")

    profile = read("prompts", "profile.md")
    assert "## 1a. A full process, or a quick guided run" in profile and "`guide_choice`" in profile
    assert "| `quick` |" in profile and "A quick run is always `none`." in profile
    assert "The owner is asked once, here," in profile
    guide = read("prompts", "guide.md")
    for section in ("## Purpose", "## What to produce", "## What good looks like", "## What to ask the owner"):
        assert section in guide
    assert "format: baton-guide/1" in guide and "Never put this owner's own facts in the guide" in guide


def test_software_shows_the_owner_the_design_and_reviews_the_package_at_every_approach(loaded):
    for a in APPROACHES:
        plan = at(loaded, a, "simple")
        assert [g.included for g in plan["shape/audit"].gates if g.type == "human"] == [True]
        assert [g.included for g in plan["generate"].gates if g.type == "review"] == [True]
        assert plan["research"].included == (a != "simple")  # software adds no research


def test_every_rating_waits_on_the_owner_in_v5_and_v4_still_applies_its_lowest_at_once(loaded):
    from baton import tailoring

    cx = loaded.recipe.complexity
    for a in SCALE:
        for sw in SOFTWARE:
            assert not tailoring.auto_approves(cx, {"approach": a, "software": sw}), (a, sw)
    v4 = load_recipe(V4).recipe.complexity
    assert tailoring.auto_approves(v4, {"approach": "simple", "software": "none"})
    assert not tailoring.auto_approves(v4, {"approach": "standard", "software": "none"})


V4 = ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v4"


def test_the_published_v4_still_loads_with_two_axes_and_its_own_profile_question():
    """A project's pinned recipe-builder@4 is never edited (§5.8): v5 is a new version, the v4 package is a frozen copy."""
    old = load_recipe(V4)
    assert old.recipe.ref == "recipe-builder@4" and not old.warnings
    assert old.recipe.complexity.axes["approach"].scale == APPROACHES
    profile = next(s for s in old.recipe.steps if s.id == "profile")
    assert [g.type for g in profile.gates] == ["schema", "human"]
    assert "guide" not in {s.id for s in old.recipe.steps}


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


def test_generate_is_gated_on_every_tool_passing_its_examples_and_writes_the_walkthrough_lists(loaded):
    gen = next(s for s in loaded.recipe.steps if s.id == "generate")
    assert [g.run for g in gen.gates if g.type == "script"][2] == "baton tools test recipes/drafts/{{ run.slug }} --require-examples --allow-unbuilt"
    prompt = " ".join((BUILDER / "prompts" / "generate.md").read_text(encoding="utf-8").split())
    assert "the Python standard library only, no network, no secrets" in prompt
    assert "Small programs in this process:" in prompt and "Parts an AI helper does that a program could do:" in prompt
    assert "An example the owner approved is never changed to fit the code." in prompt
    rubric = (BUILDER / "prompts" / "package_review_rubric.md").read_text(encoding="utf-8")
    assert "imports anything outside the Python standard library" in rubric and "were changed to fit the code" in rubric


# -- engineered tools (change 2026-11-builder-engineered-tools, Slice 2; Decisions 0155, 0164) --------------

V5 = ROOT / "tests" / "fixtures" / "recipes" / "recipe-builder-v5"


def test_the_published_v5_still_loads_with_two_software_settings():
    """A project's pinned recipe-builder@5 is never edited (§5.8): v6 is a new version, the v5 package is a frozen copy."""
    old = load_recipe(V5)
    assert old.recipe.ref == "recipe-builder@5" and not old.warnings
    assert old.recipe.complexity.axes["software"].scale == ["none", "simple"]
    assert not {"example_plan", "examples"} & {s.id for s in old.recipe.steps}


def test_engineered_adds_the_example_steps_the_design_approval_and_the_package_review_at_every_approach(loaded):
    for a in APPROACHES:
        for sw in SOFTWARE:
            plan = at(loaded, a, sw)
            assert plan["example_plan"].included == plan["examples"].included == (sw == "engineered")
        plan = at(loaded, a, "engineered")
        assert [g.included for g in plan["shape/audit"].gates if g.type == "human"] == [True]
        assert [g.included for g in plan["generate"].gates if g.type == "review"] == [True]
    assert not at(loaded, "quick")["example_plan"].included


def test_the_owners_examples_are_a_role_and_the_examples_step_is_gated_by_the_check_and_the_owner(loaded):
    [role] = loaded.recipe.project_inputs
    assert (role.role, role.many, role.required) == ("examples", True, False)
    by_id = {s.id: s for s in loaded.recipe.steps}
    plan, ex, acc = by_id["example_plan"], by_id["examples"], by_id["accept"]
    assert plan.depends_on == ["generate"] and plan.requires.capabilities == ["human_judgment"]
    assert ex.depends_on == ["example_plan"] and ex.workspace == "write"
    assert {i.name: (i.from_, i.required) for i in ex.inputs}["owner_examples"] == ("project.examples", False)
    assert [g.type for g in ex.gates] == ["schema", "script", "human"]
    assert ex.gates[1].run == "baton tools examples recipes/drafts/{{ run.slug }} --run {{ run.id }}"
    assert acc.depends_on == ["generate", "examples", "build_tools"]


ENGINEERED_TOOL = {"id": "match_payments", "kind": "engineered", "does": "Matches the bank's payments to the invoices.",
                   "input": "the bank export and the invoice list", "output": "matched and unmatched payments",
                   "reach": {"workspace": "none", "network": False, "secrets": []},
                   "contract": {"input_schema": {"type": "object"}, "output_schema": {"type": "object"},
                                "packages": [{"name": "python-dateutil", "why": "the export writes dates three ways"}],
                                "budget_reason": "One command: two files in, one report out, nothing kept running."},
                   "examples_needed": [{"name": "march", "what": "March's export and invoices, and the matches you made", "awkward": False},
                                       {"name": "april", "what": "April's, the same", "awkward": False},
                                       {"name": "split", "what": "A payment that covers two invoices", "awkward": True}]}


def test_an_engineered_tool_gives_a_contract_and_the_examples_the_owner_should_supply():
    ok = {**TOOL_STAGE, "tool": ENGINEERED_TOOL}
    assert design_valid(ok)
    assert design_valid({**TOOL_STAGE, "tool": {**TOOL, "kind": "simple"}})
    for broken in ({k: v_ for k, v_ in ENGINEERED_TOOL.items() if k != "contract"},
                   {**ENGINEERED_TOOL, "examples_needed": ENGINEERED_TOOL["examples_needed"][:2]},
                   {**ENGINEERED_TOOL, "examples_needed": [{**e, "awkward": False} for e in ENGINEERED_TOOL["examples_needed"]]},
                   {**ENGINEERED_TOOL, "contract": {**ENGINEERED_TOOL["contract"], "packages": [{"name": "x"}]}},
                   {**TOOL, "contract": ENGINEERED_TOOL["contract"]}):  # a simple tool has no contract
        assert not design_valid({**TOOL_STAGE, "tool": broken}), broken


def test_a_choice_to_have_examples_drafted_records_the_warning_and_the_owners_words():
    v = schema_of("example_plan_out")
    assert v.is_valid({"tools": [{"tool": "match_payments", "supplied": 3, "drafted": 0}]})
    assert not v.is_valid({"tools": [{"tool": "match_payments", "supplied": 1, "drafted": 2}]})
    assert not v.is_valid({"tools": [{"tool": "match_payments", "supplied": 1, "drafted": 2, "warned": False, "owner_words": "Draft them."}]})
    assert v.is_valid({"tools": [{"tool": "match_payments", "supplied": 0, "drafted": 3, "warned": True,
                                  "owner_words": "I understand; draft them and I'll check each one."}]})


def test_the_placed_examples_are_at_least_three_one_awkward_with_their_source():
    v = schema_of("examples_out")
    ex = [{"name": n, "source": "owner", "awkward": n == "split", "says": "s"} for n in ("march", "april", "split")]
    assert v.is_valid({"commit_sha": "abc1234", "tools": [{"tool": "match_payments", "examples": ex}], "summary": "s"})
    assert not v.is_valid({"commit_sha": "abc1234", "tools": [{"tool": "match_payments", "examples": ex[:2]}], "summary": "s"})
    assert not v.is_valid({"commit_sha": "abc1234", "tools": [{"tool": "match_payments", "examples": [{**e, "awkward": False} for e in ex]}],
                           "summary": "s"})


def test_the_prompts_patterns_and_rubric_carry_the_engineered_tool_rules():
    read = lambda rel: " ".join((BUILDER / rel).read_text(encoding="utf-8").split())  # noqa: E731
    assert "| `engineered` |" in read("prompts/profile.md") and "what it will ask of the owner" in read("prompts/profile.md")
    design = read("prompts/design.md")
    assert "`kind: engineered`" in design and "`examples_needed`" in design and "A tool is `engineered` only at `software: engineered`" in design
    generate = read("prompts/generate.md")
    assert "`tools/<id>/contract.json`" in generate and "which you do not write" in generate
    plan = read("prompts/example_plan.md")
    assert "three good examples are the minimum, and with fewer the tool is more likely to differ from what they expect" in plan
    assert "`bind <run> examples <paths…>`" in plan
    examples = read("prompts/examples.md")
    assert "byte for byte" in examples and "You write no code" in examples
    assert "**Contract, examples, then code**" in read("static/patterns.md")
    readiness = read("static/readiness.md")
    assert "| 28 | An engineered tool appears only at the `software` rating `engineered`" in readiness and "| 29 |" in readiness
    assert "`contract.json` differs from the design's contract" in read("prompts/package_review_rubric.md")


# -- the build loop (change 2026-11-builder-engineered-tools, Slice 3) ---------------------------------------


def test_each_engineered_tool_is_built_in_a_bounded_loop_reviewed_by_another_vendor(loaded):
    group = next(s for s in loaded.recipe.steps if s.id == "build_tools")
    assert group.depends_on == ["examples"] and group.foreach == "steps.generate.output.engineered_tools"
    assert (group.concurrency, group.max_iterations, group.repeat_from) == (1, 3, "implement")
    assert group.repeat_until == "group.steps.review.gates.passed" and group.foreach_if_source_skipped == "skip"
    implement, review = group.steps
    assert implement.independence.from_step == "examples" and implement.independence.level == "different_vendor"
    assert implement.protect.paths == ["recipes/drafts/**/tools/*/examples/**"] and implement.protect.on_violation == "fail"
    assert [g.run for g in implement.gates if g.type == "script"] == [
        "baton tools test recipes/drafts/{{ run.slug }} --tool {{ item.tool }} --repeat 2 --require-examples",
        "baton recipe check recipes/drafts/{{ run.slug }} --ledger recipes/drafts/{{ run.slug }}.ledger.json"]
    assert review.independence.from_step == "implement" and review.workspace == "read"
    assert {i.name: i.from_ for i in review.inputs}["rubric"] == "static.tool_review_rubric.md"
    for a in APPROACHES:
        for sw in SOFTWARE:
            plan = at(loaded, a, sw)
            assert plan["build_tools/implement"].included == plan["build_tools/review"].included == (sw == "engineered")
    accept = next(s for s in loaded.recipe.steps if s.id == "accept")
    assert accept.depends_on == ["generate", "examples", "build_tools"]
    assert {i.name: (i.from_, i.required) for i in accept.inputs}["tools"] == ("steps.build_tools.outputs", False)


def test_generate_lists_the_tools_to_build_and_the_prompts_carry_the_loop_rules():
    gen = schema_of("generate_out")
    base = {"commit_sha": "abc1234", "package_path": "p", "ledger_path": "l", "summary": "s"}
    assert gen.is_valid({**base, "engineered_tools": [{"tool": "count_plants", "title": "Count"}]})
    assert not gen.is_valid({**base, "engineered_tools": [{"tool": "Count Plants", "title": "Count"}]})
    read = lambda rel: " ".join((BUILDER / rel).read_text(encoding="utf-8").split())  # noqa: E731
    generate = read("prompts/generate.md")
    assert "`engineered_tools`" in generate and "copy each tool the design marks `unchanged` exactly" in generate
    assert "remove that tool's folder and step" in generate
    assert "give `base`: `unchanged`" in read("prompts/design.md")
    implement = read("prompts/implement.md")
    assert "You may not change them" in implement and "`uv pip compile --generate-hashes`" in implement
    assert "never by recognising the example" in implement and "return `blocked`" in implement
    rubric = read("static/tool_review_rubric.md")
    assert "by recognising that example" in rubric and "a package the contract does not name" in rubric
    assert "`tools`" in read("prompts/accept.md")
