<h1 align="center">Sagitta-Agent</h1>

<p align="center">
  <b>A lightweight, self-planning development assistant for durable asynchronous work.</b><br>
  Builds an ongoing working relationship through a high-agency persona and persistent experience.<br>
  Executes through pluggable coding agents (Claude Code, Codex, model APIs).
</p>

---

## What Sagitta Is

Sagitta sits between you and coding agents (Claude Code, Codex, DeepSeek). You assign work in natural language as you would to a capable colleague. Sagitta forms its own view of the task, compiles the intent into a small inspectable workflow, executes it through a durable state machine, and returns only when a decision genuinely needs you.

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
2. **State Machine** — phase-level execution with ARIS-style gating: `pending → running → done → accepted`; advancement is controlled by explicit evidence and gate policy rather than the executor's confidence
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

## Development Phases

| Phase | Scope |
|-------|-------|
| **1: CLI Core** | `sagitta "do something"` — NL to a lightweight workflow language, validation, durable state execution, workflow revision, permission tiers, and a minimal persistent persona |
| **2: Persona & Experience** | Deeper user understanding, independent decision-making continuity, experience-backed learning, and selective retrieval |
| **3: Social & Multi-Platform** | WeChat/IM integration, proactive check-ins, multi-user support |
| **4: Advanced Autonomy** | Self-initiated tasks, richer workflow composition, visual inspection and editing |

---

## Documentation

- [**AGENTS.md**](AGENTS.md) — canonical design document (persona, task engine, layers, development phases)
- [**DESIGN.md**](DESIGN.md) — detailed design (state machine, gates, memory architecture, interaction flows)

---

## Repository

- **GitHub**: https://github.com/PureDimension/Sagitta-Agent
- **Execution units**: [Claude Code](https://claude.com/claude-code), [Codex](https://github.com/openai/codex), model APIs — pluggable via the bridge layer
- **Inspired by**: [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (MIT)
- **License**: MIT
