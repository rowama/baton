---
id: reference.diagnostics
title: Diagnostic codes
audience: admin
summary: Every condition Baton records in ~/.baton/diag, and what it means.
order: 40
generated: true
---

## Here, now {#here-now}

Read them with `baton diag`. Each is something Baton worked around instead of failing; most are harmless once, and worth a look when they recur.

| Code | What happened |
|---|---|
| `accounts.check_failed` | Checking an account's key with its provider failed for a network or decoding reason. The page shows the reason without the key. |
| `cache.replay` | The cache of a run's record was out of step with its log and was rebuilt by replaying the log. Harmless; recurring means something edits the cache or the log. |
| `capability.version_check_skipped` | A helper's version could not be read, so its observed capability states were not reset after an upgrade. |
| `catalog.summaries_unavailable` | A recipe in the project would not load, so its summary was left out of the list offered to a part that wants the catalog. |
| `docs.record_unreadable` | A stored result could not be read when writing a step record; the record is left out. |
| `frame.profiles_unreadable` | Profiles could not be read while checking whether the work will need web search, so no advice about it was given. |
| `harness.version_probe_failed` | Running a coding assistant to read its version failed, so its version is unknown. |
| `harness.version_stat_failed` | A coding assistant's file could not be inspected, so its version is unknown. |
| `hooks.config_invalid` | `~/.baton/hooks.yaml` could not be loaded, so it counts as no wake path. |
| `incident.resolve_run_unreadable` | A run could not be read when resolving a platform incident, so the incident was not matched to it. |
| `known_workers.load_failed` | Baton's shipped known-workers data, or your overlay, failed validation. Run `baton workers check-overlay`. |
| `listings.fetch_failed` | A provider's model list could not be read; the last good list, if any, is kept. |
| `listings.key_failed` | A provider's remaining quota could not be read; the last figures, if any, are kept. |
| `listings.user_failed` | A user-chosen model source could not be read; it is skipped. |
| `permissions.output_unreadable` | A passed step's output could not be read when deciding whether a commit was vouched for; it counts as not vouched for. |
| `permissions.run_unreadable` | A run could not be read when deciding whether commits were vouched for; it vouches for nothing. |
| `profiles.keyring_failed` | The OS keyring failed or is missing, so the secret file store was used instead. |
| `queue.dequeue_run_unreadable` | A queued dispatch belonged to a run that is gone or unreadable, so there was nothing to record the drop in. |
| `resources.unreadable` | `~/.baton/resources.yaml` or the directory data could not be read when listing switched-off accounts. |
| `resources.yaml_invalid` | A machine resources file is not valid YAML; its declarations are ignored until fixed. |
| `sme.profiles_unreadable` | Profiles could not be read when listing experts. |
| `sme.run_unreadable` | A run could not be read when indexing or counting expert consultations. |
| `supervisor.marker_unreadable` | A running marker could not be read, so that dispatch is treated as not running here. |
| `tool_evidence.log_unreadable` | A helper's log could not be read to observe which tools it used; capability states are not updated from it. |
| `tool_evidence.tree_unreadable` | The project's working tree could not be read after a dispatch, so file changes were not observed. |
| `ui.route_failed` | A request to the setup page failed on a bug; the page answered with a generic error and no request detail was recorded. |
