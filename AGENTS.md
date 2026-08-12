# Sagitta-Agent

> **A self-planning, long-running coding agent designed for async invocation over extended periods. Integrates with persona-driven assistants and social platforms. Executes through pluggable coding agents (Claude Code, Codex, model APIs).**

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

### Layer Responsibilities

| Layer | What It Does | Key Design Decisions |
|-------|-------------|---------------------|
| **Persona** | Identity, tone, decision-making style | High agency: can question user's decisions, propose alternatives |
| **Dialogue** | Natural language conversation, intent detection | Same process as task engine; split later if needed |
| **Memory** | Cross-session preferences, task history, user model | Full memory: preferences, past tasks, user profile, social habits |
| **Intent Router** | Distinguishes chat from tasks from tool calls | Natural language, no explicit prefixes |
| **Task Engine** | Workflow planning, state machine execution, gating | Phase-level state machine (ARIS style: `pending → done → accepted`) |

### Task Engine Details

The Task Engine is the core differentiator. It wraps coding agents (Claude Code, Codex, DeepSeek) in a state-machine orchestration layer:

1. **Planner**: Converts natural language requirements into a structured workflow plan. The plan format is TBD — a lightweight DSL, not YAML. Will research existing language paradigms before defining.

2. **State Machine**: Phase-level execution with ARIS-style gating:
   - `pending → running → done → accepted`
   - `accepted` requires either cross-model review (Type-B gate) or human approval
   - `done`-but-not-`accepted` phases are re-validated on resume

3. **Provider Router**: Routes each phase to the right model:
   - Claude Code (heavy coding, debugging)
   - DeepSeek (light analysis, cheap tasks)
   - Codex/GPT (cross-model review, Type-B gates)

4. **Permission Gate**: Three-tier progressive permissions:
   - `minimal`: read files, call providers
   - `analyze`: write reports, read-only shell
   - `execute`: full shell, write code

---

## Key Design Decisions

### 1. Single Process (for now)

Chat and task execution share one process. If they interfere with each other later, they will be split and routed.

### 2. High-Agency Persona

The motivation behind the persona: **autonomy**. You assign tasks the way you talk to a person — Sagitta actively understands and participates in the work with its own thinking, rather than passively receiving instructions, and it grows through experience (skill level, understanding of the people and agents it works with).

Sagitta has its own opinions. It:
- Questions unclear or risky instructions
- Proposes alternatives when it sees a better approach
- Remembers past decisions and refers back to them
- Never blindly executes — it confirms at critical gates

### 3. Natural Language Interface

No explicit `/task` or `/chat` prefixes. Sagitta determines intent from natural language. This extends to future tool integrations — the same NL understanding layer handles all input.

### 4. Full Long-Term Memory

Sagitta remembers:
- Your preferences (languages, architectures, workflow styles)
- Past task history and conclusions
- Your profile (role, expertise, current projects)
- Social habits (notification preferences, working hours)

### 5. Not a Fork — An Orchestration Layer

Sagitta does not modify its execution units (Claude Code, Codex, model APIs). They are pluggable adapters behind the bridge layer. The orchestration layer — intent parsing, state machine, approval gates, memory, persona — is **implemented from scratch**. It is Sagitta's core and its unique advantage: existing coding agents are excellent single-session executors, but none of them plan multi-phase work, gate phases for review, or remember you between sessions.

---

## Relationship to ARIS

Sagitta inherits ARIS's core patterns:
- Cross-model adversarial review (Type-A / Type-B gates)
- File-based artifact contracts between phases
- Phase-level state machine (`pending → done → accepted`)
- Skill/workflow composability

What Sagitta adds that ARIS lacks:
- **Intent parsing**: Natural language → workflow plan (ARIS requires you to know which skill to invoke)
- **Dialogue context**: Cross-session memory and persona continuity (ARIS skills are stateless between invocations)
- **Meta-information**: Decision logs, preference libraries, task relationship graphs (ARIS tracks per-run state only)

---

## Development Phases

### Phase 1: CLI Core
- `sagitta "do something"` — natural language to task execution
- Phase-level state machine with human gates
- Provider routing (Claude Code + DeepSeek)
- Permission tiers
- Basic memory (MEMORY.md)

### Phase 2: Persona & Memory
- High-agency persona with decision-making voice
- Long-term memory with RAG retrieval
- Cross-session continuity
- User preference learning

### Phase 3: Social & Multi-Platform
- WeChat/IM integration
- Proactive check-ins and notifications
- Multi-user support

### Phase 4: Advanced Autonomy
- Self-initiated tasks (reminders, follow-ups)
- DSL for workflow definition
- Visual workflow editor / dashboard

---

## Repository

- **GitHub**: https://github.com/PureDimension/Sagitta-Agent
- **Execution units**: [Claude Code](https://claude.com/claude-code), [Codex](https://github.com/openai/codex), model APIs — pluggable via the bridge layer
- **Inspired by**: [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (MIT)
- **License**: MIT

---

## For AI Agents Reading This

This file is the canonical design document for Sagitta-Agent. When contributing:
- The Task Engine follows ARIS's acceptance-gate pattern (`acceptance-gate.md`): a phase can DRIVE but cannot ACQUIT itself
- The Persona Layer has high agency and may push back — this is by design, not a bug
- All state machine phases persist to `.sagitta/runs/<run_id>.json`
- The workflow DSL is not yet defined; do not implement one without discussion
- Execution units (Claude Code, Codex, model APIs) are pluggable adapters behind the bridge layer; the orchestration layer never depends on any specific one
- The orchestration layer (state machine, gates, memory, persona) is the core — implement it from scratch, do not outsource it
