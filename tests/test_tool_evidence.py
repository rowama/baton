"""Tool evidence read from a harness's event stream (§6.3; 0085)."""

from __future__ import annotations

import json

from baton.tool_evidence import scan

WEB = ["WebSearch", "WebFetch"]


def lines(*events) -> str:
    return "\n".join(json.dumps(e) for e in events) + "\n"


def use(id_, name):
    return {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": id_, "name": name, "input": {}}]}}


def result(id_, text, error=False):
    return {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": id_, "content": text, "is_error": error}]}}


def test_a_successful_claude_tool_call_is_a_use():
    text = lines({"type": "system", "subtype": "init"}, use("t1", "WebSearch"), result("t1", "results..."), {"type": "result", "is_error": False})
    assert scan(text, WEB) == ("used", "WebSearch call succeeded")


def test_a_denied_claude_tool_call_is_a_denial():
    text = lines(use("t1", "WebFetch"), result("t1", "Claude requested permissions to use WebFetch, but you haven't granted it yet.", error=True))
    assert scan(text, WEB)[0] == "denied"
    text = lines({"type": "result", "permission_denials": [{"tool_name": "WebSearch", "tool_use_id": "x"}]})
    assert scan(text, WEB) == ("denied", "WebSearch was denied or unavailable")


def test_a_tool_error_that_is_not_a_denial_says_nothing():
    text = lines(use("t1", "WebFetch"), result("t1", "HTTP 404 for the page", error=True))
    assert scan(text, WEB) == (None, "")


def test_other_tools_and_noise_say_nothing():
    text = "not json\n" + lines(use("t1", "Bash"), result("t1", "ok")) + "{broken\n"
    assert scan(text, WEB) == (None, "")
    assert scan("", WEB) == (None, "")


def test_codex_web_search_events_are_uses():
    text = lines({"type": "thread.started"}, {"type": "item.completed", "item": {"id": "i1", "type": "web_search", "query": "x"}})
    assert scan(text, ["web_search"]) == ("used", "web_search call succeeded")
    text = lines({"id": "1", "msg": {"type": "web_search_end", "query": "x"}})
    assert scan(text, ["web_search"])[0] == "used"
    text = lines({"type": "item.started", "item": {"id": "i1", "type": "web_search"}})
    assert scan(text, ["web_search"]) == (None, "")  # begun, never completed
