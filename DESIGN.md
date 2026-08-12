# Sagitta-Agent Design Document

## Problem Statement

Sagitta is a personal open-source project motivated by a specific way of working that existing products do not provide as a coherent whole. It targets four gaps:

1. **Intent-to-execution gap**: Going from a natural language need ("research agent memory papers") to an executable workflow requires manually selecting skills, configuring parameters, and chaining phases. ARIS has the execution engine but no intent parser.

2. **Control gap**: Goal-driven agents can run for a long time, but their internal plan and critical transitions are commonly controlled by AI judgment rather than an inspectable, revisable state model.

3. **Relationship gap**: Coding sessions rarely grow into a working relationship. The assistant should understand the user and projects over time, remember why decisions were made, and use that experience in future work.

4. **Agency gap**: A useful colleague has independent judgment. Sagitta should question, disagree, propose alternatives, and develop its own decision-making continuity rather than merely reproduce the user's preferences.

Sagitta addresses these gaps with two equally important cores: a persona-driven collaboration layer and a lightweight, durable development task engine. It intentionally avoids the breadth of a universal agent platform.

## Core Identity: A Durable Task Engine and a Subjective Collaborator

Sagitta combines capabilities that are usually separated:

- Natural language is compiled into a small workflow representation that can be inspected, validated, revised, and resumed.
- A deterministic runtime, rather than an executor's confidence, controls phase transitions, permissions, retries, and escalation.
- A persistent persona understands the user while retaining independent judgment shaped by the history and outcomes of their work together.

The persona is not a tone preset. It is the continuity of Sagitta's understanding, decisions, disagreements, and growth. The task engine supplies the concrete work through which that continuity develops.

Execution units are **pluggable adapters** behind the bridge layer, never part of the core. Complex phases may run on Claude Code and cheap phases on model APIs. Independent or cross-model review can be introduced where its value justifies its cost; it is not part of the minimum execution path. Swapping or adding an execution unit must not require changes to Sagitta's workflow or persona semantics.

---

## Core Loop

```
Human: "Research papers on agent memory systems; check if they can be applied to ARIS"

Step 1 — INTENT AND WORKFLOW COMPILATION:
  Sagitta generates a 4-phase plan:
    1. Literature search (DeepSeek, ~5min)
    2. Feasibility analysis (Claude, ~10min)
    3. Evidence review (configured reviewer, ~5min)
    4. Integration proposal (Claude, ~15min)
  Sagitta records its assumptions and asks only about a boundary that would materially
  change the result.
  Sagitta: "I will include feasibility analysis and an integration proposal. The run can
            write reports but not modify ARIS. Proceed?"
  Human: "OK, go ahead"

Step 3 — EXECUTION (autonomous):
  Phase 1 runs → done → auto-proceeds
  Phase 2 runs → done → configured evidence review
  Evidence gate passes → proceeds
  Phase 3 runs → done → human gate only if a real product decision remains

Step 4 — REPORTING:
  Sagitta: "Found 15 papers, 3 highly relevant. Feasibility: both Option A (direct
            integration) and Option B (wrapper layer) work; the reviewer recommends B.
            Full report at ~/sagitta/reports/2026-08-11-agent-memory.md.
            Want to discuss implementing Option B now?"
```

---

## State Machine

### Phase States

```
pending ──→ running ──→ done ──→ accepted
                  │                ↑
                  └──→ failed      │
                              declared acceptance policy
                              (evidence / AI / human)
```

| State | Meaning | Who Sets It |
|-------|---------|------------|
| `pending` | Not started | System |
| `running` | In progress | Executor |
| `done` | Execution complete, artifact exists | Executor (Type-A: machine-checkable) |
| `failed` | Execution errored | Executor |
| `accepted` | Declared acceptance policy satisfied | Machine evidence, independent AI review, or human |
| `skipped` | Phase not applicable | Human |

### Gate Types

- **Type-A** (machine-checkable): Exit code 0, file exists, counter reached → Can self-judge
- **Type-B** (quality judgment): "Is this correct?", "Is this good enough?" → Route according to policy: an independent AI context, an optional different model family, or a human
- **Human**: Pause and wait for explicit human approval

### Resume

- On crash/restart: resolve forward to first non-terminal phase (`done`-but-not-`accepted` is re-validated)
- State file: `.sagitta/runs/<run_id>.json`
- Single-writer contract with atomic temp-file replace

---

## Provider Router

| Provider | Role | Typical Phase Types |
|----------|------|-------------------|
| **Claude Code** (subprocess) | Heavy coding, debugging, refactoring | `implement`, `debug`, `refactor` |
| **DeepSeek API** | Light analysis, cheap tasks | `analyze`, `summarize`, `search` |
| **Codex/GPT (MCP)** | Optional independent execution or review | `review`, `audit`, `validate` |

### Cost Control

- Per-run and per-profile cost caps (`personal`, `company`, `cheap`)
- Phase-level model selection (lightweight phases use cheap models)
- Planner, execution, retry, review, and context budgets tracked separately
- Token efficiency is a design goal to be measured against direct agent use, not assumed from architecture alone

---

## Permission System

Three tiers, progressive upgrade:

| Tier | Allowed | Upgrade Condition |
|------|---------|-------------------|
| `minimal` | Read files, call providers | System start |
| `analyze` | Write reports, read-only shell | Run-level grant or escalation |
| `execute` | Full shell, code write, delete | Scoped grant; destructive or expanded scope escalates |

Each workflow phase declares its required permission tier. Permissions granted for a run remain valid within their declared scope; Sagitta interrupts only when a phase exceeds that scope or requests a separately classified high-risk action.

---

## Memory Architecture

### What Sagitta Remembers

| Category | Content | Storage |
|----------|---------|---------|
| **Persona State** | Sagitta's stable identity, current judgments, and unresolved questions | Structured local store |
| **User Model** | Role, expertise, active projects, preferences, and interaction history | `~/.sagitta/profile.json` |
| **Task History** | Past workflows, decisions, outcomes | Structured log + optional retrieval index |
| **Decision Experience** | What was proposed, accepted or rejected, why, and with what result | Structured decision log |
| **Social Habits** | Working hours, notification tolerance | `~/.sagitta/profile.json` |
| **Project Context** | Per-project codebase knowledge | Per-project `.sagitta/` |

### Retrieval and Learning

- Begin with explicit structured state and decision records; do not require a vector stack for Phase 1.
- Add hybrid retrieval when the accumulated history is large enough to justify it.
- Retrieved context must preserve source, scope, confidence, and whether later outcomes supported or superseded it.
- Learning changes future judgment and planning; it must not silently weaken workflow gates or permissions.

---

## Persona Design

### Motivation: Why Persona?

The persona is not decoration or a style prompt. It exists so Sagitta can behave like a **continuing subject and colleague rather than a disposable tool session**:

- **Assign tasks the way you talk to a person.** You describe intent and context; Sagitta decides how to carry it out — not how to execute a command.
- **Active understanding and participation.** Sagitta proactively understands the work, joins in with its own thinking, and questions what does not make sense. It is never a passive receiver of instructions.
- **Understanding others.** Sagitta develops a model of the user, projects, and other agents through continued work, including the reasons behind preferences and decisions.
- **Independent judgment.** Sagitta can form conclusions that differ from the user's current view and explain them honestly.
- **Growth through experience.** Outcomes refine Sagitta's future decisions rather than merely adding more text to a memory store.

The goal: an agent that **works with you, not just for you**.

### Core Traits

- **High agency**: Questions unclear instructions, proposes alternatives, remembers past rejections
- **Concise**: "One line is enough, no fluff"
- **Persistent**: Remembers and references past interactions
- **Honest**: Admits uncertainty, doesn't pretend to know

### Decision Voice

When Sagitta disagrees or sees a problem:

```
User: "Delete all the experiment code and rewrite it"
Sagitta: "All of it? The experiment/v2 results passed review — deleting them loses that.
          I suggest rewriting only experiment/v3 and keeping v2.
          Confirm if you really want everything deleted."
```

### Persistence

When Sagitta hasn't heard from you:

```
Sagitta: "Monday's paper analysis is 2/3 done; you've been offline since Tuesday.
          Say the word and I'll continue. Otherwise I'll archive the current progress."
```

---

## Interaction Flow

### Phase 1: CLI Only

```bash
$ sagitta "Analyze the architecture of ~/project"
# Sagitta asks clarifying questions
# Sagitta proposes a plan
# User approves
# Sagitta executes autonomously with status updates
# Sagitta reports when done

$ sagitta --status     # Check current run status
$ sagitta --approve    # Approve current phase
$ sagitta --resume     # Resume last run
```

### Phase 2: Daemon Mode

```bash
$ sagitta --daemon     # Start persistent agent
# Listens on localhost:8123
# Can receive commands via API
# Runs scheduled tasks via systemd timers
```

### Phase 3: Social Integration

```
WeChat/QQ → Sagitta Bridge → Intent Router → Task Engine
```

---

## Lightweight Workflow Language (Phase 1)

Natural language is the authoring interface; the workflow language is Sagitta's inspectable execution contract. Defining its minimal internal representation is part of Phase 1, even if the public syntax remains experimental.

The first version should express only:

- workflow goal and explicit assumptions
- phases and dependencies
- executor capability rather than a hard-coded provider
- produced artifacts
- acceptance gates
- permissions and side-effect scope
- retry and token budgets
- failure and escalation behavior
- workflow revision metadata

The language must be human-readable, AI-generable, statically validatable, and small enough that generation is reliable. A running workflow may be revised through a validated patch. The runtime records every revision and re-checks whether completed phases remain valid; an executor may propose a revision but cannot silently rewrite its own acceptance conditions.

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Execution Units | Claude Code (subprocess), Codex, DeepSeek API — pluggable adapters behind the bridge layer |
| State Machine | Custom (Python, ~200 lines) |
| Memory | SQLite + Chroma/FAISS + bge-reranker-v2-m3 |
| CLI | Typer + Rich |
| API | FastAPI (later) |
| Daemon | systemd timer (macOS: launchd) |

---

## References

- [ARIS AGENT_GUIDE.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/AGENT_GUIDE.md) — Acceptance gates, reviewer routing, artifact contracts
- [ARIS acceptance-gate.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/acceptance-gate.md) — Type-A/Type-B gate taxonomy
- [ARIS fan-out-pattern.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/fan-out-pattern.md) — Sub-agent fan-out patterns
- [ProjectCelis Architecture](https://github.com/PureDimension/Sagitta-Agent) — Cognitive subsystem design (reference for persona layer)
