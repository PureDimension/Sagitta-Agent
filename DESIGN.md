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

## Current Planning Core

```
Human NL + configured workspace
  → Codex planner inspects the workspace and writes its plan contract package
  → may ask focused questions whenever a user decision is needed
  → same Codex session receives each newly supplied answer
  → writes ARIS-style global and phase contracts plus the canonical `ir.json`
  → returns proposed ready; Sagitta validates files and `ir.json` locally
  → fresh read-only Codex reviews outcome gates, coverage, recovery, and terminal paths
  → rejection returns to the original planner as a ReAct observation for one bounded revision
  → persists the reviewed Plan Package, Q&A, planner/reviewer traces, and planning state
```

The repository currently implements this planning core. It does not yet execute a Plan IR.

### Manual Goal compatibility bridge

For immediate manual use, `sagitta goal <plan-id>` compiles a reviewed Plan Package into a self-contained `goal/GOAL.md` for Codex App. Export requires a passing `PRELAUNCH_REVIEW.md`. The Goal links the global and phase contracts, translates navigation to natural language, and adds an ARIS-style execution protocol: initialize state before work, append registered starts/commands/terminals to `.sagitta-goal/RUN_LEDGER.jsonl`, maintain `.sagitta-goal/CHECKPOINT.md`, and reconcile each contract-defined outcome condition before transition. The root `.sagitta-goal-state.json` remains the transitional UI surface. Graph completion can report only `ready_for_human_audit`, `delivery_limited`, or `blocked`. This protocol strengthens the manual fallback; it remains distinct from independent external enforcement, monitoring, or the future DBOS runtime.

### Planning conversation continuity

The initial planner prompt contains the user task and workspace-planning instructions only. When planning returns `needs_input`, Sagitta persists the question and answer, then resumes the same Codex session with only the newly provided answer. Codex retains the prior conversation; Sagitta retains the full Q&A as durable plan state for audit and future execution context, without reinjecting it into the prompt.

### Plan IR v2

The Plan IR is a small, statically validated business graph:

- workflow root: `title`, `goal`, `project_summary`, `assumptions`, `entry_phase`, `phases`;
- a `phase`: `id`, `title`, `kind`, `objective`, `outputs`, `expected_facts`, `timeout_seconds`, `on`;
- a `scope`: `id`, `entry_phase`, child `phases`, used only for real hierarchy or bounded nested loops;
- `on` maps task-specific outcomes directly to phase/scope targets or `$complete`; ordered conditional routes may read runtime counters;
- `outputs` are business artifacts; `expected_facts` are postconditions that should be confirmable after the phase. Neither is an executor self-verdict.

`explore`, `design`, `implement`, `test`, and `review` are equal phase kinds. The IR is deliberately flat: a design, test, or review step becomes an explicit phase when it has its own output, failure path, retry boundary, or navigation decision. Runtime bookkeeping is not represented as business work.

The Plan Package complements the small IR with free-text contracts under `~/.sagitta/plans/<plan-id>/`: `TASK_CONTRACT.md` defines the task-wide source of truth; `phases/<phase-id>.md` defines each phase's concrete inputs, boundaries, evidence, gates, recovery, handoff, and a complete condition for every IR outcome; and `ir.json` is the planner-written workflow. A fresh read-only reviewer checks the package as a whole before `ready`; one rejection may be returned to the original planner session for revision. The final `PRELAUNCH_REVIEW.md`, SHA-256 binding of reviewed package files, and raw reviewer traces preserve that decision. Goal export refuses post-review package changes. This retains ARIS's rich task-specific contract without turning it into a large, low-signal JSON schema.

Runtime owns worktrees, permissions, checkpoints, counters, logs, heartbeats, resource handling, and internal phase status. The IR may declare counter conditions such as `$phase.retry < 2`, but runtime stores and evaluates their values; the execution agent need not see them. A phase's `.retry` counter means a direct transition back to itself only; a repair path that passes through another phase must bound its attempts with a scope or workflow entry counter.

---

## Future Execution Runtime

### Runtime Phase States

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
| `done` | Executor reports that its phase work and declared outputs are complete | Executor |
| `failed` | Execution errored | Executor |
| `accepted` | Declared acceptance policy satisfied | Machine evidence, independent AI review, or human |
| `skipped` | Phase not applicable | Human |

### Acceptance policy

- **Type-A**: machine-observable facts such as exit codes, files, hashes, parsable results, and counters. A phase may decide at its start to create or revise its own focused checker, run it before outcome selection, and leave it for final task-level audit; the later runtime can execute these checks deterministically.
- **Type-B**: quality or correctness judgments such as “is this sufficient?” or “does this claim hold?” These are future acceptance-policy decisions, handled by an explicit review phase, an independent model, or a human as appropriate.
- This distinction governs runtime acceptance provenance. It does not create two kinds of IR nodes and does not replace ordinary graph transitions.

### Resume

- On crash/restart: resolve forward to first non-terminal phase (`done`-but-not-`accepted` is re-validated)
- Future execution state: `.sagitta/runs/<run_id>.json`; current planning state: `~/.sagitta/plans/<plan-id>/state.json`
- Single-writer contract with atomic temp-file replace

---

## Future Provider Router

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

### Current planner CLI

```bash
$ sagitta init --workspace ~/project
$ sagitta plan "Analyze this project's architecture"
$ sagitta answer <plan-id> <question-id> "Use the existing module boundary"
$ sagitta show <plan-id>
```

This CLI creates Plan IRs and exports manual Codex Goals. DBOS compilation and Sagitta-managed task execution are later stages.

### Future Daemon Mode

```bash
$ sagitta --daemon     # Start persistent agent
# Listens on localhost:8123
# Can receive commands via API
# Runs scheduled tasks via systemd timers
```

### Future Social Integration

```
WeChat/QQ → Sagitta Bridge → Intent Router → Task Engine
```

---

## Lightweight Workflow Language

Natural language is the authoring interface; the workflow language is Sagitta's inspectable execution contract. Defining its minimal internal representation is part of Phase 1, even if the public syntax remains experimental.

The implemented planning representation expresses:

- workflow goal and explicit assumptions
- phases, scopes, and explicit navigation
- phase outputs and expected facts
- per-phase timeout
- bounded counter-based retry/navigation conditions

The later runtime adds execution state, deterministic completion checks, permissions, side-effect scope, acceptance policies, and workflow revision metadata. These are deliberately outside the first IR contract.

The language must be human-readable, AI-generable, statically validatable, and small enough that generation is reliable. A running workflow may be revised through a validated patch. The runtime records every revision and re-checks whether completed phases remain valid; an executor may propose a revision but cannot silently rewrite its own acceptance conditions.

---

## Implementation and planned stack

| Component | Current or planned choice |
|-----------|--------------------------|
| Planner | Persistent Codex CLI (`gpt-5.6-sol`, high) with workspace-write for planning, plus fresh read-only Sol-high pre-launch review and one bounded ReAct revision |
| Plan persistence | Python file store under `~/.sagitta/plans/` |
| Plan IR validation | Custom Python validator |
| Manual compatibility bridge | Plan IR → paste-ready Codex App Goal |
| Durable execution | Plan IR → DBOS compiler, then DBOS runtime (planned) |
| Persona and memory | Added after a usable execution path; storage choice undecided |

---

## References

- [ARIS AGENT_GUIDE.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/AGENT_GUIDE.md) — Acceptance gates, reviewer routing, artifact contracts
- [ARIS acceptance-gate.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/acceptance-gate.md) — Type-A/Type-B gate taxonomy
- [ARIS fan-out-pattern.md](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/shared-references/fan-out-pattern.md) — Sub-agent fan-out patterns
- [ProjectCelis Architecture](https://github.com/PureDimension/Sagitta-Agent) — Cognitive subsystem design (reference for persona layer)
