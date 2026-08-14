# Phase 4 — verify MVP

> Historical executor-authored record from the withdrawn first Goal run. It is retained for diagnosis and does not constitute accepted phase evidence.

## Verification inventory

| Check | Result | What it establishes |
| --- | --- | --- |
| `source .venv/bin/activate && python3 -m unittest discover -v` | 35 passed | Original Codex/planning/IR/Goal tests and all collaboration/web tests pass together. |
| `git diff --check` | passed | No whitespace error in the delivery diff. |
| `python3 -m pip wheel --no-deps .` plus wheel inspection | passed | Installed wheel contains `index.html`, `style.css`, and `app.js`. |
| Installed console-script metadata check | passed | `sagitta-web = sagitta.web:main`. |
| PydanticAI actual tool-registration test | passed, no model turn | Installed PydanticAI accepts the real `Agent` plus registered tools; provider execution remains intercepted. |
| Browser loopback audit | passed | No-key inline diagnostic, self-hosting dashboard, bounded state, plan graph/detail, and Goal export/read worked in isolated temporary homes. |

## Requirement facts checked directly

- Existing `init`, `plan`, `answer`, `show`, and `goal` behavior remains covered by the original tests.
- The provider factory uses `OpenAIChatModel` and official `DeepSeekProvider`, checks the key only at real-turn creation, and presents the missing-key diagnostic without a provider call.
- Capturing-agent and fake-Codex tests prove the permitted delegation boundary; planner `needs_input` remains pending until `/answers` submits a user-provided answer.
- Registry and plan routes reject cross-project access; registered IDs gate workspace access.
- Profile, transcript, summary reservation, plan/Goal state, scope graph payload, malformed/absent/untrusted Goal state, package assets, and API-key-sentinel non-leakage have offline test evidence.

## Outcome

The executor selected `all_checks_passed`. That selection was later withdrawn because a passing self-authored test inventory did not prove every contract outcome or required UI behavior.
