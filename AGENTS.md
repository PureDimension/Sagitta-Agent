# Sagitta-Agent

> **A lightweight, self-planning development assistant for durable asynchronous work. It combines a high-agency, persistent persona with an inspectable workflow runtime and pluggable coding agents.**

---

## What Sagitta Is

Sagitta sits between you and coding agents (Claude Code, Codex, DeepSeek). You assign work in natural language as you would to a capable colleague. Sagitta forms its own view, compiles the intent into a lightweight workflow, executes it through explicit state and gates, and comes back only at genuine decision points.

Sagitta is development-focused rather than a universal agent gateway. Its persona is equally fundamental: it develops an understanding of the user and projects while retaining independent judgment shaped by the history and results of working together.

```
You: "Help me research recent papers on agent memory systems, and check if they can be applied to ARIS"

Sagitta:
  1. Parse intent → generate a workflow plan
  2. Compile the intent into an inspectable, editable workflow
  3. Execute phase by phase (analysis → review → implementation → verification)
  4. Advance through explicit gates; interrupt only at real decision points
  5. Learn from the decisions and outcomes for future work
```

The core loop: **Natural Language → Workflow Compilation → Boundary Confirmation → Deterministic Execution → Selective Escalation → Experience**.

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

### Layer Responsibilities

| Layer | What It Does | Key Design Decisions |
|-------|-------------|---------------------|
| **Persona** | Identity, user understanding, independent judgment, growth | High agency: can question user's decisions, propose alternatives, learn from outcomes |
| **Dialogue** | Natural language conversation, intent detection | Same process as task engine; split later if needed |
| **Memory** | User/project understanding, task history, decision outcomes | Structured experience first; selective retrieval as history grows |
| **Intent Router** | Distinguishes chat from tasks from tool calls | Natural language, no explicit prefixes |
| **Task Engine** | Workflow planning, later state-machine execution and gating | Planning IR now; ARIS-style runtime states later |

### Task Engine Details

The Task Engine is the core differentiator. It wraps coding agents (Claude Code, Codex, DeepSeek) in a state-machine orchestration layer:

1. **Planner**: Converts natural language requirements into a structured workflow. The current planning core gives one persistent Codex session workspace-write access to create a per-plan contract package and run short planning checks, persists user decisions, and locally validates the planner-written `ir.json`. A fresh read-only Codex then performs pre-launch review; one rejection returns to the original session as a ReAct observation for bounded revision. Every phase contract defines the evidence conditions for every IR outcome. Planning must not begin delivery work or edit source.

2. **Future State Machine**: Phase-level execution will use ARIS-style gating:
   - `pending → running → done → accepted`
   - `accepted` requires the declared policy: machine evidence, independent AI review, or human approval
   - `done`-but-not-`accepted` phases are re-validated on resume

3. **Future Provider Router**: The durable runtime may later route phases to different models. The current manual Goal bridge performs no execution-model orchestration; the user-selected Codex App model executes the complete Goal. A future router may use:
   - Claude Code (heavy coding, debugging)
   - DeepSeek (light analysis, cheap tasks)
   - Codex/GPT (optional independent execution or review)

4. **Permission Gate**: Three-tier progressive permissions:
   - `minimal`: read files, call providers
   - `analyze`: write reports, read-only shell
   - `execute`: full shell, write code

---

## Key Design Decisions

### 1. Lightweight and Development-Focused

Sagitta implements the smallest coherent control, relationship, and integration surface required for durable development work. Broad model, tool, channel, and lifestyle compatibility is not a goal.

### 2. High-Agency Persona

The motivation behind the persona is **subjectivity and autonomy**. You assign tasks the way you talk to a person. Sagitta actively understands the user and participates with its own thinking rather than passively receiving instructions. It grows through experience: its skill, its understanding of the people and agents around it, and the continuity of its own judgment.

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

### 5. Two Cores, Pluggable Executors

Sagitta does not modify its execution units (Claude Code, Codex, model APIs). They are pluggable adapters. Sagitta owns two cores: the durable workflow runtime and the persistent persona/collaboration model. Existing products solve parts of this problem, but their product goals and architectural trade-offs do not provide this combination in the lightweight, development-focused form Sagitta seeks.

---

## Relationship to ARIS

Sagitta inherits ARIS's core patterns:
- File-based artifact contracts between phases
- Bounded retry and structural fallback rather than unbounded patching
- Future runtime separation between execution completion and acceptance
- Skill/workflow composability

ARIS Type-A / Type-B is a future runtime acceptance-policy distinction. It does not divide the Plan IR into two node classes: `explore`, `design`, `implement`, `test`, and `review` remain equal, explicit business phases.

What Sagitta adds that ARIS lacks:
- **Intent parsing**: Natural language → workflow plan (ARIS requires you to know which skill to invoke)
- **Dialogue context**: Cross-session memory and persona continuity (ARIS skills are stateless between invocations)
- **Meta-information**: Decision logs, preference libraries, task relationship graphs (ARIS tracks per-run state only)

---

## Development Phases

### 1. Implemented: Planning Core
- `sagitta init`, `plan`, `answer`, and `show`
- Codex workspace inspection plus a planner-written Plan Package
- Natural language → locally validated, fresh-context reviewed Plan Package and Plan IR
- Persistent Q&A, planner/reviewer traces, pre-launch verdict, contracts, and ready `ir.json`

### 2. Temporary Execution Bridge
- `sagitta goal <plan-id>` exports a paste-ready Codex App Goal for initial use
- Goal temporarily applies ARIS-style registered ledger/checkpoint/outcome-gate discipline and ends at human audit, limited delivery, or blocked; it is not Sagitta's future runtime

### 3. Durable Execution
- Plan IR → DBOS workflow compiler
- DBOS execution runtime with deterministic output checks

### 4. Sagitta Collaboration Layer
- Persistent persona, task supervision, experience, user/project understanding
- Later model routing, social integration, and visual management

---

## Repository

- **GitHub**: https://github.com/PureDimension/Sagitta-Agent
- **Execution units**: [Claude Code](https://claude.com/claude-code), [Codex](https://github.com/openai/codex), model APIs — pluggable via the bridge layer
- **Inspired by**: [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) (MIT)
- **License**: MIT

---

## For AI Agents Reading This

This file is the canonical design document for Sagitta-Agent. When contributing:
- Sagitta is developed from first principles, but its authors do not need to rediscover mature solutions. Before designing or implementing a subsystem, assess mature open-source implementations and platform capabilities that solve the same bounded problem. If adopting or adapting one offers a clearer, safer, or materially lower-maintenance result than a bespoke design, explain that option and its trade-offs to the author before proceeding. Preserve Sagitta's product semantics where they are core; reuse proven infrastructure where they are not.
- The Task Engine follows ARIS's acceptance-gate pattern (`acceptance-gate.md`): an executor can DRIVE but cannot silently change or acquit its own acceptance policy
- The Persona Layer has high agency and may push back — this is by design, not a bug
- Planning sessions persist at `~/.sagitta/plans/<plan-id>/`; future execution runs will persist separately at `.sagitta/runs/<run-id>.json`
- A ready planning package contains `TASK_CONTRACT.md`, one phase contract at `phases/<phase-id>.md` for every IR phase, planner-written `ir.json`, and a passing `PRELAUNCH_REVIEW.md`; every IR outcome has a matching contract-defined admission condition, while the structured planner response carries only status, summary, and questions
- A Plan IR phase has `outputs` and `expected_facts` as business contracts; runtime state, worktrees, counters, checkpoints, and permissions are not workflow phases
- A minimal workflow language/IR is a Phase 1 design contract; keep it small, inspectable, AI-generable, and statically validatable
- Execution units (Claude Code, Codex, model APIs) are pluggable adapters behind the bridge layer; the orchestration layer never depends on any specific one
- The durable workflow runtime and persistent persona/collaboration model are Sagitta's cores; do not outsource their product semantics to an executor
