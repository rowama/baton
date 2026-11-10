---
id: 2026-11-model-listings
title: "Every model a connected provider offers can become a worker, with its price, and free or cheap capable models are found and preferred"
status: done
level: major
decisions: ["0109", "0110", "0111", "0112", "0113", "0114", "0115", "0116", "0117", "0118", "0119", "0120"]
touches: [design/workers.md, design/runtime.md, design/director-interface.md, principles.md]   # §6.1, §6.4, §8.4, §13.1, §13.4, §2
---

# Every model a connected provider offers can become a worker, with its price, and free or cheap capable models are found and preferred

> **Accepted by the owner 2026-11-10 (Request approved; all 11 suggested answers accepted as decisions 0109–0119).** Proposed, 2026-11-10; extended the same day (owner) with a provider directory and an OpenAI-compatible provider kind, so switching providers is a choice, not a research run.** Request only. Design waits for the owner's answers to the open questions and approval of the Request (level major). Companion change: [2026-11-setup-ui](2026-11-setup-ui.md), which gives the owner a page to manage what this change finds; this change is useful without it (CLI and Director), and it is a prerequisite of it.

## Request

### Problem

Today the only models Baton can route to are the routes in the shipped known-workers data (§6.4). That file is written by a maintainer-run research step, so it is a curated shortlist. The 2026-11-06 research report's criteria were the flagship plus one cheaper tier per creator, for a fixed list of creators. As a result, OpenRouter, which offers several hundred models, contributes 10 routes. They are in-scope models that OpenRouter also serves, plus `openrouter/auto`. That report also says the run could not enumerate OpenRouter's catalog: its `/api/v1/models` read came back as a 10-entry, odd-shaped response. The 2026-11-08 run carried OpenRouter over unchanged, without the LiteLLM model map (not installed in that run).

Providers are limited the same way. The `providers:` section of that file lists eight API providers and two CLI harnesses. An owner can declare any other provider, but `resources.declare` then warns that "no known routes reach provider …; nothing will be generated for it". So an owner who moves from OpenRouter to another intermediary, such as Chutes or Requesty, gets no workers at all until a maintainer researches it and a new Baton ships.

So an owner with an OpenRouter key, or a Groq, Gemini or DeepSeek key, gets only what the maintainer happened to research. The free and cheap models that make Baton affordable for laypeople and small projects are almost entirely missing. The only way to add one is to write a profile by hand, which the owner rules out: it is friction that does not pay for itself (§1.1 #2).

The facts needed are already published in machine-readable form, and none of them needs an agent to find:

- **OpenRouter's public models API.** `GET https://openrouter.ai/api/v1/models` needs no key and was fetched on 2026-11-10. It returns, per model:
  - `id`, `canonical_slug`, `hugging_face_id`;
  - `context_length`;
  - `pricing` (`prompt`, `completion`, and more);
  - `architecture.input_modalities` / `output_modalities`;
  - `supported_parameters` (`tools`, `response_format`, `structured_outputs`, …);
  - `top_provider`, `knowledge_cutoff`, `expiration_date`, and on some entries `benchmarks`.

  Free variants end in `:free`.
- **OpenRouter's per-account listing.** `GET /api/v1/models/user` needs the key and lists the models that this account's provider preferences, privacy settings and guardrails allow ([OpenRouter API reference](https://openrouter.ai/docs/api/api-reference/models/list-models-filtered-by-user-provider-preferences-privacy-settings-and-guardrails)).
- **OpenRouter's key endpoint.** `GET /api/v1/key` returns credit limit, remaining credit, usage and `free_model_daily_requests` (`used`, `limit`, `remaining`). Free models are limited to 20 requests/minute and 50/day, or 1,000/day once 10 credits have been bought ([OpenRouter limits](https://openrouter.ai/docs/api/reference/limits)).
- **Direct providers' model lists.** OpenAI, Gemini, xAI, Anthropic, Fireworks, Bedrock, Vertex AI and others are listed by LiteLLM's model discovery (`check_provider_endpoint`). It reaches OpenRouter through its per-user endpoint and returns `openrouter/<vendor>/<model>` ids ([LiteLLM model discovery](https://docs.litellm.ai/docs/proxy/model_discovery)) **[VERIFY: the library-level call Baton would use, outside the proxy]**.
- **LiteLLM's model map** (`litellm.model_cost`). It holds price, context and `supports_*` flags for every model LiteLLM knows. It is already used as the `catalog` capability basis (Decision: [0088](../decisions/0088-capability-basis.md)).
- **models.dev.** An open-source database of models across providers with cost, context and output limits, tool-call, structured-output and reasoning flags, open-weights status, and knowledge and release dates ([models.dev](https://models.dev)). Hermes reads pricing and context from it **[VERIFY: its API and licence before depending on it]**.

**How Hermes does it** (researched 2026-11-10):

- `hermes setup` and `hermes model` are interactive pickers over about 40 providers. Subscriptions log in by OAuth or device code, other providers by API key ([quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)).
- The model list is a curated manifest of ids hosted with the docs: 74 for OpenRouter and 58 for Nous Portal in the 2026-10-26 manifest ([model-catalog.json](https://nousresearch.github.io/hermes-agent/docs/api/model-catalog.json)).
- Hermes caches the manifest (20-minute default) and falls back to a snapshot bundled with the CLI. Pricing and context are not in the manifest; they come live from provider `/v1/models` APIs and models.dev ([model catalog reference](https://hermes-agent.nousresearch.com/docs/reference/model-catalog)).
- Browsing all of OpenRouter, with a free-only filter, is a community plugin ([OR Picker](https://hermes-agent.nousresearch.com/docs/plugins/openrouter-picker)).

Hermes only has to pick one model for one chat. Baton routes each step by capability, tier and independence, so it needs more per model than a picker does. Most of that comes from the same deterministic data; only the judgment part (tier, `technical_reasoning`, `long_form_writing`) does not.

### What changes, in outline (not yet a Design)

1. **Listings are fetched, not researched.**
   - For each connected provider that has a listing source, Baton reads the provider's model list deterministically: on `workers setup`, on `workers refresh` (new), and on demand from the setup page.
   - The listing is cached machine-locally with its fetch date and source.
   - Each listed model becomes a candidate route. Its `context_tokens`, price and catalog-basis capabilities come straight from the listing fields (`tools` → `tool_use`, `response_format`/`structured_outputs` → `structured_output`, image input → `vision`), each with `capability_basis: catalog` naming the field.
   - No agent is involved, so it cannot miss or invent a model.
2. **Research becomes knowledge about models, applied to every route.**
   - Researched entries keep what only judgment can give: `tier`, the judgment capabilities, and the `model_id` identity for each listing id.
   - A listed model whose identity matches a researched model takes that knowledge, whichever provider lists it. This is the identity/route split of Decision [0075](../decisions/0075-model-identity-separate-from-route.md), now carried through to listings.
   - Research's scope gains a target: the free and cheap models that appear in listings and are capable enough to be worth judging.
3. **Unjudged models are usable, conservatively.**
   - A listed model with no researched entry gets only its catalog-basis capabilities and a default tier (open question 2).
   - It is eligible for steps that need nothing more, which is typically extraction, formatting and structured summarizing.
   - The owner, on the setup page or by asking the Director, can ask Baton to assess selected models. That is a research dispatch scoped to those models, through the owner's own workers, writing a machine-local overlay (open question 3).
4. **Price is a profile fact and a routing preference.**
   - Profiles carry the route's price (per million input and output tokens, or `free`, or `subscription` for harness routes) and its source and date.
   - A new ordering preference ranks the eligible set cheapest first. It never makes an ineligible profile eligible (§8.4 step 4 unchanged in kind).
   - The run's record shows the price at dispatch, so cost is visible after the fact.
5. **Free-tier limits are respected.**
   - A `:free` route's quota is known from the provider's key endpoint where one exists.
   - Exhausting it is a classified platform condition (open question 6) that re-routes the step to the next eligible worker.
   - `doctor` and `workers status` show the remaining quota.
6. **Providers come from a directory, researched broadly and separately from models.**
   - Provider facts are few and stable: display name, kind, base URL, how the key is passed (the variable LiteLLM reads, or a header), the API style it speaks, where its model list lives, whether it has a key-info or quota endpoint, and where to get a key (sign-up URL).
   - They are much cheaper to research than per-model judgments, so the directory can cover dozens of providers. Hermes ships about 40 ([Hermes quickstart](https://hermes-agent.nousresearch.com/docs/getting-started/quickstart)).
   - The directory is the existing `providers:` section of the known-workers data, extended with these fields. Research proposes provider entries the way it proposes models, with sources, and the validator checks them.
   - A provider in the directory needs no researched models: its models come from its listing (point 1).
7. **Any OpenAI-compatible endpoint is a provider, even one not in the directory.**
   - Many intermediaries and local runtimes speak the OpenAI API, including a model list at `GET <base_url>/models`.
   - A new provider kind, `openai_compatible`, needs only a base URL and a key (or no key, for a local runtime). Baton reads the listing from the base URL and dispatches through LiteLLM's OpenAI-compatible route with that base URL **[VERIFY: the prefix and `api_base` handling in the installed LiteLLM]**.
   - Directory entries for OpenAI-compatible providers use the same kind, with their base URL filled in, so the generic and the directory path are one mechanism.
   - What an OpenAI-style listing does not say (price, tool support on some providers) stays unknown, so those models get only what the listing shows, under point 3's defaults.
8. **No hand-written profiles anywhere in the path.** Connecting a provider (a key, or a CLI login) is the owner's only input. Listings, profiles, prices and quotas follow from it.

### How it feels to the owner

*Switching from OpenRouter to Chutes,* on the setup page ([2026-11-setup-ui](2026-11-setup-ui.md)) or by asking the Director:

1. The owner opens "Add an account" and picks Chutes from the list of providers. If Chutes were not listed, they would pick "Custom endpoint" and paste the address from Chutes' documentation instead.
2. The page links to where Chutes issues keys. The owner pastes the key.
3. Baton checks the key, fetches Chutes' model list and generates workers:
   - models research already knows (the same model also reached through OpenRouter, say) arrive with their tier and judgment capabilities;
   - the rest arrive with what the listing shows and the conservative defaults, and can be assessed later.
4. The models page now shows Chutes' models beside OpenRouter's, each with its price where Chutes publishes one.
5. Turning OpenRouter off is one switch. Its workers stay recorded, only routing stops using them, and turning it back on restores them.

At no point does the owner edit a file, wait for a Baton release or run research. From the CLI, the same flow is:
- `baton workers declare chutes-main --provider chutes --credential secret:chutes_main`, or `--provider openai_compatible --base-url <url>` for a custom endpoint;
- then `baton workers setup`.

### Acceptance criteria (draft)

1. With an OpenRouter credential declared and nothing else, `baton workers setup` generates a profile for every OpenRouter text model that the listing shows supporting `response_format` or `structured_outputs` (the `litellm_api` adapter's reply contract, §6.3). It does this without editing any file, and `workers status` reports the count and the listing's fetch date.
2. Each generated listing profile has `model`, `context_tokens` and price from the listing, and catalog-basis capabilities that each cite the listing field. It has a researched `tier` and judgment capabilities only when its identity matches a researched model; otherwise it has the default tier.
3. The same model listed by two providers has one `model_id` and two routes; independence (§8.4) treats them as the same model.
4. With the cheapest-first preference on, a step whose eligible set contains a free and a paid route dispatches to the free one. The `worker_selected` event records the price.
5. When a free route's daily quota is exhausted, the step is re-routed to the next eligible worker without counting an attempt, and `workers status` shows the quota and when it resets.
6. A listing fetch that fails (network, auth, malformed response) changes no generated profile and keeps the last good cache. The failure is reported in plain words and recorded as a diagnostic, never a crash.
7. An upgraded listing (models added, removed, repriced) is applied only by `workers setup`/`refresh`, under the existing refresh rules: removed models are flagged, not deleted; edited profiles are never touched.
8. Recipes are unchanged and the neutrality lint is unchanged: vendors and prices live only in profiles and machine data (§0 rule 4).
9. A listing never adds a capability that needs judgment, and never marks anything `verified`.
10. Declaring a provider from the directory that has no researched models, with a working key, generates profiles from its listing. Nothing else is needed.
11. Declaring `openai_compatible` with a base URL and key (tested against a local fake server speaking the OpenAI API) generates profiles from `<base_url>/models` and dispatches a step through it.
12. Turning a provider off excludes all its profiles from routing without deleting them, and turning it on restores them unchanged.

### Open questions (each with a suggested answer)

1. **Which listing sources in the first version?** *Suggest:* OpenRouter (public plus per-account) first; it alone covers most free and cheap models. Then Groq, Gemini, DeepSeek, Mistral and xAI through the same mechanism, using LiteLLM's model map for metadata where the provider's own list is bare. models.dev only after its licence and API are checked.
2. **Default tier for an unjudged listed model.** *Suggest:* `basic`, with no judgment capabilities. A step requiring `technical_reasoning` or a `standard`/`strong` tier then never goes to an unassessed model, which is safe. Assessment (open question 3) lifts it. *Alternative:* derive a tier from listing `benchmarks` where present, with basis `catalog`. That is more automatic but rests on a field that is not on every entry and whose meaning OpenRouter defines.
3. **Owner-run assessment.** Should research run on the owner's machine, scoped to chosen models and writing a machine-local overlay (`~/.baton/known-workers.local.yaml`)? Today research is maintainer-only (Decision: [0083](../decisions/0083-researcher-dispatches-through-a-profile.md)). *Suggest:* yes. The overlay can never touch `verified`, follows the same validator, and an owner's overlay can be offered upstream as a candidate change to the shipped data.
4. **Model identity for listing ids.** OpenRouter's ids differ from Baton's (`anthropic/claude-opus-5.5` versus `anthropic/claude-opus-5-5`). *Suggest:*
   - identity comes from a researched route's `invocation` when one matches;
   - otherwise from the listing's `canonical_slug`, lower-cased, as `<creator>/<name>`, with `alias: true` when the listing says it is an alias (`alias_target`) or a router (`openrouter/auto`);
   - otherwise unknown.

   Unknown is never treated as independent (Decision: [0076](../decisions/0076-unknown-identity-not-independent.md)).
5. **Filtering the listing.** Hundreds of profiles is noise in eligibility lists and `doctor`. *Suggest:* generate profiles only for text models meeting the adapter's contract, and show all of them on the setup page. Routing still considers them all, but `workers status` summarises them by provider (counts, free count, cheapest per tier) rather than listing each one. The owner can hide providers or models from routing (an `exclude` preference) without deleting anything.
6. **Free-quota exhaustion.** Make it a classified platform condition (`quota_exhausted`) that re-routes without counting an attempt, like `capability_absent` (Decision: [0086](../decisions/0086-capability-absent-reroutes.md)). *Suggest:* yes, and cover subscription-CLI quota exhaustion the same way. That is the failover question left open in [2026-11-step-tool-harness](2026-11-step-tool-harness.md); suggest it moves here.
7. **Is price a concept?** Price is a profile field and a preference, not a new owner concept (§2). *Suggest:* no new concept, and record that in §2's worker-setup note.
8. **LiteLLM by default.** Every API route needs LiteLLM (`baton[api]`), and so does catalog data. The README's install command includes it, but the launcher's per-version installs add only the extras named in `~/.baton/launcher.yaml` (default: none). *Suggest:* make `api` part of the launcher's default extras, so a project-pinned runtime can always run API routes. The alternative is to make LiteLLM a core dependency. That is simpler for owners, but LiteLLM is a heavy dependency for a project that only uses CLI harnesses.
9. **Which providers go in the directory first?** *Suggest:* the intermediaries with free or cheap tiers (OpenRouter, Groq, Chutes, Requesty, Together, Fireworks, Cerebras, DeepInfra), the direct APIs already in the data, and the local runtimes (Ollama, LM Studio, vLLM) as `openai_compatible` entries. Each is a research entry with sources, refreshed on the maintainer's research runs.
10. **A local runtime as a provider.** Ollama and others on `localhost` bring the machine-dependent `loopback_network` question (Decision: [0082](../decisions/0082-machine-dependent-capabilities.md)) and no key. *Suggest:* allowed under `openai_compatible` with `credential` omitted. Whether the API adapter's child process can reach `localhost` on every platform is to be checked in Design.
11. **Providers whose API is not OpenAI-compatible.** Anthropic's own API and Bedrock, for example. *Suggest:* they stay directory entries with their LiteLLM provider prefix, as today; only their listing source differs (LiteLLM's model discovery, or the model map).

## Design

### Doc edits

- `design/workers.md` §6.4: listings (a cached, fetched list of the models a provider offers) become candidate routes beside researched routes; listing profiles carry `price`; the `providers` section gains directory fields and the `openai_compatible` kind; `workers refresh`; owner-run assessment overlay.
- `design/workers.md` §6.1: a profile's optional `price` field and the `exclude` preference.
- `design/runtime.md` §8.4, §8.8: the cheapest-first ordering preference, the price in `worker_selected`, and `quota_exhausted`.
- `design/director-interface.md` §13.1, §13.4: `workers refresh`, quota in `workers status` and `doctor`.
- `principles.md` §2: the worker-setup note says price and listings add no concept.

### Mechanism (slice 1)

- A listing is a JSON file `~/.baton/listings/<provider>.json` (`baton-listing/1`: `provider`, `source`, `fetched`, `models`). A failed fetch leaves the last good file.
- `listings.py` fetches OpenRouter's public `GET /api/v1/models` (injectable fetcher for tests) and turns each entry into a candidate: `id`, `canonical_slug`, `context_length`, price per million tokens (or `free`), and catalog-basis capabilities (`structured_output` from `response_format`/`structured_outputs`, `tool_use` from `tools`, `vision` from image input). Only text-output models with a structured-output parameter become profiles (0113).
- `resources.plan_profiles` also plans listing profiles for each declared resource whose provider has a listing and has no researched route for that id. Identity follows 0112, tier is `basic` (0110), the name is `<resource>-<slug of listing id>`.
- A listing profile's `price` is refreshable (like `capabilities`), never a binding.

### Decisions

0109–0119, all accepted 2026-11-10.

## Plan

### Listing profiles from OpenRouter

- **Outcome:** `workers refresh` caches OpenRouter's listing; `workers setup` generates profiles with price, context, catalog capabilities and `basic` tier (acceptance 1, 2, 6, 7).
- **Effort:** L

### Price preference, quota and exclusion

- **Outcome:** cheapest-first routing, price in `worker_selected`, `quota_exhausted` re-routing, `exclude` and provider on/off (acceptance 4, 5, 12).
- **Effort:** L

### The openai_compatible kind

- **Outcome:** a custom endpoint is a provider, proven against a local fake server (acceptance 11).
- **Effort:** M

### Directory fields and entries

- **Outcome:** providers carry directory fields; a directory provider with no researched models generates profiles from its listing (acceptance 10, 3).
- **Effort:** M

### Owner-run assessment and launcher extras

- **Outcome:** assessment overlay (0111); `api` in the launcher's default extras (0116).
- **Effort:** M

## Log

### Listing profiles from OpenRouter

- **Commit:** `2026-11-model-listings: Slice 1, listing profiles from OpenRouter`
- **Summary:** `listings.py` (fetch, `baton-listing/1` cache, candidates, identity), `WorkerProfile.price`, `resources._plan_listings` and `refresh_listings`, `baton workers refresh`. Edits §6.1, §6.4, §13.1. Tests `tests/test_listings.py`: candidates follow the adapter contract and cite fields; setup writes profiles with price, context, identity and `basic` tier and is idempotent; a researched route is not duplicated; a failed or malformed fetch keeps the last good cache; a repriced listing reaches a profile only through setup. Not yet done: per-account listing (`/models/user`), `workers status` summary by provider (0113), CLI-level test of `workers refresh`.
- **Review:** clean
- **Accepted:** pending

### Price preference, quota and exclusion

- **Commit:** `2026-11-model-listings: Slice 2, price preference and quota re-routing`
- **Summary:** `Preferences.cheapest_first` and `routing.price_rank`; `worker_selected.price`; `quota.py` (`~/.baton/quota.yaml`, reset at next UTC midnight) attached to profiles and excluded in routing; the API runner classifies `RateLimitError` as `platform`/`quota_exhausted`; `Engine._quota_exhausted` re-routes without counting the attempt and opens no incident. Exclusion already existed (`exclude` in preferences). Edits runtime.md §8.4, §8.8. Tests in `tests/test_listings.py` and an end-to-end rate-limit test in `tests/test_api_worker.py`. Not yet done: quota shown by `workers status` and `doctor` from the key endpoint (acceptance 5 in part), provider on/off switch (acceptance 12), subscription-CLI quota signals, `workers status` summary by provider.
- **Review:** clean
- **Accepted:** pending

### The openai_compatible kind

- **Commit:** `2026-11-model-listings: Slice 3, the openai_compatible kind`
- **Summary:** provider kind `openai_compatible` and a generic `openai_compatible` provider in the known-workers data; `listings.normalize_openai` and per-resource listing caches; `refresh_listings` reads `<base_url>/models`; listing planning dispatches through `openai/<id>` with the resource's `base_url`, `auth: none` for a keyless local runtime; `declare` requires `--base-url`. Edits workers.md §6.4. Tests in `tests/test_api_worker.py`: a local fake OpenAI server is listed, a profile generated and a step dispatched through it (real litellm child, acceptance 11); `declare` without a base URL is refused. Localhost reach checked on Linux only (Design noted the question, 0118). Not done: `workers declare --provider openai_compatible` help text.
- **Review:** clean
- **Accepted:** pending

### Directory fields and entries

- **Commit:** `2026-11-model-listings: Slice 4, the provider directory`
- **Summary:** `KnownProvider` gains `display_name`, `base_url`, `signup_url` (validator: `base_url` only on `openai_compatible`); a resource's `base_url` falls back to the directory's; `declare` needs a base URL from one or the other. Nine entries added to the known-workers data (Together, Fireworks, Cerebras, DeepInfra, Chutes, Requesty; Ollama, LM Studio, vLLM), endpoints and key pages checked 2026-11-10 by request (not by a research run, so no tier or price claims). Tests in `tests/test_listings.py`: a directory provider with only a credential generates profiles from its listing (acceptance 10); a keyless local runtime; the validator refusal. Acceptance 3 is covered by slice 1's identity tests (a listed id matching a researched route takes its `model_id`; a directory provider's models have unknown identity by 0118). Not done: the per-provider key-info/quota endpoint field and showing remaining quota.
- **Review:** clean
- **Accepted:** pending

### Owner-run assessment and launcher extras

- **Commit:** `2026-11-model-listings: Slice 5, assessed-model overlay and launcher extras`
- **Summary:** `known_workers.load_with_overlay` merges `~/.baton/known-workers.local.yaml` (models and routes only; never edits a shipped model; no `verified`; a basis for every capability; same validator), used by the resource manager. Listing profiles now take creator, tier and capabilities from a matching researched or assessed model (the 0112 knowledge flow that slice 1 left at `basic`). The launcher's default extras are `[api]`; an explicit list, even empty, replaces it (0116). Edits workers.md §6.4, versioning.md §14.1. Tests: an assessed model lifts its listing profiles and leaves the unassessed at `basic`; four overlay refusals; the launcher requirement string. The overlay-producing dispatch followed in the next slice.
- **Review:** clean
- **Accepted:** pending

### Owner-run assessment dispatch

- **Commit:** `2026-11-model-listings: Slice 6, baton workers assess`
- **Summary:** owner decision 2026-11-10 (record 0120): fetch the recipe pinned to the runtime's version, reuse the runtime's validator. `assess.py` (fetch at tag `v<version>` from `launcher.yaml`'s source, cached; wanted-model checks; scratch-project run through the owner's profile; validation by `known_workers.merge_overlay`, now the single overlay validator; atomic overlay write; report), recipe `tools/worker-research/assessment/` (not in the wheel), `baton workers assess` and `baton workers check-overlay`. Edits workers.md §6.4, layouts.md §4.4, director-interface.md §13.1. Tests `tests/test_assess.py` and a fake worker: pinned fetch and cache, refusal for a missing tag or non-git source, validator, end-to-end assess then setup lifts the profile, a refused draft writes nothing, only listed unjudged models accepted, the recipe lints.
- **Review:** clean
- **Accepted:** pending

### Account list, quota figures, summary and the provider switch

- **Commit:** `2026-11-model-listings: Slice 7, quota figures, provider summary and switch`
- **Summary:** closes the gaps earlier slices listed. `workers refresh` reads OpenRouter's per-account list when a key is declared (public list as a stated fallback) and caches the key endpoint's figures; `workers status` and `doctor` show them, dated, without network; `status` summarises listing profiles by resource (counts, free, cheapest per tier), marked by `generated.listing`; `WorkerResource.enabled` with `workers disable|enable` and a routing exclusion reason; `workers declare --provider` help names `openai_compatible`. **Deferred by the owner, 2026-11-10: subscription-CLI quota signals** (the Request's "subscription CLIs report what they can" item); route-level re-routing on `quota_exhausted` covers them when a worker reports it. Edits workers.md §6.4, director-interface.md §13.1. Tests in `tests/test_listings.py`: account list and figures; the public fallback; a failed key read keeps the last figures; the provider summary and readiness quota; the switch keeps workers recorded and routing skips them; the `workers refresh`, `disable` and `enable` commands (the CLI-level test slice 1 lacked). Repair: the full run of `8e1fe03` was red on the slow openai_compatible test, which compared the whole `refreshed` entry and so failed on the new `source` key; the test now checks provider and count (fix commit named below).
- **Review:** clean
- **Accepted:** pending
