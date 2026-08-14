# Phase 3 — local console

> Historical executor-authored record from the withdrawn first Goal run. It is retained for diagnosis and does not constitute accepted phase evidence.

## Contract checklist

| Required output/fact | Evidence | Result |
| --- | --- | --- |
| Packageable FastAPI/ASGI loopback console and native assets | `sagitta.web.create_app`, `sagitta-web` entry point, `src/sagitta/web/static/` | Confirmed. |
| Project list/detail/register, profile, conversation, planner-answer, plans, Goal, and transitional-state API | `tests/test_collaboration.py`; source route audit | Confirmed. |
| UI includes cards, selected workspace, profile, chat, explicit pending answer, plans, graph, node details, Goal controls, and Goal-state display | Browser DOM/UI audit on isolated loopback ports 8126/8127 | Confirmed. |
| Browser cannot start Codex planning directly | Removed `POST /api/projects/{id}/plans` and planner form; API regression returns 405 | Confirmed. |
| Graph is presentation only | Graph test proves scopes/phases/outcomes are represented while route `when` expressions are absent | Confirmed. |
| Goal data remains project-isolated and structured response does not expose plan-home path | Cross-project request test; `goal/GOAL.md` response path regression test | Confirmed. The validated Goal body intentionally includes contract paths because it is the copied executor prompt. |
| Transitional state handles absent, malformed, and untrusted unknown fields safely | Store/API tests and browser display of bounded projection | Confirmed. |
| Missing key has useful local UX | Browser submitted a local no-key chat on port 8126 and displayed `DEEPSEEK_API_KEY is not configured. Run: export DEEPSEEK_API_KEY=...` inline | Confirmed. |

## Browser evidence

An isolated temporary-home server was launched on `127.0.0.1:8126`; the browser loaded the self-hosting dashboard, profile, conversation-first planner guidance, and bounded Goal-state summary. A separate temporary ready Plan Package on port 8127 verified plan-card selection, phase title/kind/objective/outputs/facts/outcomes, and Goal export/read in the actual UI.

## Commands and results

```text
.venv/bin/python -m unittest tests.test_collaboration -v -> 10 tests passed
git diff --check                                       -> passed
```

## Outcome

The executor selected `console_ready`. That selection was later withdrawn because a later browser inspection found uncovered required behavior. The observations above remain diagnostic inputs only.
