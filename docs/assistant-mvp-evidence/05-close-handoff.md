# Phase 5 — close handoff audit

> Historical executor-authored handoff from the withdrawn first Goal run. It is retained for diagnosis and is not a completion or acceptance record.

## Delivery map

| User requirement | Delivered path/evidence |
| --- | --- |
| PydanticAI outer assistant using DeepSeek and narrow delegation | `src/sagitta/assistant.py`, `tests/test_collaboration.py` provider/tool tests |
| Profile, registry, full transcript, future-summary reservation | `src/sagitta/collaboration.py`, collaboration persistence tests |
| Existing PlanningService/GoalService reuse with explicit answer ownership | `assistant.py`, planner isolation/answer/API/tool tests |
| Local FastAPI + native science-fiction console | `src/sagitta/web.py`, `src/sagitta/web/static/`, isolated browser evidence |
| Selected-project plans, IR graph/details, Goal, and transition state | `web.py`, browser audit, API tests |
| Self-hosting relation and separate application home | `CollaborationStore.bootstrap_self_hosting`, temporary-home tests |
| Package dependencies/resources and clear launch instructions | `pyproject.toml`, `README.md`, wheel/entrypoint check |
| Preserve existing CLI planner/IR/Goal behavior | original test suite under final `unittest discover` |

## Safety audit

- Browser/API access resolves a registered project ID before workspace reads.
- The browser has no source-edit, shell, provider, raw environment, or arbitrary filesystem operation.
- Planner answer is a user API operation; the PydanticAI model has no answer/resume tool.
- Key material is read only in the real-turn factory and is excluded from stores and normal API data. The Goal body remains available only through the selected validated plan because copying that body is the purpose of the manual bridge.
- Goal-state rendering projects untrusted executor state to a bounded known-field summary.

## Operation and limitations audit

`README.md` documents editable install, `sagitta-web`, `127.0.0.1:8123`, `SAGITTA_HOST`/`SAGITTA_PORT`, process-only `DEEPSEEK_API_KEY`, no-key behavior, self-hosting behavior, supported UI actions, profile/transcript locations, and the manual Goal limitation.

The passing evidence is offline-only. No real DeepSeek request was made and no DBOS runtime, Goal supervision, real-time Goal event channel, interruption, or execution acceptance runtime is claimed.

## Final command inventory

The final post-documentation audit runs:

```text
source .venv/bin/activate && python3 -m unittest discover -v
git diff --check
```

The old executor recorded the result in `.sagitta-goal-state.json`; that terminal claim was withdrawn. Current acceptance requires the reviewed contract package and the strengthened ledger/checkpoint protocol.
