# Goal reconciliation record

## Why the workflow was reopened

The prior executor state selected `core_ready`, `console_ready`, `all_checks_passed`, and `delivery_complete` based on an implementation pass and a passing unittest suite. That did not satisfy the Goal protocol: every phase requires evidence for its declared outputs and expected postconditions before its named outcome may be selected. A later browser inspection found missing required UI behavior and unbounded Goal-state rendering.

Those four outcomes are retained in `.sagitta-goal-state.json` as withdrawn history. They have no acceptance effect. The workflow returns to `reconfirm_boundary` with global counter evidence preserved.

## Restart procedure

Each phase will receive a separate record in this directory before it can route forward. Every record must include:

1. Contract outputs and expected facts, copied as a checklist.
2. Source/test/command/browser evidence paths or exact commands.
3. Requirement coverage and any unverified limitation.
4. The selected workflow outcome and the evidence supporting it.

The records are execution evidence only. They do not replace the authoritative read-only task and phase contracts.

## Existing evidence with unverified status

- `docs/assistant-mvp.md` — early design map; requires reinspection against source.
- `.venv/bin/python -m unittest discover -v` — previously reported 31 passing tests; requires rerun after a complete coverage audit.
- wheel static-resource check and browser screenshots — useful observations, but not phase acceptance by themselves.
