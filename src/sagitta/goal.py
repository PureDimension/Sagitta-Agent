"""Compile a ready Plan IR into a paste-ready Codex Goal."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
from typing import Any

from .config import PlanningRunStore, StorageError
from .ir import validate_workflow


class GoalCompilationError(RuntimeError):
    """Raised when a persisted plan cannot be exported as a Goal."""


class GoalService:
    """Export a ready plan as a manual, temporary Codex Goal compatibility bridge."""

    def __init__(self, runs: PlanningRunStore) -> None:
        self.runs = runs

    def export(self, run_id: str) -> tuple[Path, str]:
        try:
            record = self.runs.load(run_id)
        except StorageError as error:
            raise GoalCompilationError(str(error)) from error
        if record.get("status") != "ready":
            raise GoalCompilationError("only a ready planning run can be exported as a Goal")
        try:
            workflow = self.runs.load_ir(run_id)
            validate_workflow(workflow)
        except (StorageError, ValueError) as error:
            raise GoalCompilationError(f"cannot export an invalid Plan IR: {error}") from error

        intent = record.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise GoalCompilationError("planning record has no user intent")
        qa = record.get("qa")
        if not isinstance(qa, list):
            raise GoalCompilationError("planning record has invalid question-and-answer history")

        goal = compile_goal(workflow, intent, qa)
        return self.runs.save_goal(run_id, goal), goal


def compile_goal(workflow: dict[str, Any], intent: str, qa: list[dict[str, Any]]) -> str:
    """Turn validated IR and durable planning context into a self-contained Goal prompt."""
    validate_workflow(workflow)
    return (
        _template()
        .replace("{{TITLE}}", workflow["title"])
        .replace("{{USER_INTENT}}", intent.strip())
        .replace("{{PROJECT_SUMMARY}}", workflow["project_summary"])
        .replace("{{ASSUMPTIONS}}", _bullets(workflow["assumptions"], empty="- None recorded."))
        .replace("{{PLANNING_DECISIONS}}", _format_qa(qa))
        .replace("{{ENTRY_PHASE}}", workflow["entry_phase"])
        .replace("{{WORKFLOW_GRAPH}}", _format_nodes(workflow["phases"]))
    )


def _template() -> str:
    return resources.files("sagitta.prompts").joinpath("goal.md").read_text(encoding="utf-8")


def _bullets(items: list[str], *, empty: str) -> str:
    return "\n".join(f"- {item}" for item in items) if items else empty


def _format_qa(qa: list[dict[str, Any]]) -> str:
    if not qa:
        return "- No planning questions were answered."
    lines: list[str] = []
    for item in qa:
        question = item.get("question")
        answer = item.get("answer")
        if isinstance(question, str) and isinstance(answer, str):
            lines.append(f"- Decision: {question}\n  Answer: {answer}")
    return "\n".join(lines) if lines else "- No usable planning decisions were recorded."


def _format_nodes(nodes: list[dict[str, Any]], depth: int = 0) -> str:
    sections: list[str] = []
    for node in nodes:
        if node["type"] == "scope":
            sections.append(_format_scope(node, depth))
        else:
            sections.append(_format_phase(node, depth))
    return "\n\n".join(sections)


def _format_scope(scope: dict[str, Any], depth: int) -> str:
    heading = "#" * min(6, 3 + depth)
    body = [
        f"{heading} Scope `{scope['id']}`",
        f"Entering this scope starts at `{scope['entry_phase']}` and opens a fresh local counter window.",
        _format_nodes(scope["phases"], depth + 1),
    ]
    return "\n\n".join(body)


def _format_phase(phase: dict[str, Any], depth: int) -> str:
    heading = "#" * min(6, 3 + depth)
    body = [
        f"{heading} Phase `{phase['id']}` — {phase['title']}",
        f"Kind: `{phase['kind']}`. Time budget: {phase['timeout_seconds']} seconds.",
        "Objective:\n" + phase["objective"],
        "Required outputs:\n" + _bullets(phase["outputs"], empty="- None."),
        "Expected postconditions:\n" + _bullets(phase["expected_facts"], empty="- None."),
        "Outcome routing:\n" + _format_outcomes(phase["on"]),
    ]
    return "\n\n".join(body)


def _format_outcomes(outcomes: dict[str, Any]) -> str:
    lines: list[str] = []
    for outcome, route in outcomes.items():
        if isinstance(route, str):
            lines.append(f"- Report `{outcome}` → go to `{route}`.")
            continue
        routes: list[str] = []
        for item in route:
            if "when" in item:
                routes.append(f"when `{item['when']}` → `{item['target']}`")
            else:
                routes.append(f"otherwise → `{item['target']}`")
        lines.append(f"- Report `{outcome}` → " + "; then ".join(routes) + ".")
    return "\n".join(lines)
