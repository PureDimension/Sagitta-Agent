# Assistant and local console MVP

## Boundary and module map

The existing `ConfigStore`, `PlanningRunStore`, `PlanningService`, `CodexPlanner`, `GoalService`, Plan IR validator, and `sagitta` CLI retain their responsibilities and public behavior. The collaboration layer adapts them; it does not compile or execute Plan IR, change planner session semantics, or supervise a Goal.

| Module | Responsibility |
| --- | --- |
| `sagitta.collaboration` | Versioned profile, registry, append-only transcript, future-summary reservation, safe registered-workspace reads, and project-scoped plan/Goal lookup. |
| `sagitta.assistant` | Narrow collaboration service and injectable conversational gateway. Its only delegated operations are status, start planning, explicit planner-answer resume, and ready Goal export. |
| `sagitta.web` | Loopback FastAPI app, typed JSON boundary, static-resource serving, and ASGI startup. |
| `sagitta.web.static` | Native HTML/CSS/ES-module dashboard. It renders server-supplied workflow data and has no provider, filesystem, shell, or secret capability. |

## Ownership and storage

`~/.sagitta/` (or the configured home) is the outer application's state home:

- `profile.md`: editable UTF-8 user profile;
- `projects.json`: schema-versioned registry of named project IDs and resolved workspaces;
- `conversations/<project-id>.jsonl`: full append-only audited turns;
- `conversation-summaries/<project-id>.md`: reserved empty future compression location;
- `plans/<plan-id>/`: PlanningRunStore-owned Plan Packages, planner traces, fresh pre-launch review traces, and the final launch verdict.

A registered project's workspace stays operationally separate. The console reads executor-owned `.sagitta-goal-state.json`, reported as `absent`, `invalid`, or `available`; the Goal also keeps append-only `.sagitta-goal/RUN_LEDGER.jsonl` and `.sagitta-goal/CHECKPOINT.md` for manual execution reconciliation. These are transitional Goal artifacts, not Sagitta runtime records. The self-hosted inner project is registered with a stable ID and a `relationship: "self_hosting_inner"` marker; its application state remains outside that workspace.

## JSON API

All responses use either `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message"}}`. Browser-visible errors exclude provider internals, environment values, and unapproved paths.

| Route | Operation |
| --- | --- |
| `GET /api/health` | Local configuration/no-key diagnostic. |
| `GET/POST /api/projects` | List or register an existing local directory. |
| `GET /api/projects/{id}` | Project, workspace display state, plan summary, and transitional Goal state. |
| `GET /api/projects/{id}/conversation`, `POST .../messages` | Read full transcript or send a user turn. |
| `GET /api/projects/{id}/pending-question`, `POST .../answers` | Read and explicitly submit a planner answer. |
| `GET /api/projects/{id}/plans`, `GET .../plans/{run_id}` | Project-isolated plan data and a presentation-only IR graph (`nodes`, `edges`). Planner start remains a PydanticAI-only controlled tool after Sagitta has understood the task. |
| `POST /api/projects/{id}/plans/{run_id}/goal`, `GET .../goal` | Export/read a ready, validated Goal. |
| `GET /api/projects/{id}/goal-state` | Safe transitional Goal-state display. |

Allowed browser actions are local project registration, registered-project state reads, messaging, explicit planner answers, ready Goal export, and validated Goal reads. Arbitrary paths, shell operations, source edits, API keys, raw environment access, and browser-side workflow execution are excluded.

## Provider interface fact

The declared runtime dependency is `pydantic-ai-slim[openai]>=2.29,<3`, the lightweight official PydanticAI distribution that provides the same `pydantic_ai` runtime and OpenAI-compatible provider support. Offline installation validated version `2.29.0`: `Agent`, `OpenAIChatModel`, and `DeepSeekProvider` import from the documented module paths. The implementation creates `pydantic_ai.models.openai.OpenAIChatModel("deepseek-chat", provider=pydantic_ai.providers.deepseek.DeepSeekProvider(api_key=...))` only while servicing a real turn. `DEEPSEEK_API_KEY` is read from the process environment at that moment and is never stored or returned. PydanticAI's production loop receives only the named collaboration tools above; offline tests inject a gateway fake and make no provider call.

## Local operation

Install with `python -m pip install -e .`, then run `sagitta-web` (or `python -m sagitta.web`) to bind `127.0.0.1:8123`. `SAGITTA_HOST` and `SAGITTA_PORT` are explicit optional overrides. Without `DEEPSEEK_API_KEY`, dashboards still work and chat returns the configuration action `export DEEPSEEK_API_KEY=...`; a real provider turn is outside offline verification. Planning uses a persistent Sol-high author and a fresh read-only Sol-high pre-launch reviewer, with one bounded package revision. Goal execution remains the manual Codex compatibility bridge, with contract-gated ledger/checkpoint discipline but no live supervision, interruption, or DBOS runtime.

## Persisted and API shapes

`projects.json` has `{"version": 1, "projects": [...]}`. A project record has a validated lower-case `id`, user label, canonical resolved `workspace`, relationship marker, and creation time. Its ID is the only input used to obtain a workspace later.

Each `conversations/<project-id>.jsonl` line is an append-only turn object with `id`, UTC `at`, `role` (`user` or `assistant`), `content`, and structured non-secret `metadata`. Future compression has a separately named `conversation-summaries/<project-id>.md` location; no code reads it for retrieval.

Goal-state display accepts only an object up to 128 KiB, then projects it to bounded known fields: `current_phase`, `final_result`, bounded `entered_nodes`, `{phase, outcome}` entries, and string-only `coverage`. Unknown fields and unbounded nested values never reach the API/browser.

Message input is `{"content": "..."}`; planner answer input is `{"run_id", "question_id", "answer"}`; registration input is `{"id", "label", "workspace"}`. Planning intent is supplied to Sagitta in conversation and reaches `PlanningService` only through the PydanticAI controlled tool after task understanding. Ready plan detail adds a presentation-only graph whose node data contains phase/scope ID, title, kind, objective, outputs, expected facts, and outcome names; edges contain only `from`, `to`, and outcome label. The browser never evaluates workflow routes or counter expressions.
