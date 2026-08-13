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
│  │  │       Provider Router             │  │ │
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
3. **Provider Router** — routes each phase to the right executor; independent or cross-model review is an optional gate policy rather than a required path
4. **Permission Gate** — three-tier progressive permissions: `minimal` / `analyze` / `execute`

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
| 3 | Plan IR → DBOS workflow compiler | Planned |
| 4 | DBOS-backed execution runtime and deterministic output checks | Planned |
| 5 | Sagitta as the persistent persona and task-management assistant | Planned |

Cross-model routing, richer permissions, memory retrieval, social integrations, and visual management follow after a usable execution path exists.

---

## Documentation

- [**AGENTS.md**](AGENTS.md) — canonical design document (persona, task engine, layers, development phases)
- [**DESIGN.md**](DESIGN.md) — detailed design (state machine, gates, memory architecture, interaction flows)

## Planning MVP

The first runnable slice is deliberately narrow: natural language → Codex workspace inspection → a planner-written Plan Package with a validated, hierarchical Plan IR → a manual Goal export. Sagitta itself does not execute phases yet; the user manually starts the exported Goal in Codex App.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# Configure the existing directory that Codex may inspect.
sagitta init --workspace /absolute/path/to/workspace

# Codex plans with workspace-write access, using gpt-5.6-terra at high reasoning effort.
# It may run short, reversible project checks to establish planning facts and write its contract package.
# It does not begin delivery work, edit source, install dependencies, or change Git state while planning.
sagitta plan "Add OAuth login while preserving the existing session flow"

# If planning returns needs_input, answer a named question and resume that same Codex session.
sagitta answer <run-id> <question-id> "Use the existing session flow"

# Export the ready workflow as a Goal, paste it into a Codex App Goal, and let it run.
sagitta goal <run-id>
```

Prompts are regular editable files under `src/sagitta/prompts/`. The active planner prompt is `planner.md`; it includes a canonical IR few-shot and an ARIS-style contract-writing example. `phase_executor.md` records a later execution rule that missing information becomes explicit assumptions after a task has started.

The IR starts with ordinary `phase` nodes. Every phase declares its business `outputs` and `expected_facts`, then uses `on` to route task-specific outcomes to their next target. These contracts make completion inspectable without forcing a universal outcome vocabulary. Nested `scope` nodes are optional: use them only for real hierarchical work or bounded nested loops. Runtime will later maintain scope-local and workflow-wide entry counters, which conditional `on` routes can read with expressions such as `$major.minor < 3 and $workflow.minor < 8`. A phase's `.retry` counter is strictly for a direct transition back to that same phase; a repair cycle that travels through another phase must use a scope or workflow entry counter.

Each planning session is durable and inspectable under `~/.sagitta/plans/<plan-id>/`:

- `state.json` is the current planning state, configured workspace, Codex session ID, and Q&A;
- `TASK_CONTRACT.md` is the global source of truth for task-specific scope, trusted inputs, delivery, authority, and stop conditions;
- `phases/<phase-id>.md` is the concrete execution contract for each workflow phase;
- `ir.json` is written directly by the planner at `ready` and is the plan's only workflow source;
- `events.jsonl` records planning lifecycle events;
- `codex/` keeps each raw Codex JSONL event stream, stderr log, and final structured response.

The planner may inspect and revise this contract package at any point, and may ask questions whenever a user decision remains material. `sagitta answer` resumes the same Codex session from the plan's recorded workspace and sends only the newly supplied answer. Codex retains the preceding planning conversation; Sagitta separately retains the full Q&A for audit and later execution context, without injecting it back into the planner prompt. A `ready` response contains only planning status; Sagitta accepts it only when the global contract and every phase contract exist and are non-empty, and the planner-written `ir.json` passes local workflow validation.

`sagitta goal <run-id>` writes `goal/GOAL.md` into that plan's directory and prints the same self-contained text for pasting into Codex App. This compatibility bridge asks Goal to keep an uncommitted `.sagitta-goal-state.json` in the workspace while it follows the compiled graph. It explicitly links the global contract and the matching phase contract before each phase, while compiling IR navigation into natural-language instructions rather than exposing IR JSON or counter syntax to the executor. Its final user response remains task-defined rather than following a forced report template. It is a temporary substitute for Sagitta's future runtime; Goal's review records remain advisory unless backed by independent or deterministic evidence.

`outputs` and `expected_facts` are business contracts, rather than current runtime state. They describe what a phase must leave behind and what should be confirmable after it finishes. The later runtime will perform cheap deterministic completion checks wherever possible; judgment-heavy review remains an explicit `review` phase or a later acceptance policy.

If the planner-written `ir.json` fails Sagitta's local IR validator, Sagitta stores the validation error, then gives the same Codex session one automatic opportunity to correct the IR structure. A second invalid result remains recorded and ends planning with an error.

### Workspace policy

The MVP starts planning with workspace-write access. This lets Codex create the plan's contract package and run short, reversible checks, existing tests, compilation checks, or narrowly scoped dry runs when they establish a planning fact. The planner must not edit source, install dependencies, change Git state, start delivery work, or launch a long-running or costly job. It is intended to run in an operating workspace managed for this task. A later workspace resolver will prepare an isolated operating copy when the user directs Sagitta to another location:

- a GitHub repository is cloned into a managed workspace;
- a local or remote Git repository is worked on through a dedicated branch/worktree;
- a non-Git local or remote directory is copied into the managed workspace.

Sagitta will leave resulting content in that chosen operating location when work ends; it will not clean it up automatically.

---

## Repository

- **GitHub**: https://github.com/PureDimension/Sagitta-Agent
- **Execution units**: [Claude Code](https://claude.com/claude-code), [Codex](https://github.com/openai/codex), model APIs — pluggable via the bridge layer
- **Inspired by**: [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (MIT)
- **License**: MIT
