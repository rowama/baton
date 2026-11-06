## 6. Worker Profiles and Execution

### 6.1 Profiles (`~/.baton/workers.yaml`, overridable by `.baton/workers.local.yaml`)

```yaml
openai-api-strong:
  adapter: litellm_api
  creator: openai                      # who made the model: different_vendor
  model_id: openai/…                   # the model's identity on every route: different_model
  provider: openai                     # the access provider
  model: "openai/…"                    # what the adapter passes on [VERIFY current model strings]
  capabilities: [structured_output, long_form_writing, technical_reasoning, tool_use]
  tier: strong
  context_tokens: 200000
  auth: { mode: api_key, env: { OPENAI_API_KEY: "secret:openai_main" } }

codex-sub:
  adapter: codex
  creator: openai                      # no model_id: the CLI's default model is a mutable alias
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }            # the CLI's stored subscription login
  env_deny: [OPENAI_API_KEY, CODEX_API_KEY]   # a stray key could switch billing to the API
  executable: codex                    # the preset's default
  path: { search: [nvm] }
  # args omitted: the codex preset's defaults (§6.3); args.write / args.read / args.none override per mode

claude-code-sub:
  adapter: claude_code
  creator: anthropic
  capabilities: [structured_output, tool_use, file_write, shell, code_exec, repo_workspace, workspace_read, loopback_network, long_form_writing, technical_reasoning]
  tier: strong
  context_tokens: 200000
  auth: { mode: cli_login }
  env_deny: [ANTHROPIC_API_KEY]
  executable: claude
  path: { search: [nvm] }
  args: { write: ["--permission-mode", "bypassPermissions"] }   # the preset's default; shown as an example

owner:
  adapter: manual
  creator: human                       # a person's identity is human/<person>
  person: owner
  capabilities: [human_judgment, long_form_writing, vision, file_write]
  tier: strong
```

| Field | Notes |
|---|---|
| `creator` | Who made the model (`human` for people). Required. `vendor`, its name before, is still read (giving both, differing, is a load error). Compared by `different_vendor` (§8.4) |
| `model_id` | The model's canonical identity, `<creator>/<name>` in lower case, the same on every route (direct API, OpenRouter, a harness). Revisions are part of it when the creator distinguishes them; fine-tunes and quantizations take their base model's id; a mutable alias (a harness's default model, `latest`) or a route whose underlying model is unknown has none. Absent means **unknown**, and nothing is inferred from `model`. A `manual` profile's identity is `human/<person>`. Compared by `different_model` (§8.4) |
| `provider` | The access provider (`openai`, `openrouter`, `local`…). Route only: never used for independence |
| `model` | The provider- or harness-specific invocation identifier the adapter passes on (§6.3) |
| `resource` | The machine resource the profile uses |
| `auth.mode` | `api_key` (resolved secrets injected) \| `cli_login` (CLI's stored credentials) \| `none` |
| `env_mode` | `clean` (default for `api_key`) \| `allowlist` (default for `cli_login`; passes `HOME`, `USERPROFILE`, `APPDATA`, `LOCALAPPDATA`, `LANG`, `TERM` plus `env_allow`) \| `inherit` (escape hatch). `env_deny` is always applied last. |
| `auth.config_home` | Relocated CLI config dir so several logins coexist: `CLAUDE_CONFIG_DIR` for `claude_code`, `CODEX_HOME` for `codex` (both seen in the installed CLIs; switching logins with them is untested) |
| `executable`, `path.search`, `path.prepend` | Harness CLI resolution (§6.2) |
| `args.write` / `args.read` / `args.none` | Adapter args per workspace mode (permission and sandbox modes). Each replaces the preset's built-in default for that mode only (§6.3) |
| `isolation` | `none` \| `user` \| `container` |
| `capabilities` | Must be **true on this machine** (e.g. a sandbox that cannot bind localhost must not claim `loopback_network`) |
| `env_deny` | Exact names or `fnmatch` patterns (`*_API_KEY`); removes a name whatever put it there (inherit, `env_allow`, `auth.env`) |
| `options` | Non-secret adapter options (`litellm_api`: keyword arguments for the completion call, e.g. `base_url`, `temperature`) |
| secrets | `secret:<name>`, allowed only in `auth.env`; resolved at spawn time from the variable `BATON_SECRET_<NAME>` (upper-cased, other characters `_`), then the OS keyring (service `baton`; needs the optional `keyring` package), then the file `~/.baton/secrets/<name>`. A missing secret refuses the dispatch as `configuration`, naming all three places. Never written to packets, events or logs; resolved values are redacted from anything the runtime records |

Decision: [0075](../decisions/0075-model-identity-separate-from-route.md). Identity (`creator`, `model_id`) and route (`provider`, `model`, `adapter`, `resource`) are separate: the same model reached directly and through OpenRouter has one identity and two routes. A profile's hash (`worker_profile_sha256`, §7.1) still names the creator `vendor`, so profiles written before the rename keep their hashes.

CLI logins are usually files under the home directory; some platforms use an OS keychain that needs the user's session **[VERIFY]**. `doctor` (§13.4) proves each profile works on each machine.

### 6.2 Environment and PATH

`profiles.build_env(profile)`: start empty (`clean` / `allowlist`) or from the parent (`inherit`); copy allowed variables; build `PATH`; inject resolved secrets for `api_key`; set the config-home variable if any; **remove `env_deny` last**; add `BATON_PACKET_DIR`, `BATON_RESULT_DIR`, `BATON_WORKSPACE` (the last only for workspace steps). Only variable **names** are logged: `dispatched` records the env mode, the names present, the names denied, the names holding secrets and the resolved executable, plus the profile's declared `auth_mode` and the step's `workspace_mode`. On Windows, `SYSTEMROOT`, `WINDIR`, `COMSPEC`, `PATHEXT`, `TEMP` and `TMP` are always passed, since a child process cannot start without them **[VERIFY]**.

**PATH resolution** is explicit because version-managed CLIs (e.g. Node via nvm) are not on PATH in non-login shells:
1. Absolute `executable` → use it.
2. Found on the base PATH (`path.prepend` + minimal system PATH; `path.prepend` + the parent's PATH under `inherit`) → use it.
3. Each `path.search` source (`~` is the user's home, `HOME`/`USERPROFILE`, never the Baton home) (`nvm` → `$NVM_DIR/versions/node/*/bin`, `~/.nvm/versions/node/*/bin`, newest version first by numeric order, and `$NVM_HOME/v*` for nvm-windows **[VERIFY]**; `pyenv` → `$PYENV_ROOT/versions/*/bin`, `~/.pyenv/versions/*/bin`; `asdf` → `$ASDF_DATA_DIR/shims` or `~/.asdf/shims`; explicit dirs, `~` allowed) → prepend the first dir that has it. Any other source name is a profile load error.
4. Otherwise fail with `executable_not_found` (a **platform** failure, §8.8), listing every place searched (a source whose root does not exist is listed as its pattern).

A location found through a `path.search` source is recorded once as an observed platform fact (§12.3).

### 6.3 Adapters

```python
class WorkerAdapter(Protocol):
    name: str
    def command(self, profile, packet_dir, result_dir, workspace, mode) -> list[str]: ...
    def postprocess(self, profile, packet_dir, result_dir, proc_result) -> None: ...
    failure_signals: list[dict]          # patterns for classification (§8.8)
```

- **`litellm_api`**: runs `python -m baton.worker_runner` as the child (installed with the optional extra `baton[api]`). It builds messages from `INSTRUCTIONS.md` plus the text of every input not already inlined there, requests structured output where `litellm` reports support **[VERIFY per model]** (otherwise the reply schema goes in the prompt), and writes artifacts and `result.json` itself. The model replies with one JSON object: `status`, `output`, `artifacts` (text by declared name), `notes`, `questions_for_human`; a reply that is not a JSON object is a `failed` result (the step's problem, retried). **Inputs too large to inline are a hard error (§18 #1):** a non-UTF-8 input, or messages over `context_tokens × 2` bytes (roughly half the window; 256 KiB when `context_tokens` is not declared). The runtime checks this when dispatching, before anything is recorded, and refuses with a hint to choose a worker that reads files. Failures that are not the step's (authentication, network or provider errors, an unknown model, `litellm` missing) write no result; the child prints one line `baton-worker: failure=<class> code=<code> message=<redacted text>` and exits non-zero.
- **`subprocess_harness`** with presets **`claude_code`** (`claude -p <prompt> <args>`) and **`codex`** (`codex exec <args> --skip-git-repo-check --color never <prompt>`); flags checked against `claude` 2.1.316 and `codex-cli` 0.166.0. Prompt: "Read <packet>/INSTRUCTIONS.md and follow it exactly; write outputs to <result>/ …". `cwd` is the attempt directory for `workspace: none`, the project root for `read` and `write`. `executable` defaults to `claude` / `codex`; `model` is passed as `--model`. The CLI uses its stored login (`auth.mode: cli_login`, env `allowlist`) or an injected key (`api_key`); `auth.mode: none` is a configuration error.
  - **Built-in args per mode** (a profile's `args.<mode>` replaces one mode's default): `claude_code` write `--permission-mode bypassPermissions`, read and none `--permission-mode acceptEdits`; `codex` `--sandbox workspace-write` for every mode.
  - **Read and none steps are enforced by the runtime, not by flags.** The attempt's `result/` lies inside the project, so every mode must allow some writes and no CLI flag confines them to `result/`. For workers that can touch files (harness and `command` adapters), the runtime snapshots the working tree (HEAD, plus every changed or untracked path with its content hash, excluding the attempt directory; ignored files are not seen) before and after the worker runs. Any difference fails the implicit `workspace` gate and **escalates** the step (`workspace_modified`, listing the paths). HEAD moving only through Baton's own checkpoint commits (`baton(…): …` subjects, descending from the earlier HEAD; this run's or another's) is not a difference (found in Phase 14: consulting an expert about a just-completed run releases its lease again, and that checkpoint was blamed on the expert). The runtime never reverts the change; the owner inspects it. Write steps are not checked here (protected paths, §9.4, are). The snapshot's `git status` uses the repository's own line-ending settings, not `core.autocrlf=false` (found on Windows CI in Phase 16: files the owner's git committed with `autocrlf=true` are CRLF in the tree and LF in the index, and a forced override reported them modified only when git happened to re-hash them, so two snapshots of an untouched tree could differ); the hashes are of the raw bytes either way.
  - **Failure signals**: lines such as "Not logged in" or "Invalid API key" classify an exit without a result as `platform` / `auth_failed`.
- **`command`**: a configured command line with placeholders (`{prompt_file}`, `{packet}`, `{result}`, `{workspace}`), for other tools or for relaying to another agent. It is split like a POSIX shell would split it (no shell runs it; on Windows a backslash is an ordinary character, so `C:\tools\x.exe` stays intact); placeholders are substituted per word with POSIX-form paths (`{workspace}` is empty for `none` steps); the first word is the executable, resolved per §6.2.
- **`manual`**: prints the packet path and waits for `submit`. Used for humans and physical-world work.

Adapters never interpret results; intake does.

### 6.4 Worker setup

Writing profiles by hand needs knowledge that is not the owner's: model strings, capabilities, which adapter reaches which model. Three parts keep that work out of the owner's way, each with its own job (Decision: [0074](../decisions/0074-worker-research-and-resources-separate.md)): maintainers research models into shared data; the worker resource manager turns that data, plus what this machine has and what the owner declares, into profiles; `init` and `doctor` only confirm the machine is ready.

**Known-workers data** (`defaults/known-workers.yaml`, `baton-known-workers/1`; Decision: [0080](../decisions/0080-known-workers-format.md)) ships with the runtime, read-only, beside the adapters (`known_workers.py` validates it):

| Section | Holds |
|---|---|
| `machine_dependent` | Capabilities never listed in this data, because they depend on the machine (`loopback_network`): a profile gets one only from the owner's declaration or a probe (Decision: [0082](../decisions/0082-machine-dependent-capabilities.md)) |
| `models` | Keyed by `model_id` (§6.1): `creator`, intrinsic `capabilities`, `tier`, `context_tokens`, `category` (`llm`, `vision`, `transcription`…), `sources` (`url`, `retrieved`), `researched`, `retired` |
| `providers` | How access is obtained: `kind` `direct_api` \| `intermediary` \| `harness` \| `local`, with sources |
| `routes` | One way to run a model: `model_id` (or, for a mutable alias, `alias: true` and a `creator`), `provider`, `adapter`, `invocation` (the profile's `model`; empty only for a harness's default model), `supported`, the capabilities the route adds (a harness's tools), `tier`/`context_tokens` for an alias route, `sources`, and `verified` (`date`, `tool`, `version`) only for an actual live check |

Research claims and live checks are separate fields, so an unverified finding is never shown as tested. Research may cover models no adapter can run yet: such a route is `supported: false` and never becomes a profile. Validation checks the schema, the capability and tier vocabulary, that a supported route names an existing adapter, that every route's model and provider exist, that a `model_id` starts with its creator, that machine-dependent capabilities are absent, provenance on every model, and duplicate routes. Vendors and models here are profile data, like the adapters; recipes stay model-neutral and their lint is unchanged (§5.3).

**Research** (Decision: [0083](../decisions/0083-researcher-dispatches-through-a-profile.md)) is for maintainers, in the source checkout only: `python tools/worker-research/research.py --profile <name>` runs the one-step `worker-research` recipe in a scratch project, dispatched to a profile on the maintainer's machine (`web_access`, `file_write`, `structured_output`, `technical_reasoning`). The worker covers the landscape systematically (frontier and alternative creators, open-weight models, intermediaries, distribution hubs and local runtimes, every category that can do a bounded job on its own) and returns the proposed file plus a report of its inclusion criteria, coverage and coverage gaps. The script validates the proposal and refuses one that touches `verified`; a valid one replaces `defaults/known-workers.yaml` for review with `git diff`, and the report goes to `tools/worker-research/reports/<date>.md`. The wheel ships `defaults/` and nothing from `tools/` (a test builds it).

