# Phase 2 — collaboration core

> Historical executor-authored record from the withdrawn first Goal run. It is retained for diagnosis and does not constitute accepted phase evidence.

## Contract checklist

| Required output/fact | Evidence | Result |
| --- | --- | --- |
| Atomic profile/registry records and append-only transcripts under Sagitta home | `sagitta.collaboration.CollaborationStore`; `test_profile_registry_transcript_and_goal_state_are_project_scoped` | Confirmed. |
| Canonical registered workspace and project-ID-only access | `register_project` resolves directories; `resolve_project`, transcript, plan, Goal, and state operations begin with project resolution; registry/path tests | Confirmed. |
| Self-hosting identity stays separate from application home | Stable `sagitta-self-hosting` record with `self_hosting_inner`; temporary-home test | Confirmed. |
| Goal compatibility state is safe for untrusted display | 128 KiB bound, invalid/absent typed state, bounded known-field projection; secret-projection regression test | Confirmed. |
| Lazy process-only DeepSeek factory | `PydanticAIGateway.reply`; no-key and model/provider construction fakes | Confirmed offline. |
| Only named model delegation tools | Capturing-agent test proves exactly `project_status`, `start_codex_planning`, and `export_ready_goal`; planner answer has no model tool | Confirmed. |
| Planner answer can only be resumed explicitly by the user | `/answers` path invokes `AssistantService.submit_planner_answer`; no browser planning-start route; API regression test | Confirmed. |
| Existing CLI configuration remains unchanged by project planning | `test_planning_is_registered_project_scoped_and_keeps_cli_config` | Confirmed. |

## Commands and results

```text
.venv/bin/python -m unittest tests.test_collaboration -v -> 9 tests passed
git diff --check                                       -> passed
```

## Outcome

The executor selected `core_ready`. That selection was later withdrawn: the checks remain useful implementation observations, while the old contract and Goal protocol did not establish a complete, independently reconcilable admission condition.
