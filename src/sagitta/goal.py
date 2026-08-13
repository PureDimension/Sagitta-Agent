"""Compile a ready Plan IR into a paste-ready Codex Goal."""

from __future__ import annotations

from importlib import resources
from pathlib import Path
import re
from typing import Any

from .config import PlanningRunStore, StorageError
from .ir import validate_workflow


_COMPARISON = re.compile(
    r"(?P<counter>\$[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*(?P<operator><=|>=|==|!=|<|>)\s*(?P<number>\d+)"
)
_COMPARISON_WORDS = {
    "<": "fewer than",
    "<=": "at most",
    ">": "more than",
    ">=": "at least",
    "==": "exactly",
    "!=": "a number of times other than",
}


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
            _validate_contract_files(workflow, self.runs.directory_for(run_id))
        except (StorageError, ValueError) as error:
            raise GoalCompilationError(f"cannot export an incomplete Plan Package: {error}") from error

        intent = record.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise GoalCompilationError("planning record has no user intent")
        qa = record.get("qa")
        if not isinstance(qa, list):
            raise GoalCompilationError("planning record has invalid question-and-answer history")

        goal = compile_goal(workflow, intent, qa, self.runs.directory_for(run_id))
        return self.runs.save_goal(run_id, goal), goal


def compile_goal(workflow: dict[str, Any], intent: str, qa: list[dict[str, Any]], plan_directory: Path) -> str:
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
        .replace("{{TASK_CONTRACT_PATH}}", str(plan_directory / "TASK_CONTRACT.md"))
        .replace("{{WORKFLOW_GRAPH}}", _format_nodes(workflow["phases"], plan_directory))
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


def _format_nodes(nodes: list[dict[str, Any]], plan_directory: Path, depth: int = 0) -> str:
    sections: list[str] = []
    for node in nodes:
        if node["type"] == "scope":
            sections.append(_format_scope(node, plan_directory, depth))
        else:
            sections.append(_format_phase(node, plan_directory, depth))
    return "\n\n".join(sections)


def _format_scope(scope: dict[str, Any], plan_directory: Path, depth: int) -> str:
    heading = "#" * min(6, 3 + depth)
    body = [
        f"{heading} Scope `{scope['id']}`",
        f"Entering this scope starts at `{scope['entry_phase']}` and opens a fresh local counter window.",
        _format_nodes(scope["phases"], plan_directory, depth + 1),
    ]
    return "\n\n".join(body)


def _format_phase(phase: dict[str, Any], plan_directory: Path, depth: int) -> str:
    heading = "#" * min(6, 3 + depth)
    contract_path = plan_directory / "phases" / f"{phase['id']}.md"
    body = [
        f"{heading} Phase `{phase['id']}` — {phase['title']}",
        f"Kind: `{phase['kind']}`. Time budget: {phase['timeout_seconds']} seconds.",
        (
            "Phase contract:\n"
            "Before beginning or resuming this phase, read and follow "
            f"`{contract_path}`. "
            "It is the source of truth for phase-specific inputs, execution rules, evidence, "
            "gates, recovery, and handoff artifacts."
        ),
        "Objective:\n" + phase["objective"],
        "Required outputs:\n" + _bullets(phase["outputs"], empty="- None."),
        "Expected postconditions:\n" + _bullets(phase["expected_facts"], empty="- None."),
        "Outcome routing:\n" + _format_outcomes(phase["on"], phase["id"]),
    ]
    return "\n\n".join(body)


def _format_outcomes(outcomes: dict[str, Any], current_phase_id: str) -> str:
    lines: list[str] = []
    for outcome, route in outcomes.items():
        if isinstance(route, str):
            lines.append(f"- If you observe `{outcome}`, {_format_target(route)}.")
            continue
        routes: list[str] = []
        for index, item in enumerate(route):
            if "when" in item:
                prefix = "if" if index == 0 else "otherwise, if"
                routes.append(f"{prefix} {_format_condition(item['when'], current_phase_id)}, {_format_target(item['target'])}")
            else:
                routes.append(f"otherwise, {_format_target(item['target'])}")
        lines.append(f"- If you observe `{outcome}`: " + "; ".join(routes) + ".")
    return "\n".join(lines)


def _format_target(target: str) -> str:
    if target == "$complete":
        return "finish the workflow"
    return f"continue with phase or scope `{target}`"


def _format_condition(condition: str, current_phase_id: str) -> str:
    """Compile the intentionally small IR condition language into executor prose."""

    def replace(match: re.Match[str]) -> str:
        counter = match["counter"]
        scope_or_phase, child_or_metric = counter[1:].split(".", maxsplit=1)
        amount = match["number"]
        comparison = _COMPARISON_WORDS[match["operator"]]
        if scope_or_phase == "workflow":
            subject = f"the workflow has entered `{child_or_metric}`"
        elif child_or_metric == "retry":
            subject = f"phase `{current_phase_id}` has directly retried itself"
        else:
            subject = (
                f"this run of scope `{scope_or_phase}` has entered its direct child "
                f"`{child_or_metric}`"
            )
        if match["operator"] == "!=":
            return f"{subject} {comparison} {amount}"
        return f"{subject} {comparison} {amount} times"

    return _COMPARISON.sub(replace, condition)


def _validate_contract_files(workflow: dict[str, Any], plan_directory: Path) -> None:
    paths = [plan_directory / "TASK_CONTRACT.md"]
    paths.extend(plan_directory / "phases" / f"{phase_id}.md" for phase_id in _phase_ids(workflow["phases"]))
    missing = [str(path) for path in paths if not path.is_file() or not path.read_text(encoding="utf-8").strip()]
    if missing:
        raise ValueError("missing required non-empty contracts: " + ", ".join(missing))


def _phase_ids(nodes: list[dict[str, Any]]) -> list[str]:
    phase_ids: list[str] = []
    for node in nodes:
        if node["type"] == "phase":
            phase_ids.append(node["id"])
        else:
            phase_ids.extend(_phase_ids(node["phases"]))
    return phase_ids
