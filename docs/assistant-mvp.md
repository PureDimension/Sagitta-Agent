# Assistant and local console MVP

## Boundary and module map

The existing `ConfigStore`, `PlanningRunStore`, `PlanningService`, `CodexPlanner`, `GoalService`, Plan IR validator, and `sagitta` CLI retain their responsibilities and public behavior. The collaboration layer adapts them; it does not compile or execute Plan IR, change planner session semantics, or supervise a Goal.

| Module | Responsibility |
| --- | --- |
| `sagitta.collaboration` | Versioned profile, inferred project registry, Task-owned transcripts and model history, safe registered-workspace reads, and Task-scoped Plan/Goal lookup. |
| `sagitta.assistant` | Narrow collaboration service and injectable conversational gateway. It routes Sagitta and Direct turns into one Task-owned context, with planning, complete planner-answer rounds, and ready Goal export. |
| `sagitta.web` | Loopback FastAPI app, typed JSON boundary, static-resource serving, and ASGI startup. |
| `sagitta.web.static` | Native HTML/CSS/ES-module dashboard. It renders server-supplied workflow data and has no provider, filesystem, shell, or secret capability. |

## Ownership and storage

The UI and persistence model distinguish four objects:

```text
Project → Task → Plan → Run
```

A Project is an operating workspace. A Task is one user objective and the only collaboration boundary. A Plan is the selected workflow package for that Task; it may be created, reviewed, or replaced before work begins. A Run is one durable execution attempt of a selected Plan. Plan and Run are therefore separable operational stages of one Task: the current MVP implements Task and Plan persistence, while the Run record is reserved for the durable runtime.

`~/.sagitta/` (or the configured home) is the outer application's state home:

- `profile.md`: editable UTF-8 user profile;
- `model.json`: owner-only local model, base URL, and API-key configuration;
- `projects.json`: schema-versioned registry of named project IDs and resolved workspaces;
- `tasks/<task-id>/state.json`: Task identity, Project owner, title, and optional Plan package reference;
- `tasks/<task-id>/conversation.jsonl`: full append-only audited Sagitta and Direct turns;
- `tasks/<task-id>/agent-history.json`: PydanticAI structured message history, including permitted tool calls;
- `plans/<plan-id>/`: PlanningRunStore-owned Plan Packages, planner traces, fresh pre-launch review traces, and the final launch verdict. Each package belongs to one Task.

The future Run store will be distinct from the Plan Package. One Run will record its selected immutable Plan revision, active phase and route, phase entry/retry counters and anchor-window counters, executor session reference, heartbeat, checkpoint, evidence pointers, allowed operation decisions, and append-only event ledger. This separation permits a Task to preserve planning context while recording one or more actual execution attempts.

A registered project's workspace stays operationally separate. Registration is external-only and comes from an explicit Finder directory selection; it writes no marker into the chosen project. The console reads executor-owned `.sagitta-goal-state.json`, reported as `absent`, `invalid`, or `available`; the Goal also keeps append-only `.sagitta-goal/RUN_LEDGER.jsonl` and `.sagitta-goal/CHECKPOINT.md` for manual execution reconciliation. These are transitional Goal artifacts, not Sagitta runtime records.

## JSON API

All responses use either `{"ok": true, "data": ...}` or `{"ok": false, "error": {"code", "message"}}`. Browser-visible errors exclude provider internals, environment values, and unapproved paths.

| Route | Operation |
| --- | --- |
| `GET /api/health` | Local configuration/no-key diagnostic. |
| `GET /api/settings`, `PUT /api/settings` | Read redacted or update owner-only local model settings. |
| `POST /api/system/select-directory`, `GET/POST /api/projects` | Open Finder, then list or register its selected local directory with inferred identity. |
| `GET /api/projects/{id}` | Project workspace display state and transitional Goal state. |
| `GET/POST /api/projects/{id}/tasks`, `GET/DELETE .../tasks/{task_id}` | List, create, inspect, or delete one isolated Task and its dependent local data. |
| `GET .../tasks/{task_id}/conversation`, `POST .../messages` | Read one Task transcript or send a Sagitta-routed turn. |
| `POST .../tasks/{task_id}/plans`, `POST .../answers`, `GET .../activity` | Direct-mode planning, complete answer rounds, and AG-UI-shaped Codex activity for that Task. |
| `GET .../plans/{run_id}` | Plan detail and a presentation-only IR graph (`nodes`, `edges`). |
| `POST /api/projects/{id}/plans/{run_id}/goal`, `GET .../goal` | Export/read a ready, validated Goal. |
| `GET /api/projects/{id}/goal-state` | Safe transitional Goal-state display. |
| `GET .../plans/{run_id}/artifacts`, `GET .../artifacts/{artifact_id}` | List/read only known Plan Package files for formatted observation. |

Allowed browser actions are Finder-selected project registration, Task creation/deletion, Task-scoped messaging through Sagitta, direct Task planning, complete planner-answer rounds, ready Goal export, and validated Plan artifact reads. The Agent/Direct switch is a routing choice within one Task: it never moves or duplicates context. Arbitrary paths, shell operations, source edits, raw environment access, and browser-side workflow execution are excluded.

## Provider interface fact

The declared runtime dependency is `pydantic-ai-slim[openai]>=2.29,<3`, the lightweight official PydanticAI distribution that provides the same `pydantic_ai` runtime and OpenAI-compatible provider support. The implementation creates `OpenAIChatModel` only while servicing a real turn, using a locally configured model/base URL/API key with `DEEPSEEK_API_KEY` and `DEEPSEEK_BASE_URL` as environment fallbacks. The browser only receives a redacted settings status. PydanticAI's production loop persists its structured message history and receives only the named collaboration tools above; offline tests inject a gateway fake and make no provider call.

## Local operation

Install with `python -m pip install -e .`, then run `sagitta-web` (or `python -m sagitta.web`) to bind `127.0.0.1:8123`. `SAGITTA_HOST` and `SAGITTA_PORT` are explicit optional overrides. One PID file per port under `~/.sagitta/` lets startup replace a prior Sagitta Web instance; a verified legacy Sagitta listener on the same port is also stopped, while unrelated listeners are never terminated. The app does not register its own source tree. Without a configured API key, dashboards, Direct planning, Plan visualization, and Goal observation still work. Planning uses a persistent Sol-high author and a fresh read-only Sol-high pre-launch reviewer, with one bounded package revision. Goal execution remains the manual Codex compatibility bridge, with contract-gated ledger/checkpoint discipline but no live supervision, interruption, or DBOS runtime.

## Persisted and API shapes

`projects.json` has `{"version": 1, "projects": [...]}`. A project record has a validated lower-case `id`, inferred directory label, canonical resolved `workspace`, and creation time. Its ID is the only input used to obtain a workspace later.

Each `tasks/<task-id>/conversation.jsonl` line is an append-only turn object with `id`, UTC `at`, `role` (`user` or `assistant`), `content`, and structured non-secret `metadata`. A Task is the only UI collaboration boundary; legacy Project transcript locations remain compatibility data and are not used by the current console.

Goal-state display accepts only an object up to 128 KiB, then projects it to bounded known fields: `current_phase`, `final_result`, bounded `entered_nodes`, `{phase, outcome}` entries, and string-only `coverage`. Unknown fields and unbounded nested values never reach the API/browser. These Goal files are observational compatibility data only; the future Run ledger will be owned by Sagitta's program runtime rather than inferred from executor-written files.

Message input is `{"content": "..."}`; Task creation uses `{"title": "..."}`; direct planning input is `{"intent": "..."}`; complete Task planner answers use `{"answers": [{"id", "answer"}]}`; registration input is `{"workspace": "..."}` after a Finder selection. Agent mode supplies planning intent and complete settled answer rounds through PydanticAI tools after task understanding, while Direct mode sends them explicitly to the same Task's `PlanningService`. Ready plan detail adds a presentation-only graph whose node data contains phase ID, title, kind, objective, outputs, expected facts, and outcome names; edges contain only `from`, `to`, and outcome label. The browser never evaluates workflow routes or counter expressions.

## Planned Run and collaboration boundaries

The durable runtime will execute a Plan as a real-time **Run**, keeping state transitions program-owned and recoverable. The initial boundary is deliberately narrow: the runtime validates IR routes and counters, starts one phase worker, persists a checkpoint and heartbeat, receives a structured phase result, records evidence, and then decides the next route. Deterministic validation plugins can progressively replace executor assertions for checks that have a concrete contract. The backend adapter remains open: DBOS is a planned candidate, while the Run semantics and event model stay independent of it.

The later Sagitta collaboration layer builds around that boundary in four parts:

- **Experience**: structured after-action records for decisions, failures, effective tests, preferences, and outcomes, with selective retrieval later.
- **Monitoring**: observation of worker health, heartbeat loss, retry exhaustion, route/evidence conflicts, and project anomalies; recovery is proposed or requested through audited runtime operations.
- **Project operations**: explicit clone, worktree, branch, copy, archive, and handoff operations around a Task/Run, rather than an unrestricted background agent.
- **Persistent collaboration**: a persona that can retain user and project understanding, continue design discussion, and make visible, bounded initiatives without silently mutating a Run.
