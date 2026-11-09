# Change register

One row per change doc in this folder: the place to see every change's status without opening it. Every agent that creates a change doc, or changes its status, title or level, updates its row in the same commit; and every agent that touches this register first adds any change doc that has no row yet and fixes any row that has drifted from its front matter. Rows are ordered by status (in-progress, accepted, proposed, done, abandoned), then by id. The rules are in [AGENTS.md](../../AGENTS.md); `tests/test_docs.py` checks the register against the change docs.

| Change | Title | Status | Level | Note |
|---|---|---|---|---|
| [2026-11-browser-automation](2026-11-browser-automation.md) | Steps can operate a web app in a browser for the owner, with the owner's authorization | proposed | major | On hold: after 2026-11-step-tool-harness |
| [2026-11-recipe-builder](2026-11-recipe-builder.md) | A recipe-builder recipe turns an owner's described process into a validated, vendorable recipe | proposed | major | |
| [2026-11-recipe-tree](2026-11-recipe-tree.md) | Recipes form a tree: broad recipes that specialized ones are derived from by copy | proposed | major | On hold indefinitely (2026-11-08): provenance recorded via 2026-11-recipe-builder; revisit on trigger |
| [2026-11-self-improvement](2026-11-self-improvement.md) | Baton notices when the owner is confused by a question and improves the recipe's wording, locally first | proposed | major | On hold: discussion stage, not ready for Design approval |
| [2026-11-step-tool-harness](2026-11-step-tool-harness.md) | Baton runs a bounded tool loop for API workers, with only the tools a step requires | proposed | major | On hold: after 2026-11-capability-confidence and 2026-11-cli-model-routes |
| [2026-11-zero-friction-setup](2026-11-zero-friction-setup.md) | Become a Baton director: setup with as little owner effort as possible | proposed | major | On hold (owner, 2026-11-05): not to be designed further or implemented until the owner accepts it |
| [2026-11-capability-confidence](2026-11-capability-confidence.md) | Capabilities are likely until used; harness tooling is turned on per step and verified by use | done | standard | |
| [2026-11-change-register](2026-11-change-register.md) | Change statuses are tracked in one register that every agent keeps up to date | done | minor | |
| [2026-11-cli-model-routes](2026-11-cli-model-routes.md) | Research proposes a route for every model each harness can run, and the capabilities that should be present | done | standard | |
| [2026-11-codex-director-sandbox](2026-11-codex-director-sandbox.md) | Codex as Director: detect its sandbox and connect Baton through MCP | done | standard | |
| [2026-11-diagnostics](2026-11-diagnostics.md) | Baton records the conditions it works around, keeps them bounded, and doctor speaks up when they become unusual | done | standard | |
| [2026-11-director-question-check](2026-11-director-question-check.md) | The Director checks its questions before asking the owner, and the framing label tells the truth | done | minor | |
| [2026-11-director-wake](2026-11-director-wake.md) | A detached Director notices when work finishes, or tells the owner first that it might not | done | standard | |
| [2026-11-fast-tests](2026-11-fast-tests.md) | Slices are checked by a fast run of the affected tests; the full suite runs in parallel in the background and still gates every finish | done | standard | |
| [2026-11-framing-perspective](2026-11-framing-perspective.md) | The Director bridges the process and owner perspectives; framing's breakdown and the owner's notes are kept as project documents | done | standard | |
| [2026-11-not-offered-reasons](2026-11-not-offered-reasons.md) | Worker status says which catalog it read and exactly why a generated profile is no longer offered | done | minor | |
| [2026-11-windows-harness-version-change](2026-11-windows-harness-version-change.md) | A harness upgrade is noticed on Windows, so observed capability states return to likely | done | minor | |
| [2026-11-windows-real-use-timeout](2026-11-windows-real-use-timeout.md) | The multi-session real-use scenario finishes on the Windows runner instead of hitting its own deadline | done | minor | |
| [2026-11-windows-running-marker](2026-11-windows-running-marker.md) | A supervisor on Windows survives a Director reading its running marker | done | minor | |
| [2026-11-windows-supervisor-console](2026-11-windows-supervisor-console.md) | A supervisor on Windows opens no console window | done | minor | |
| [2026-11-worker-setup](2026-11-worker-setup.md) | Machine-wide worker resources are maintained separately from project setup | done | standard | |
