<h1 align="center">Sagitta-Agent</h1>

<p align="center">
  <b>A lightweight, self-planning development assistant for durable asynchronous work.</b><br>
  Builds an ongoing working relationship through a high-agency persona and persistent experience.<br>
  Executes through pluggable coding agents (Claude Code, Codex, model APIs).
</p>

---

## What Sagitta Is

Sagitta is designed to sit between you and coding agents (Claude Code, Codex, DeepSeek). You assign work in natural language as you would to a capable colleague. It forms its own view of the task, compiles the intent into a small inspectable workflow, will execute it through a durable state machine, and returns only when a decision genuinely needs you.

Sagitta is deliberately development-focused. It is not a universal agent gateway and does not try to connect every model, tool, channel, or part of a user's life. Its goal is to make real development work reliable enough to leave running asynchronously while preserving the judgment and continuity of an ongoing working relationship.

```
You: "Help me research recent papers on agent memory systems, and check if they can be applied to ARIS"

Sagitta:
  1. Parse intent → generate a workflow plan
  2. Compile the intent into a lightweight, editable workflow
  3. Execute phase by phase (analysis → review → implementation → verification)
  4. Advance through machine-checkable gates; interrupt only at real decision points
  5. Remember the decisions, results, and what they reveal about how you work together
```

The core loop: **Natural Language → Workflow Compilation → Boundary Confirmation → Deterministic Execution → Selective Escalation → Experience**.

---

## Why Sagitta Exists

Sagitta is a personal open-source project built because the available tools do not fit the way its author wants to work:

- ARIS provides disciplined acceptance gates, but asks the user to design the workflow and settle too many implementation details before a long run can begin.
- Goal-driven coding agents can work for a long time, but their control state and phase decisions remain largely inside the AI loop rather than an inspectable runtime.
- General agent platforms optimize for broad compatibility. Sagitta instead optimizes for a small, coherent development workflow and a persistent working relationship.
- Graph runtimes provide durable primitives, but leave the user or application developer to author the graph.

Sagitta joins two cores that are usually separated: a **durable development task engine** and a **high-agency persona**. The task engine turns natural language into a lightweight, revisable workflow and advances it using explicit state and evidence. The persona develops an understanding of the user, projects, past decisions, and its own judgment through continued work together.

Execution units are **pluggable adapters** behind the bridge layer, not part of the core: complex phases can run on coding agents and cheap phases on model APIs. Independent or cross-model review can be introduced selectively when its value justifies its cost.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Sagitta-Agent                   │
│                                              │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Persona  │  │  Dialogue  │  │Experience│ │  ← Collaboration layer: identity, user understanding, history
│  │ Layer    │  │  Manager   │  │  Memory  │ │
│  └────┬─────┘  └─────┬──────┘  └────┬─────┘ │
│       │              │              │        │
│  ┌────▼──────────────▼──────────────▼─────┐ │
│  │           Intent Router                │ │  ← Routing layer: chat vs task vs tool calls
│  └────────────────┬───────────────────────┘ │
│                   │                          │
│  ┌────────────────▼───────────────────────┐ │
│  │           Task Engine                  │ │
│  │                                        │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────┐ │ │  ← Execution layer: ARIS-style state machine
│  │  │ Planner  │  │  State   │  │ Gate │ │ │
│  │  │ (NL→WF)  │  │ Machine  │  │Engine│ │ │
│  │  └──────────┘  └──────────┘  └──────┘ │ │
│  │                                        │ │
│  │  ┌──────────────────────────────────┐  │ │
│  │  │    Future Provider Router          │  │ │
│  │  │  Claude Code / Codex / DeepSeek  │  │ │
│  │  └──────────────────────────────────┘  │ │
│  └────────────────────────────────────────┘ │
│                                              │
│  Executes via: Claude Code / DeepSeek /      │
│  Codex (pluggable execution units)           │
└─────────────────────────────────────────────┘
```

### Task Engine

The Task Engine is one of Sagitta's two cores. It wraps coding agents (Claude Code, Codex, DeepSeek) in a state-machine orchestration layer:

1. **Planner** — converts natural language requirements into a structured workflow plan
2. **Future State Machine** — phase-level execution will use ARIS-style gating: `pending → running → done → accepted`; advancement will be controlled by explicit evidence and gate policy rather than executor confidence
3. **Future Provider Router** — the durable runtime may later route phases to different executors; the current Goal bridge has no execution-model orchestration and runs entirely in the Codex App model selected by the user
4. **Permission Gate** — three-tier progressive permissions: `minimal` / `analyze` / `execute`

### Work ownership: Project, Task, Plan, Run

Sagitta uses four deliberately different objects. Keeping them separate is what lets a natural-language collaboration become a recoverable overnight process without turning a planning artifact into the runtime itself.

```text
Project  = one registered operating workspace or repository
└─ Task  = one user objective and its collaboration boundary
   ├─ Plan = the selected, inspectable workflow and contract package
   └─ Run  = one concrete attempt to execute that Plan
```

- A **Project** supplies the operating context. It can contain many independent Tasks.
- A **Task** owns the conversation, user decisions, planner activity, and eventual execution history for one objective.
- A **Plan** is the Task's selected planning result: its IR, task contract, phase contracts, and launch review. Planning and execution are separable in practice, so a Task may be discussed or planned for a long time before any Run starts.
- A **Run** is a durable, observable execution of a selected Plan. It owns the current phase, route decision, counters, executor session, checkpoint, heartbeat, evidence, and append-only event ledger. A Task may eventually retain several Runs of the same or revised Plan.

The current console persists Task conversations and Plan packages. The Run model is the next runtime boundary; the temporary Codex Goal is a compatibility bridge, not a Run implementation.

---

## Key Design Decisions

1. **Lightweight and Development-Focused** — build only the control, relationship, and integration surfaces required for durable development work
2. **High-Agency Persona** — Sagitta understands the user over time while forming and expressing its own opinions; it questions unclear instructions, proposes alternatives, and learns from outcomes
3. **Natural Language Interface** — no explicit `/task` or `/chat` prefixes; intent is determined from natural language
4. **Long-Term Collaboration Memory** — user and project understanding, past decisions, outcomes, disagreements, and Sagitta's evolving judgments
5. **Two Cores, Pluggable Executors** — Sagitta owns the durable workflow semantics and persistent persona; coding agents and model APIs remain replaceable execution units

---

## Delivery Roadmap

| Order | Scope | Status |
|-------|-------|--------|
| 1 | NL → inspected Plan Package + validated Plan IR | Implemented planning core |
| 2 | Plan IR → paste-ready Codex Goal | Implemented temporary compatibility bridge |
| 3 | Task Plan → durable, real-time program state-machine Run | Planned |
| 4 | Run persistence, deterministic checks, and a backend adapter (including a possible DBOS compiler) | Planned |
| 5 | Sagitta as the persistent persona and task-management assistant | Planned |

The runtime semantics come before selecting a durable backend: Plan IR routing, Run state, counters, evidence, resume, and allowed operations must stay testable independently of DBOS or another engine. Cross-model routing, richer permissions, memory retrieval, social integrations, and visual management follow after a usable execution path exists. Today only Plan Package authoring and its fresh pre-launch review are fixed to `gpt-5.6-sol` with high reasoning effort; Goal execution does not select or switch models.

### Long-term collaboration capabilities

Sagitta's later collaboration layer has four connected responsibilities:

1. **Real-time overnight execution** — a program-owned Run state machine advances only through recorded routes and gate decisions, retains heartbeats and checkpoints, and can resume after interruption.
2. **Experience accumulation** — after-action experience records first capture decisions, failures, effective checks, preferences, and outcomes. Retrieval can grow from this structured base instead of treating an unbounded chat transcript as memory.
3. **Run monitoring and maintenance** — Sagitta observes run events, executor health, retry exhaustion, evidence failures, and unexpected project conditions. It may diagnose or propose a bounded recovery; the runtime performs only explicitly permitted, auditable operations.
4. **Project operations and ongoing collaboration** — Sagitta can treat a long task as an atomic project operation: prepare a clone/worktree/branch, hand it to a Run, preserve or move the resulting work, and retain context for continuing design conversations. Its initiative remains visible and bounded by the Task's authority.

---

## Documentation

- [**AGENTS.md**](AGENTS.md) — canonical design document (persona, task engine, layers, development phases)
- [**DESIGN.md**](DESIGN.md) — detailed design (state machine, gates, memory architecture, interaction flows)

## Planning MVP

The first runnable slice is deliberately narrow: natural language → Codex workspace inspection → a planner-written Plan Package and hierarchical Plan IR → fresh read-only pre-launch review with one bounded planner revision → a manual Goal export. Sagitta itself does not execute phases yet; the user manually starts the exported Goal in Codex App.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Configure the existing directory that Codex may inspect.
sagitta init --workspace /absolute/path/to/workspace

# Codex plans with workspace-write access, using gpt-5.6-sol at high reasoning effort.
# It may run short, reversible project checks to establish planning facts and write its contract package.
# It does not begin delivery work, edit source, install dependencies, or change Git state while planning.
sagitta plan "Add OAuth login while preserving the existing session flow"

# If planning returns needs_input, answer a named question and resume that same Codex session.
sagitta answer <run-id> <question-id> "Use the existing session flow"

# A fresh read-only Codex reviews the whole package before ready. One revision is allowed.
# Export the reviewed workflow as a Goal, paste it into a Codex App Goal, and let it run.
sagitta goal <run-id>
```

Prompts are regular editable files under `src/sagitta/prompts/`. `planner.md` includes the canonical IR few-shot, ARIS-style contract example, and mandatory per-outcome admission conditions. `prelaunch_review.md` reviews the complete package for uncovered requirements, fakeable gates, and invalid terminal paths. `goal.md` compiles the reviewed package into the temporary deterministic Goal protocol. `phase_executor.md` records a later execution rule for the durable runtime.

The IR starts with ordinary `phase` nodes. Every phase declares its business `outputs` and `expected_facts`, then uses `on` to route task-specific outcomes to their next target. These contracts make completion inspectable without forcing a universal outcome vocabulary. Nested `scope` nodes are optional: use them only for real hierarchical work or bounded nested loops. Runtime will later maintain scope-local and workflow-wide entry counters, which conditional `on` routes can read with expressions such as `$major.minor < 3 and $workflow.minor < 8`. A phase's `.retry` counter is strictly for a direct transition back to that same phase; a repair cycle that travels through another phase must use a scope or workflow entry counter.

Each planning session is durable and inspectable under `~/.sagitta/plans/<plan-id>/`:

- `state.json` is the current planning state, configured workspace, Codex session ID, and Q&A;
- `TASK_CONTRACT.md` is the global source of truth for task-specific scope, trusted inputs, delivery, authority, and stop conditions;
- `phases/<phase-id>.md` is the concrete execution contract for each workflow phase;
- `ir.json` is written directly by the planner at `ready` and is the plan's only workflow source;
- `PRELAUNCH_REVIEW.md` is the final fresh-context launch verdict;
- `events.jsonl` records planning lifecycle events;
- `codex/` keeps planner calls, while `reviews/` keeps each fresh pre-launch review trace and response.

The planner may inspect and revise this contract package at any point, and may ask questions whenever a user decision remains material. `sagitta answer` resumes the same Codex session from the plan's recorded workspace and sends only the newly supplied answer. Codex retains the preceding planning conversation; Sagitta separately retains the full Q&A for audit and later execution context, without injecting it back into the planner prompt. When the planner proposes `ready`, Sagitta first validates the files and IR, then starts a fresh read-only Sol-high review. A rejection becomes a new observation for the original planner session; it may revise once or return `needs_input`. A second rejection ends as `planning_review_failed` and cannot export a Goal. A passing verdict freezes SHA-256 values for the reviewed contracts and IR; Goal export refuses a package changed after review.

`sagitta goal <run-id>` exports only a Plan Package with a passing pre-launch review. The generated Goal links the task, review, and phase contracts and compiles IR navigation into natural language rather than exposing IR JSON or counter syntax. During manual execution it maintains `.sagitta-goal-state.json`, append-only `.sagitta-goal/RUN_LEDGER.jsonl`, and `.sagitta-goal/CHECKPOINT.md`. Every phase registers its outcome conditions before work, records commands/evidence, reconciles the contract before transition, and may choose an outcome only when its complete admission condition is proved. Graph completion ends as `ready_for_human_audit`, `delivery_limited`, or `blocked`; the executor cannot declare `delivery_complete`. This remains a temporary substitute for the future durable runtime.

Plans created before the pre-launch-review contract are not grandfathered into Goal export. Re-plan them so the package can be reviewed and content-hash-bound before execution.

`outputs` and `expected_facts` are business contracts, rather than current runtime state. They describe what a phase must leave behind and what should be confirmable after it finishes. The later runtime will perform cheap deterministic completion checks wherever possible; judgment-heavy review remains an explicit `review` phase or a later acceptance policy.

If the planner-written `ir.json` fails Sagitta's local IR validator, Sagitta stores the validation error, then gives the same Codex session one automatic opportunity to correct the IR structure. Separately, a rejected pre-launch review permits one package-level revision. A second structural error or second review rejection remains recorded and prevents Goal export.

### Workspace policy

The MVP starts planning with workspace-write access. This lets Codex create the plan's contract package and run short, reversible checks, existing tests, compilation checks, or narrowly scoped dry runs when they establish a planning fact. The planner must not edit source, install dependencies, change Git state, start delivery work, or launch a long-running or costly job. It is intended to run in an operating workspace managed for this task. A later workspace resolver will prepare an isolated operating copy when the user directs Sagitta to another location:

- a GitHub repository is cloned into a managed workspace;
- a local or remote Git repository is worked on through a dedicated branch/worktree;
- a non-Git local or remote directory is copied into the managed workspace.

Sagitta will leave resulting content in that chosen operating location when work ends; it will not clean it up automatically.

## Local assistant and project console MVP

The planning CLI remains available as above. The first collaboration slice adds a loopback-only local console for registered projects, full audited transcripts, an editable profile, Codex planning delegation, and manual Goal inspection.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Starts only on localhost by default.
sagitta-web
```

Open `http://127.0.0.1:8123`. Set `SAGITTA_HOST` and `SAGITTA_PORT` only when an explicit alternate local binding or port is required. Startup replaces an older Sagitta Web process recorded for the same port, and can also recognize an older local `sagitta-web`/`python -m sagitta.web` listener left before PID tracking was introduced. It never terminates an unrelated process that happens to own the port. The console starts with no implicit project registration; add an operating copy as an ordinary project when you want Sagitta to update Sagitta itself.

Use the local settings button to configure the collaboration model, OpenAI-compatible base URL, API key, and Profile. The API key is kept in an owner-only file under `~/.sagitta/`, is never returned by the API, and may also be supplied through `DEEPSEEK_API_KEY` as an environment fallback.

The console uses a Finder directory picker to register existing local projects and automatically selects the first available project when it opens. A Project is only a workspace; each **Task** owns an isolated conversation, Codex activity stream, and the lifecycle around one objective. Its current Plan artifacts are the package, IR, review, and Goal export; a future Run will supply separate execution records. Its two main views are **Interaction** and **Visualization**. In **Sagitta** mode, natural language goes through the persistent PydanticAI collaboration agent; in **Direct** mode, the same Task conversation is routed directly to the Codex planner. The Visualization view renders the selected Task's Plan graph, phase contracts, package files, review, Q&A, and transitional Goal state. Goal remains a manual compatibility bridge: this MVP does not supervise a Goal run, receive real-time Goal events, interrupt Codex, or implement the future program-owned runtime.

Profile is editable in Settings and stored at `~/.sagitta/profile.md`; Task conversation and PydanticAI message history live together under `~/.sagitta/tasks/<task-id>/`. This makes switching between Sagitta and Direct a routing choice rather than a context change. See [the implementation map](docs/assistant-mvp.md) for state ownership and API details.

---

## Repository

- **GitHub**: https://github.com/PureDimension/Sagitta-Agent
- **Execution units**: [Claude Code](https://claude.com/claude-code), [Codex](https://github.com/openai/codex), model APIs — pluggable via the bridge layer
- **Inspired by**: [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (MIT)
- **License**: MIT
