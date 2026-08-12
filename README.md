<h1 align="center">Sagitta-Agent</h1>

<p align="center">
  <b>A self-planning, long-running coding agent designed for async invocation over extended periods.</b><br>
  Integrates with persona-driven assistants and social platforms.<br>
  Executes through pluggable coding agents (Claude Code, Codex, model APIs).
</p>

---

## What Sagitta Is

Sagitta sits between you and coding agents (Claude Code, Codex, DeepSeek). You talk to Sagitta in natural language. Sagitta decides what to do, plans how to do it, executes autonomously, and comes back to you at decision points.

```
You: "Help me research recent papers on agent memory systems, and check if they can be applied to ARIS"

Sagitta:
  1. Parse intent → generate a workflow plan
  2. Show the plan, ask for your confirmation
  3. Execute phase by phase (analysis → review → implementation → verification)
  4. Report after each phase, wait for approval
  5. Remember the research results for future reference
```

The core loop: **Natural Language → AI Plans → Human Approves → State Machine Executes → AI Reports → Human Reviews**.

---

## Why the Orchestration Layer Is Our Core

Sagitta's orchestration layer — intent parsing, workflow planning, phase state machine, approval gates, cross-session memory, persona — is **implemented from scratch**. No existing agent framework provides it: coding agents (Claude Code, Codex) are single-session execution engines. They execute a task well, but they do not plan multi-phase work, gate phases for review, or remember you between sessions. That gap — long-running, reviewable, rememberable coding workflows — is the pain point Sagitta solves, and the orchestration layer is our unique advantage.

Execution units are **pluggable adapters** behind the bridge layer, not part of the core: complex phases run on Claude Code, cheap phases on model APIs, reviews on a different model family.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│              Sagitta-Agent                   │
│                                              │
│  ┌──────────┐  ┌────────────┐  ┌──────────┐ │
│  │ Persona  │  │  Dialogue  │  │  Memory  │ │  ← Assistant layer: chat, persona, long-term memory
│  │ Layer    │  │  Manager   │  │  (RAG)   │ │
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

The Task Engine is the core differentiator. It wraps coding agents (Claude Code, Codex, DeepSeek) in a state-machine orchestration layer:

1. **Planner** — converts natural language requirements into a structured workflow plan
2. **State Machine** — phase-level execution with ARIS-style gating: `pending → running → done → accepted`; `accepted` requires either cross-model review (Type-B gate) or human approval
3. **Provider Router** — routes each phase to the right model (Claude Code for heavy coding, DeepSeek for cheap analysis, Codex/GPT for cross-model review)
4. **Permission Gate** — three-tier progressive permissions: `minimal` / `analyze` / `execute`

---

## Key Design Decisions

1. **Single Process (for now)** — chat and task execution share one process
2. **High-Agency Persona** — Sagitta has its own opinions: questions unclear instructions, proposes alternatives, remembers past decisions
3. **Natural Language Interface** — no explicit `/task` or `/chat` prefixes; intent is determined from natural language
4. **Full Long-Term Memory** — preferences, past task history, user profile, social habits
5. **Not a Fork — An Orchestration Layer** — Sagitta does not modify its execution units (Claude Code, Codex, model APIs); they are pluggable adapters. The orchestration layer is implemented from scratch — that is the core

---

## Development Phases

| Phase | Scope |
|-------|-------|
| **1: CLI Core** | `sagitta "do something"` — NL to task execution, phase state machine with human gates, provider routing, permission tiers, basic memory |
| **2: Persona & Memory** | High-agency persona, long-term memory with RAG, cross-session continuity, preference learning |
| **3: Social & Multi-Platform** | WeChat/IM integration, proactive check-ins, multi-user support |
| **4: Advanced Autonomy** | Self-initiated tasks, workflow DSL, visual dashboard |

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
