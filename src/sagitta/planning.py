"""The NL-to-Plan-IR planning service."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

from .codex import CodexPlanner
from .config import ConfigStore, PlanningRunStore, StorageError
from .ir import ValidationError, validate_planning_response, validate_workflow


class PlanningError(RuntimeError):
    """Raised when a planning request cannot be started or resumed."""


MAX_IR_REPAIR_ATTEMPTS = 1


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


class PlanningService:
    def __init__(
        self,
        config: ConfigStore,
        runs: PlanningRunStore,
        codex: CodexPlanner,
    ) -> None:
        self.config = config
        self.runs = runs
        self.codex = codex

    def plan(self, intent: str) -> dict[str, Any]:
        if not intent.strip():
            raise PlanningError("intent must be non-empty")
        try:
            workspace = Path(self.config.load()["workspace"])
        except StorageError as error:
            raise PlanningError(str(error)) from error

        run_id = str(uuid.uuid4())
        record = {
            "id": run_id,
            "created_at": _now(),
            "updated_at": _now(),
            "workspace": str(workspace),
            "intent": intent,
            "session_id": None,
            "qa": [],
            "response": None,
            "status": "planning",
            "planning_closed": False,
            "codex_call_count": 0,
        }
        self.runs.create(record)
        package_directory = self.runs.prepare_contract_package(run_id)
        self.runs.append_event(run_id, {"at": _now(), "type": "planning_started"})
        result = self.codex.start(workspace, self._initial_prompt(intent, package_directory), package_directory)
        return self._apply_codex_result(record, result, sequence=0, label="initial")

    def answer(self, run_id: str, question_id: str, answer: str) -> dict[str, Any]:
        if not answer.strip():
            raise PlanningError("answer must be non-empty")
        try:
            record = self.runs.load(run_id)
        except StorageError as error:
            raise PlanningError(str(error)) from error
        if record.get("status") != "needs_input":
            raise PlanningError("planning run is not waiting for an answer")
        response = record.get("response")
        questions = response.get("questions") if isinstance(response, dict) else None
        if not isinstance(questions, list):
            raise PlanningError("planning run has no pending questions")
        question = next((item for item in questions if item.get("id") == question_id), None)
        if not isinstance(question, dict):
            raise PlanningError(f"unknown pending question: {question_id}")

        qa = list(record.get("qa", []))
        qa.append({"id": question_id, "question": question["question"], "answer": answer})
        workspace = Path(record.get("workspace", ""))
        if not workspace.is_dir():
            raise PlanningError(f"planning workspace is unavailable: {workspace}")
        session_id = record.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise PlanningError("planning run has no Codex session id")
        self.runs.append_event(
            run_id,
            {"at": _now(), "question_id": question_id, "type": "answer_recorded"},
        )
        result = self.codex.resume(
            workspace,
            session_id,
            self._answer_prompt(question_id, answer, self.runs.directory_for(run_id)),
            self.runs.directory_for(run_id),
        )
        record["qa"] = qa
        return self._apply_codex_result(
            record,
            result,
            sequence=int(record.get("codex_call_count", 0)),
            label="resume",
        )

    def _apply_codex_result(
        self,
        record: dict[str, Any],
        result: Any,
        sequence: int,
        label: str,
        repair_attempt: int = 0,
    ) -> dict[str, Any]:
        run_id = record["id"]
        try:
            response = self._validated_response(result.response)
            if response["status"] == "ready":
                workflow = self._load_written_workflow(run_id)
                self._validate_contract_package(run_id, workflow)
        except PlanningError as error:
            return self._repair_invalid_ir(
                record,
                result,
                sequence,
                label,
                repair_attempt,
                error,
            )
        self.runs.save_codex_call(
            run_id,
            sequence,
            label,
            result.stdout,
            result.stderr,
            response,
        )
        status = response["status"]
        record.update(
            {
                "updated_at": _now(),
                "session_id": result.session_id,
                "response": response,
                "status": status,
                "planning_closed": status == "ready",
                "codex_call_count": sequence + 1,
            }
        )
        record.pop("last_validation_error", None)
        self.runs.append_event(
            run_id,
            {
                "at": _now(),
                "codex_call": sequence,
                "session_id": result.session_id,
                "status": status,
                "type": "codex_response_received",
            },
        )
        if status == "needs_input":
            for question in response["questions"]:
                self.runs.append_event(
                    run_id,
                    {"at": _now(), "question_id": question["id"], "type": "question_asked"},
                )
        else:
            self.runs.append_event(run_id, {"at": _now(), "type": "planning_ready"})
        self.runs.save(record)
        return record

    def _repair_invalid_ir(
        self,
        record: dict[str, Any],
        result: Any,
        sequence: int,
        label: str,
        repair_attempt: int,
        error: PlanningError,
    ) -> dict[str, Any]:
        run_id = record["id"]
        self.runs.save_codex_call(
            run_id,
            sequence,
            label,
            result.stdout,
            result.stderr,
            result.response,
        )
        record.update(
            {
                "updated_at": _now(),
                "session_id": result.session_id,
                "status": "repairing_ir",
                "planning_closed": False,
                "codex_call_count": sequence + 1,
                "last_validation_error": str(error),
            }
        )
        self.runs.append_event(
            run_id,
            {
                "at": _now(),
                "codex_call": sequence,
                "repair_attempt": repair_attempt,
                "type": "invalid_ir_received",
                "validation_error": str(error),
            },
        )
        self.runs.save(record)
        if repair_attempt >= MAX_IR_REPAIR_ATTEMPTS:
            record["status"] = "invalid_ir"
            self.runs.save(record)
            raise error

        workspace = Path(record["workspace"])
        repaired = self.codex.resume(
            workspace,
            result.session_id,
            self._repair_prompt(str(error), self.runs.directory_for(run_id)),
            self.runs.directory_for(run_id),
        )
        return self._apply_codex_result(
            record,
            repaired,
            sequence=sequence + 1,
            label="resume",
            repair_attempt=repair_attempt + 1,
        )

    @staticmethod
    def _validated_response(response: dict[str, Any]) -> dict[str, Any]:
        try:
            return validate_planning_response(response)
        except ValidationError as error:
            raise PlanningError(f"Codex returned an invalid planning response: {error}") from error

    @staticmethod
    def _planner_template() -> str:
        return resources.files("sagitta.prompts").joinpath("planner.md").read_text(encoding="utf-8")

    def _initial_prompt(self, intent: str, package_directory: Path) -> str:
        return (
            self._planner_template()
            .replace("{{TASK}}", intent)
            .replace("{{PLAN_DIRECTORY}}", str(package_directory))
        )

    def _answer_prompt(self, question_id: str, answer: str, package_directory: Path) -> str:
        return (
            "Continue the same planning task. The user has answered the pending planning question "
            f"`{question_id}`:\n\n{answer}\n\n"
            "You may inspect the workspace and revise the planning contract package as needed. "
            f"Its only writable planning location is:\n{package_directory}\n\n"
            "Then return a fresh response that follows the output contract."
        )

    def _validate_contract_package(self, run_id: str, workflow: dict[str, Any]) -> None:
        expected = [self.runs.task_contract_path(run_id)]
        expected.extend(self.runs.phase_contract_path(run_id, phase_id) for phase_id in _phase_ids(workflow["phases"]))
        missing = [str(path) for path in expected if not path.is_file() or not path.read_text(encoding="utf-8").strip()]
        if missing:
            raise PlanningError("Codex did not write the required non-empty planning contracts: " + ", ".join(missing))

    def _load_written_workflow(self, run_id: str) -> dict[str, Any]:
        path = self.runs.directory_for(run_id) / "ir.json"
        try:
            workflow = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as error:
            raise PlanningError(f"Codex did not write the required IR file: {path}") from error
        except json.JSONDecodeError as error:
            raise PlanningError(f"Codex wrote invalid JSON to {path}: {error}") from error
        try:
            return validate_workflow(workflow)
        except ValidationError as error:
            raise PlanningError(f"Codex wrote an invalid workflow to {path}: {error}") from error

    @staticmethod
    def _repair_prompt(validation_error: str, package_directory: Path) -> str:
        return (
            "Your previous final JSON did not satisfy Sagitta's local workflow IR validator. "
            "Keep the same task understanding and planning intent, correct any affected planning contracts in this directory, "
            f"then return a corrected replacement JSON object only:\n{package_directory}\n\n"
            "Do not explain the correction or ask a new question unless the prior response already required user input.\n\n"
            f"Validation error:\n{validation_error}"
        )


def _phase_ids(nodes: list[dict[str, Any]]) -> list[str]:
    phase_ids: list[str] = []
    for node in nodes:
        if node["type"] == "phase":
            phase_ids.append(node["id"])
        else:
            phase_ids.extend(_phase_ids(node["phases"]))
    return phase_ids


def record_for_display(record: dict[str, Any]) -> str:
    """Return a stable JSON representation for CLI output."""
    return json.dumps(record, ensure_ascii=False, indent=2)
