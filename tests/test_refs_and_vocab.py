from __future__ import annotations

import pytest

from baton import refs, vocab


@pytest.mark.parametrize(
    "raw,kind,step,name,path",
    [
        ("run.inputs.title", "run_input", None, "title", ()),
        ("steps.plan.output", "step_output", "plan", None, ()),
        ("steps.plan.output.slices.0.id", "step_output", "plan", None, ("slices", "0", "id")),
        ("steps.design.artifacts.design_doc", "step_artifact", "design", "design_doc", ()),
        ("steps.slices.outputs", "group_outputs", "slices", None, ()),
        ("item", "item", None, None, ()),
        ("item.effort", "item", None, None, ("effort",)),
        ("group.steps.implement.output", "sibling_output", "implement", None, ()),
        ("group.steps.implement.artifacts.diff", "sibling_artifact", "implement", "diff", ()),
        ("group.previous_iteration.findings", "previous_findings", None, None, ()),
        ("static.rubric.md", "static", None, "rubric.md", ()),
        ("human.approve_scope", "human", None, "approve_scope", ()),
        ("human_revision.design.design_doc", "human_revision", "design", "design_doc", ()),
        ("research.findings", "research", None, None, ()),
        ("platform.facts", "platform", None, None, ()),
    ],
)
def test_reference_grammar(raw, kind, step, name, path):
    ref = refs.parse(raw)
    assert (ref.kind, ref.step, ref.name, ref.path) == (kind, step, name, path)


@pytest.mark.parametrize("raw", ["", "steps", "steps.Plan.output", "steps.plan.outputz", "run.inputs", "group.foo", "memory.x"])
def test_reference_grammar_rejects(raw):
    with pytest.raises(refs.RefSyntaxError):
        refs.parse(raw)


def test_repeat_until_condition():
    assert refs.parse_condition("group.steps.a.gates.passed and group.steps.b.gates.passed") == ["a", "b"]
    with pytest.raises(refs.RefSyntaxError):
        refs.parse_condition("group.steps.a.gates.failed")


def test_vocabulary():
    v = vocab.load("baton-capabilities/1")
    assert "human_judgment" in v.capabilities
    assert v.tiers == ["basic", "standard", "strong"]
    assert v.find_vendor_string("Prefer GPT-5") == "gpt-"
    assert v.find_vendor_string("plain text") is None
    assert vocab.supported() == ["baton-capabilities/1"]
    with pytest.raises(vocab.UnknownVocabulary):
        vocab.load("baton-capabilities/2")
