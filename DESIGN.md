# Sagitta-Agent Design Document

## Problem Statement

Current AI coding workflows suffer from three gaps:

1. **Intent-to-execution gap**: Going from a natural language need ("research agent memory papers") to an executable workflow requires manually selecting skills, configuring parameters, and chaining phases. ARIS has the execution engine but no intent parser.

2. **Memory gap**: Each coding session is isolated. Preferences, past decisions, and project context are lost between invocations. There is no "working relationship" with the AI.

3. **Agency gap**: Coding agents are tools that wait for instructions. They don't question, propose alternatives, remember what you rejected last time, or proactively follow up on incomplete work.

Sagitta addresses all three by adding a persona-driven dialogue layer on top of a state-machine task engine, backed by persistent memory.

---

## Core Loop

```
Human: "Research papers on agent memory systems; check if they can be applied to ARIS"

Step 1 — INTENT PARSING:
  Sagitta: "Do you want: (a) a pure literature review, (b) literature + feasibility
            analysis + integration proposal?"
  Human: "b"

Step 2 — PLANNING:
  Sagitta generates a 4-phase plan:
    1. Literature search (DeepSeek, ~5min)
    2. Feasibility analysis (Claude, ~10min)
    3. Cross-model review (Codex/GPT, ~5min)
    4. Integration proposal (Claude, ~15min)
  Sagitta: "Does this plan look good? Estimated 30 minutes to complete."
  Human: "OK, go ahead"

Step 3 — EXECUTION (autonomous):
  Phase 1 runs → done → auto-proceeds
  Phase 2 runs → done → cross-model review
  Review passes → proceeds
  Phase 3 runs → done → human gate (critical decision)

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
                              cross-model review
                              OR human approval
```

| State | Meaning | Who Sets It |
|-------|---------|------------|
| `pending` | Not started | System |
| `running` | In progress | Executor |
| `done` | Execution complete, artifact exists | Executor (Type-A: machine-checkable) |
| `failed` | Execution errored | Executor |
| `accepted` | Quality verified | Cross-model reviewer OR human (Type-B: requires judgment) |
| `skipped` | Phase not applicable | Human |

### Gate Types

- **Type-A** (machine-checkable): Exit code 0, file exists, counter reached → Can self-judge
- **Type-B** (quality judgment): "Is this correct?", "Is this good enough?" → Must route to different model family
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
| **Codex/GPT (MCP)** | Cross-model review | `review`, `audit`, `validate` |

### Cost Control

- Per-profile daily cost caps (`personal`, `company`, `cheap`)
- Phase-level model selection (lightweight phases use cheap models)
- Token tracking with warnings

---

## Permission System

Three tiers, progressive upgrade:

| Tier | Allowed | Upgrade Condition |
|------|---------|-------------------|
| `minimal` | Read files, call providers | System start |
| `analyze` | Write reports, read-only shell | Human approval per phase |
| `execute` | Full shell, code write, delete | Human approval per phase |

Each workflow phase declares its required permission tier. If current tier is insufficient, the system pauses and requests human approval.

---

## Memory Architecture

### What Sagitta Remembers

| Category | Content | Storage |
|----------|---------|---------|
| **User Profile** | Role, expertise, active projects, preferences | `~/.sagitta/profile.json` |
| **Task History** | Past workflows, decisions, outcomes | Vector DB + metadata |
| **Preference Library** | "Prefers functional style", "Avoids microservices" | Deduced from past feedback |
| **Social Habits** | Working hours, notification tolerance | `~/.sagitta/profile.json` |
| **Project Context** | Per-project codebase knowledge | Per-project `.sagitta/` |

### Retrieval

- Hybrid: BM25 + dense embeddings + local reranker (bge-reranker-v2-m3)
- Fused retrieval with RRF
- Injected into system prompt as context cards

---

## Persona Design

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

## Workflow DSL (Deferred)

The workflow definition language is intentionally deferred. Research areas:
- GitHub Actions-style YAML + expressions
- Makefile-style dependency declarations
- Python decorator-based phase definitions
- Natural language as the canonical representation

The key constraint: the DSL must be both human-readable and AI-generable. The AI should be able to produce a valid workflow from natural language, and the human should be able to read and modify it without learning a new syntax.

---

## Tech Stack

| Component | Choice |
|-----------|--------|
| Agent Engine | pydantic-deepagents |
| State Machine | Custom (Python, ~200 lines) |
| Memory | SQLite + Chroma/FAISS + bge-reranker-v2-m3 |
| CLI | Typer + Rich |
| API | FastAPI (later) |
| Daemon | systemd timer (macOS: launchd) |
| Chat Backend | pydantic-deepagents interactive_chat |

---

## References

- [ARIS AGENT_GUIDE.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/AGENT_GUIDE.md) — Acceptance gates, reviewer routing, artifact contracts
- [ARIS acceptance-gate.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/acceptance-gate.md) — Type-A/Type-B gate taxonomy
- [ARIS fan-out-pattern.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/fan-out-pattern.md) — Sub-agent fan-out patterns
- [ProjectCelis Architecture](https://github.com/PureDimension/Sagitta-Agent) — Cognitive subsystem design (reference for persona layer)
