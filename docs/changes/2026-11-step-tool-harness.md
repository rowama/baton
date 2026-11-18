---
id: 2026-11-step-tool-harness
title: "Baton runs a bounded tool loop for API workers, with only the tools a step requires"
status: in-progress
level: major
decisions: ["0168", "0075", "0076", "0084", "0085", "0086", "0088", "0114", "0154", "0166"]
touches: [design/workers.md, design/runtime.md, design/recipes.md, design/platform-and-security.md]
manual: [admin/accounts-and-costs.md, admin/network-and-security.md, admin/machine-settings.md, reference/commands.md, reference/diagnostics.md]
---

# Baton runs a bounded tool loop for API workers, with only the tools a step requires

## Request

### Problem

The `litellm_api` adapter's runner (`worker_runner.call_model`) makes one `litellm.completion` call and reads the reply. It offers the model no tools and runs no loop. So an API worker cannot search or read the web, or read files beyond what is inlined in its packet. A step that requires `web_access` or `workspace_read` can only go to a harness (Claude Code, Codex), which ties it to a CLI subscription and its quotas. For now web steps are steered to subscription CLIs (`2026-11-capability-confidence`, criterion 10).

LiteLLM does not run tools: the caller executes the model's tool calls and sends the results back in another `completion` call ([LiteLLM: function calling](https://docs.litellm.ai/docs/completion/function_call)). A small loop owned by Baton, offering only the tools a step's `requires` names, would let any API model with tool calling do those steps. This serves the owner's aim that cheap and free models be usable for real work, and that web search work without the owner opening a search API account.

The tools here are Baton's own, offered to a model inside one worker's attempt, in the sense agent software uses the word. A recipe's code that does a whole step with no model is a program (§5.9), not a tool (Decision [0166](../decisions/0166-tools-renamed-programs.md)).

### Acceptance criteria

1. **A loop in the runner.** When a step requires a tooling capability the runner provides, the `litellm_api` runner offers the model the matching tools, executes each call, returns its result, and calls the model again, until the model finishes or a limit is reached.
2. **Only what the step requires.** The runner offers:
   - `search` and `fetch` for `web_access`;
   - `list_files` and `read_file` for `workspace_read` on a `read` step, or for reading the packet's inputs;
   - always, `finish`, whose arguments are the step's reply (§6.3).
   No tool writes to the workspace, runs a command or executes code. A step requiring `shell`, `code_exec`, `repo_workspace` or `file_write` in the workspace is not given to the runner.
3. **Search without an account where possible.** `search` uses the model provider's own web search where LiteLLM reports `supports_web_search`, passing `web_search_options` ([LiteLLM: web search](https://docs.litellm.ai/docs/completion/web_search)). Otherwise it uses a search provider the owner has declared on the machine. Otherwise `web_access` is not offered by that profile. Baton never scrapes search engine result pages.
4. **Fetch is safe by construction.** `fetch` makes an HTTP(S) GET, extracts text, and refuses loopback, private and link-local addresses, other schemes, bodies over a size limit and redirects to any of these. It has a timeout.
5. **Reading stays in bounds.** `read_file` and `list_files` see only the packet's inputs, and for a `read` step the working tree, never `.git`, `.baton`, or anything outside the tree; each read has a size limit.
6. **The loop is bounded.** A step has a limit on tool calls (a recipe may set it; otherwise a default). Reaching it without `finish` is a `failed` result for the step, retried as any failure is, with the transcript kept. The step's effort band deadline (§8.7) still applies.
7. **Tool output is untrusted.** Results go back to the model marked as data from outside, never as instructions. The system message says so.
8. **Every call is recorded.** The attempt's log records each tool call (name, arguments, result size and hash, time taken) and keeps the transcript beside it. `record` and `trace` show the calls.
9. **The capability facts are Baton's.** A profile's `web_access` and `workspace_read` through the runner are facts about Baton's code and the machine (the model supports tool calling, LiteLLM's `supports_function_calling`, and a search backend exists), recorded `verified` with that basis rather than researched (Decisions [0084](../decisions/0084-capability-states.md), [0088](../decisions/0088-capability-basis.md)).
10. **No silent model switch.** One attempt uses one model throughout. Nothing inside the loop falls back to another model, so the recorded identity and independence checks hold (Decisions [0075](../decisions/0075-model-identity-separate-from-route.md), [0076](../decisions/0076-unknown-identity-not-independent.md)). Quota exhaustion re-routes the step as today (Decision [0114](../decisions/0114-quota-exhausted-reroutes.md)).
11. **Steps without tooling are unchanged.** A step requiring no tooling capability makes one call as today, byte for byte.
12. **Manual and design are current.**

### Open questions

All nine were answered as suggested (Decision [0168](../decisions/0168-step-tool-harness-details.md)); question 9 was raised when the first eight were put to the owner.

1. **An option of `litellm_api`, or a new adapter?** *Suggested:* part of `litellm_api`. *Rationale:* the same profiles, routes and identity; a new adapter would duplicate every API profile.
2. **Does `web_access` need both search and fetch?** *Suggested:* yes; a profile with fetch but no search backend does not offer `web_access`. *Rationale:* the capability means "can fetch / search the web" (§5.6), and research steps depend on finding sources, not only reading known ones.
3. **Which search providers may the owner declare?** *Suggested:* any that LiteLLM's web search interception supports ([LiteLLM: web search interception](https://docs.litellm.ai/docs/integrations/websearch_interception)), declared once per machine with `workers declare` and a `secret:` key, plus a self-hosted SearXNG with only a base URL. *Rationale:* no Baton code per provider; SearXNG gives a free route for an owner who runs one.
4. **How does the model finish?** *Suggested:* by calling `finish` with the reply as its arguments, on every route that has tools. *Rationale:* some providers do not combine tool calling with structured output in one call **[VERIFY per provider]**; a finish tool works the same everywhere, and its arguments are checked against the reply schema as today.
5. **Default tool-call limit?** *Suggested:* 40 per attempt; a recipe may set `tool_calls: <n>` on a step. *Rationale:* a guess, not a measured figure: enough for a research step to search a few times and read a dozen pages, small enough to stop a model that loops. To be revised from recorded use.
6. **May a step read the project and the web at once?** This is the real risk: a page can instruct the model to fetch a URL that carries the project's contents out. *Suggested:* allowed, but with both, `fetch` only opens URLs that appeared in a search result or in the step's inputs during this attempt. *Rationale:* research steps need both; limiting fetch to found or given URLs blocks the easy route out without forbidding the step. With provider-native search, the search runs on the provider's side, so the URLs it found are the citations the provider returns; a provider that returns none allows no fetch on such a step. How each provider returns citations is checked in Slice 2 **[VERIFY]**.
7. **Does the runner prefer itself over a harness?** *Suggested:* no new routing rule; the runner's profiles compete by tier and capability state like any other. *Rationale:* routing already prefers what fits; a special preference would surprise the owner and hide cost differences.
8. **Can a step offer one of its recipe's programs (§5.9) to the model as a tool?** *Suggested:* not in this change; recorded as a later possibility. *Rationale:* it would let a model call pinned, tested code mid-reasoning, which is valuable, but it mixes two designs that are each new.
9. **Provider search is billed per search.** Some providers charge for each web search apart from tokens. *Suggested:* each attempt records how many searches it made, and `doctor` and the setup page say when a profile's web access is billed per search; Baton does not estimate the charge. *Rationale:* the owner sees that a cost exists and how much the work used, without Baton keeping a price list for searches.

### Out of scope

- **Driving a browser:** [2026-11-browser-automation](2026-11-browser-automation.md), which builds on this loop.
- **Writing, running commands or executing code** in the runner. Those stay with harnesses; Baton does not become a coding agent.
- **A recipe's programs offered to a model** (open question 8).
- **Failover between workers on quota** (done: Decision 0114).

## Design

Approved by the owner with the Request, 2026-11-17.

### Shape

- **Which tools.** At dispatch the runtime computes, from the step's `requires` and workspace mode, the tools to offer, and writes them into the packet's manifest (`tools: [search, fetch, list_files, read_file]`). The runner offers exactly those plus `finish`. A step whose tooling needs include anything the runner cannot provide never routes to a `litellm_api` profile (the profile does not have the capability).
- **The loop** (`worker_runner.run`):
  1. Messages as today, with a system note that tool results are outside data and that the reply goes through `finish`.
  2. `completion(model, messages, tools=…)`; for a search through the provider, `web_search_options` instead of a `search` tool.
  3. For each tool call: run it, append the result as a `tool` message, log it.
  4. Stop on `finish` (its arguments are the reply, validated as today), on the limit (`failed`, `notes` say so), or on an error the runner classifies as today.
- **`search`** returns `[{title, url, snippet}]`, at most ten results. Through an owner-declared provider, the runner calls LiteLLM's search interface for that provider directly.
- **`fetch(url)`** resolves the host, refuses non-public addresses (also after each redirect, at most five), downloads at most 2 MiB, extracts readable text (HTML to text; plain and JSON as is; PDF and others refused in the first version) and returns at most 50,000 characters with the final URL.
- **`read_file(path)` / `list_files(dir)`**: paths start with `inputs/` (the packet's inputs) or, on a `read` step, `workspace/` (the working tree); normalized and checked to stay inside; `.git` and `.baton` refused; at most 1 MiB per read.
- **Records.** `tool_calls.jsonl` in the attempt folder (`{n, tool, args, bytes, sha256, ms, refused?}`), committed with the run; the transcript beside the attempt's machine-local log (`~/.baton/logs/<run>/<step_path>/attempt-<n>.transcript.json`), since it holds whole files and pages; `dispatched` gains `tools {runner, limit}`, and `result_submitted` gains `tool_calls: <count>`, `tool_calls_sha256` and (Slice 2) `searches: <count>`.
- **Capability facts.** `workers status` and routing compute, for each `litellm_api` profile, `workspace_read` (when the model supports tool calling) and `web_access` (when it also has a search backend: provider-native, or a declared provider) as `verified` with `basis: baton_runner`. `doctor` says which profiles gain web access and why the others do not, and which are billed per search; the setup page shows the same note on a model's web access.
- **Declared search.** `workers declare --search <provider> --credential secret:<NAME>` (or `--search searxng --base-url <url>`) writes the machine's search backend to `~/.baton/resources.yaml`.
- **Limits in numbers** (2 MiB, 50,000 characters, 1 MiB, ten results, five redirects) are starting values chosen for this draft, not from a source; each is a constant to tune from use.

### Doc edits

- `design/workers.md` §6.3 (`litellm_api` with the loop; its tools; `finish`), §6.4 (declared search backend; capability facts).
- `design/runtime.md` §8.2 (`tool_calls` on `result_submitted`), §8.4 (runner-provided capabilities in routing).
- `design/recipes.md` §5.6 (tooling capabilities may be provided by Baton's runner as well as by a harness), the `tool_calls` step key.
- `design/platform-and-security.md`: fetch restrictions, the read boundary, the combined read-and-web rule, untrusted output.

### Manual edits

- A new administrator topic, `admin/web-access.md`, on giving API models web access: provider search, declaring a search backend, SearXNG, and what a model may fetch. Added to `manual:` in Slice 3, when the file exists.
- `admin/accounts-and-costs.md`: provider search billed per search; the search count recorded per attempt.
- `admin/network-and-security.md`: what `fetch` refuses, the read boundary, the combined read-and-web rule.
- `admin/machine-settings.md`: the search backend in `~/.baton/resources.yaml`.
- `reference/commands.md`, `reference/diagnostics.md`: regenerated (`workers declare --search`, new codes).

### Decisions

- [0084](../decisions/0084-capability-states.md), [0088](../decisions/0088-capability-basis.md) (accepted): capability states and their basis.
- [0085](../decisions/0085-harness-tool-maps.md) (accepted): a step gets only the tooling it requires.
- [0075](../decisions/0075-model-identity-separate-from-route.md), [0076](../decisions/0076-unknown-identity-not-independent.md) (accepted): recorded identity; no silent switch.
- [0086](../decisions/0086-capability-absent-reroutes.md), [0114](../decisions/0114-quota-exhausted-reroutes.md) (accepted): re-routing on absent capability and exhausted quota.
- [0154](../decisions/0154-tool-steps.md), [0166](../decisions/0166-tools-renamed-programs.md) (accepted): a recipe's programs, which these tools are not.
- [0168](../decisions/0168-step-tool-harness-details.md) (accepted): the answers to the nine open questions, all as suggested.

## Plan

Slices as proposed; refined once the Request and Design are approved.

### Slice 1: the loop, reading and finish

- **Outcome:** an API worker on a `read` step can list and read files and finishes through `finish`; steps without tooling are unchanged.
- **Criteria:** the manifest's `tools`; the loop and its limit; `finish` validated against the reply schema; read boundary and size limit; records and transcript; `workspace_read` as a runner fact; the unchanged single-call path (its existing tests pass).
- **Effort:** M

### Slice 2: the web

- **Outcome:** an API model with provider search does a step requiring `web_access`.
- **Criteria:** provider-native search where supported; `fetch` and its refusals (private addresses, redirects, size, type); the combined read-and-web rule; `web_access` as a runner fact; `doctor` reporting; the recipe-builder's `research` step run on an API model in a scenario.
- **Effort:** L

### Slice 3: declared search and the manual

- **Outcome:** an owner whose models have no built-in search can declare a search backend once and give them web access.
- **Criteria:** `workers declare --search`; a declared provider through LiteLLM's interface; SearXNG by base URL; the manual topics.
- **Effort:** M

## Log

### Discussed and put on hold

- **Summary:** Drafted 2026-11-06 as a stub and put on hold until `2026-11-capability-confidence` and `2026-11-cli-model-routes` were done.
- **Owner decision:** 2026-11-06, discussion of web search for API workers.
- **Accepted:** No; on hold.

### Taken off hold and written out

- **Summary:** Both prerequisites are done, and quota failover, the stub's first open question, was settled by Decision 0114. The LiteLLM facts the stub cited were re-read on 2026-11-17 (tools are executed by the caller; `supports_function_calling`; `web_search_options` and `supports_web_search`; web search interception with Perplexity, Tavily, Exa, Brave, SearXNG and others). Request completed, eight open questions with suggested answers, Design and Plan written; the tools were named runner tools to keep them apart from recipe tools. No code changed.
- **Owner decision:** 2026-11-17, "take step-tool-harness off hold".
- **Accepted:** No; proposal only. Eight open questions await the owner.

### Back to plain "tools"

- **Summary:** With the recipe's tool renamed a program (Decision 0166, `2026-11-program-steps`), this change's tools keep the plain word, as agent software uses it; "runner tools" is dropped. To be built after `2026-11-program-steps`.
- **Owner decision:** 2026-11-17, "It seems to me that the 5.9 usage is the odd one out." (0166).
- **Accepted:** No; proposal only. Eight open questions await the owner.

### Open questions answered

- **Summary:** The eight open questions were put to the owner with their suggested answers, plus a ninth raised in doing so: provider web search is billed per search. Question 6 gained a note on provider-native search, where the found URLs are the provider's citations. The owner accepted all nine. Recorded as Decision 0168; the Request, Design and manual list now cite it. No code changed.
- **Owner decision:** 2026-11-17, "As suggested." (0168).
- **Accepted:** No; the Request and Design await the owner's approval.

### Request and Design approved

- **Summary:** The owner approved the Request and Design as updated with Decision 0168. Two facts are to be checked in Slice 2 before they are relied on: how each provider returns its native search's citations, and whether a provider accepts native search and function tools in one call. No code changed.
- **Owner decision:** 2026-11-17, "Agree. Proceed."
- **Accepted:** Yes.

### Slice 1: the loop, reading and finish

- **Summary:** `runner_tools.py` (new, standard library only) holds the rules (`provided`: `workspace_read` for a `litellm_api` profile whose model claims `tool_use`, not recorded absent; `offered`: the tools for the needed capabilities) and the tools (`ReadScope`: `list_files`, `read_file` over `inputs/` and, on a read step, `workspace/`). `worker_runner.py` loops when the manifest lists `tools`: tools plus `finish`, results marked as outside data, the step's `tool_calls` limit (default 40), two reminders for a reply in text, profile fallback options refused (`fallbacks_not_allowed`), `tool_calls.jsonl` in the attempt folder and the transcript in the machine-local log. `WorkerProfile` gains `claims()` and the runner-provided capabilities (attached in `Project.profiles`, never hashed; `verified`, `by: baton_runner`); an API profile never has `shell`, `file_write`, `code_exec`, `repo_workspace` or (for now) `web_access`. `routing` uses `claims()` and names the runner in its reasons; SME consultations do not route to a runner-provided capability yet (their packets carry no tools). `packet.py` writes `tools` and `tool_calls` only for API packets with tools; the step key `tool_calls` is new (a program step cannot set it). `engine.py` records `dispatched.tools {runner, limit}` and `result_submitted.tool_calls` / `tool_calls_sha256`; `record` lists the calls and `trace` the count; `workers status` shows the provided capability (`provided_by_runner`). Two details settled while building: tool paths carry a root name (`inputs/`, `workspace/`) so the inputs and the tree never collide, and the call list is committed with the attempt while the transcript stays machine-local. Design: §6.1, §6.3 (`workers.md`), §8.2, §8.4 (`runtime.md`), §5.6 (`recipes.md`), §15.2 (`platform-and-security.md`). Manual: `admin/network-and-security.md` (new heading *What an API model may read*), `admin/machine-settings.md`. Tests: `tests/test_runner_tools.py` (rules, hash unchanged, routing, packet keys, read boundary and limits, the loop, its limit, reminders, refusals, fallbacks, classified errors, the unchanged single call, `workers status`, and end to end with the real child and LiteLLM's offline `mock_tool_calls`).
- **Owner decision:** 2026-11-17, "Agree. Proceed."
- **Accepted:** Yes.
