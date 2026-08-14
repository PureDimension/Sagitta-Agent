"""The NL-to-Plan-IR planning service."""

from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any, Iterator

import fcntl

from .codex import CodexPlanner
from .config import ConfigStore, PlanningRunStore, StorageError
from .ir import ValidationError, validate_planning_response, validate_workflow


class PlanningError(RuntimeError):
    """Raised when a planning request cannot be started or resumed."""


class PlanBusyError(PlanningError):
    """Raised when another request is already advancing the same Plan."""


MAX_IR_REPAIR_ATTEMPTS = 1
MAX_PRELAUNCH_REVISIONS = 1


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

    def plan(self, intent: str, *, task_id: str | None = None) -> dict[str, Any]:
        record = self.begin(intent, task_id=task_id)
        return self.run_initial(record["id"])

    def begin(self, intent: str, *, task_id: str | None = None) -> dict[str, Any]:
        """Persist a Plan before dispatching its long-running Codex invocation."""
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
            "task_id": task_id,
            "intent": intent,
            "session_id": None,
            "qa": [],
            "response": None,
            "status": "planning",
            "planning_closed": False,
            "codex_call_count": 0,
            "review_call_count": 0,
            "prelaunch_revision_count": 0,
        }
        self.runs.create(record)
        self.runs.prepare_contract_package(run_id)
        self.runs.append_event(run_id, {"at": _now(), "type": "planning_started"})
        return record

    def run_initial(self, run_id: str) -> dict[str, Any]:
        """Run the initial Codex call for a previously persisted planning record."""
        try:
            record = self.runs.load(run_id)
        except StorageError as error:
            raise PlanningError(str(error)) from error
        if record.get("status") != "planning":
            raise PlanningError("planning run is not ready for its initial Codex call")
        workspace = Path(record.get("workspace", ""))
        if not workspace.is_dir():
            raise PlanningError(f"planning workspace is unavailable: {workspace}")
        package_directory = self.runs.directory_for(run_id)
        try:
            result = self.codex.start(
                workspace,
                self._initial_prompt(str(record.get("intent", "")), package_directory),
                package_directory,
            )
            return self._apply_codex_result(record, result, sequence=0, label="initial")
        except Exception as error:
            self._record_planning_failure(record, error)
            raise

    def answer(self, run_id: str, question_id: str, answer: str) -> dict[str, Any]:
        """Resume from one explicit CLI answer without changing the CLI contract."""
        return self._answer_many(run_id, [{"id": question_id, "answer": answer}], require_all=False)

    def answer_many(self, run_id: str, answers: list[dict[str, str]]) -> dict[str, Any]:
        """Atomically record one complete question round and resume Codex once."""
        return self._answer_many(run_id, answers, require_all=True)

    @contextmanager
    def _run_lock(self, run_id: str) -> Iterator[None]:
        path = self.runs.directory_for(run_id) / ".planning.lock"
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise PlanBusyError("This Plan is already processing an answer. Wait for its response before submitting again.") from error
            yield
        finally:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            finally:
                os.close(descriptor)

    def _answer_many(self, run_id: str, answers: list[dict[str, str]], *, require_all: bool) -> dict[str, Any]:
        if not answers:
            raise PlanningError("at least one answer is required")
        normalized: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in answers:
            question_id = item.get("id") if isinstance(item, dict) else None
            answer = item.get("answer") if isinstance(item, dict) else None
            if not isinstance(question_id, str) or not question_id or not isinstance(answer, str) or not answer.strip():
                raise PlanningError("every answer requires a non-empty id and answer")
            if question_id in seen:
                raise PlanningError(f"duplicate answer for pending question: {question_id}")
            seen.add(question_id)
            normalized.append({"id": question_id, "answer": answer.strip()})

        with self._run_lock(run_id):
            return self._resume_answers(run_id, normalized, require_all=require_all)

    def _resume_answers(self, run_id: str, answers: list[dict[str, str]], *, require_all: bool) -> dict[str, Any]:
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
        question_map = {item.get("id"): item for item in questions if isinstance(item, dict) and isinstance(item.get("id"), str)}
        answer_ids = {item["id"] for item in answers}
        unknown = answer_ids - set(question_map)
        if unknown:
            raise PlanningError("unknown pending question: " + ", ".join(sorted(unknown)))
        if require_all and answer_ids != set(question_map):
            missing = set(question_map) - answer_ids
            raise PlanningError("submit one answer for every pending question; missing: " + ", ".join(sorted(missing)))

        qa = list(record.get("qa", []))
        for item in answers:
            question = question_map[item["id"]]
            qa.append({"id": item["id"], "question": question["question"], "answer": item["answer"]})
        workspace = Path(record.get("workspace", ""))
        if not workspace.is_dir():
            raise PlanningError(f"planning workspace is unavailable: {workspace}")
        session_id = record.get("session_id")
        if not isinstance(session_id, str) or not session_id:
            raise PlanningError("planning run has no Codex session id")
        for item in answers:
            self.runs.append_event(run_id, {"at": _now(), "question_id": item["id"], "type": "answer_recorded"})
        try:
            result = self.codex.resume(
                workspace,
                session_id,
                self._answers_prompt(answers, self.runs.directory_for(run_id)),
                self.runs.directory_for(run_id),
            )
            record["qa"] = qa
            return self._apply_codex_result(
                record,
                result,
                sequence=int(record.get("codex_call_count", 0)),
                label="resume",
            )
        except Exception as error:
            record["qa"] = qa
            self._record_planning_failure(record, error)
            raise

    def _record_planning_failure(self, record: dict[str, Any], error: Exception) -> None:
        existing_status = record.get("status")
        status = existing_status if existing_status in {"planning_review_failed", "invalid_ir"} else "planning_failed"
        record.update(
            {
                "updated_at": _now(),
                "status": status,
                "planning_closed": True,
                "last_error": str(error),
                "last_error_type": type(error).__name__,
            }
        )
        self.runs.append_event(
            record["id"],
            {
                "at": _now(),
                "error": str(error),
                "error_type": type(error).__name__,
                "status": status,
                "type": "planning_exception_recorded",
            },
        )
        self.runs.save(record)

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
                "planning_closed": False,
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
            self.runs.save(record)
            return record

        record["status"] = "reviewing_plan"
        self.runs.save(record)
        return self._review_ready_package(record)

    def _review_ready_package(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = record["id"]
        review_sequence = int(record.get("review_call_count", 0))
        workspace = Path(record["workspace"])
        package_directory = self.runs.directory_for(run_id)
        self.runs.append_event(
            run_id,
            {"at": _now(), "review_call": review_sequence, "type": "prelaunch_review_started"},
        )
        self.runs.save(record)
        result = self.codex.review(
            workspace,
            self._prelaunch_review_prompt(record["intent"], package_directory),
            package_directory,
        )
        try:
            review = self._validated_review(result.response)
        except PlanningError as error:
            self.runs.save_review_call(
                run_id,
                review_sequence,
                result.stdout,
                result.stderr,
                result.response,
            )
            record.update(
                {
                    "updated_at": _now(),
                    "review_call_count": review_sequence + 1,
                    "status": "planning_review_failed",
                    "planning_closed": True,
                    "last_validation_error": str(error),
                }
            )
            self.runs.append_event(
                run_id,
                {
                    "at": _now(),
                    "review_call": review_sequence,
                    "type": "invalid_prelaunch_review_received",
                    "validation_error": str(error),
                },
            )
            self.runs.save(record)
            raise
        self.runs.save_review_call(
            run_id,
            review_sequence,
            result.stdout,
            result.stderr,
            review,
        )
        review_path = self.runs.save_prelaunch_review(
            run_id,
            self._format_prelaunch_review(review, review_sequence),
        )
        record.update(
            {
                "updated_at": _now(),
                "review_call_count": review_sequence + 1,
                "prelaunch_review": review,
                "prelaunch_review_path": str(review_path),
            }
        )
        self.runs.append_event(
            run_id,
            {
                "at": _now(),
                "review_call": review_sequence,
                "review_session_id": result.session_id,
                "type": "prelaunch_review_received",
                "verdict": review["verdict"],
            },
        )
        if review["verdict"] == "pass":
            record.update(
                {
                    "status": "ready",
                    "planning_closed": True,
                    "reviewed_package_hashes": self.runs.plan_package_hashes(run_id),
                    "prelaunch_review_sha256": self.runs.file_sha256(review_path),
                }
            )
            record.pop("last_review_findings", None)
            self.runs.append_event(run_id, {"at": _now(), "type": "planning_ready"})
            self.runs.save(record)
            return record

        record["last_review_findings"] = review["findings"]
        revision_count = int(record.get("prelaunch_revision_count", 0))
        if revision_count >= MAX_PRELAUNCH_REVISIONS:
            record.update({"status": "planning_review_failed", "planning_closed": True})
            self.runs.append_event(
                run_id,
                {"at": _now(), "type": "prelaunch_review_exhausted", "review_call": review_sequence},
            )
            self.runs.save(record)
            return record

        record.update(
            {
                "status": "revising_plan",
                "planning_closed": False,
                "prelaunch_revision_count": revision_count + 1,
            }
        )
        self.runs.append_event(
            run_id,
            {
                "at": _now(),
                "type": "prelaunch_revision_started",
                "revision": revision_count + 1,
            },
        )
        self.runs.save(record)
        revised = self.codex.resume(
            workspace,
            record["session_id"],
            self._prelaunch_revision_prompt(review, package_directory),
            package_directory,
        )
        return self._apply_codex_result(
            record,
            revised,
            sequence=int(record.get("codex_call_count", 0)),
            label="resume",
        )

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
    def _validated_review(response: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(response, dict) or set(response) != {"verdict", "summary", "findings"}:
            raise PlanningError("Codex returned an invalid pre-launch review object")
        verdict = response.get("verdict")
        summary = response.get("summary")
        findings = response.get("findings")
        if verdict not in {"pass", "revise"}:
            raise PlanningError("Codex pre-launch review verdict must be pass or revise")
        if not isinstance(summary, str) or not summary.strip():
            raise PlanningError("Codex pre-launch review summary must be non-empty")
        if not isinstance(findings, list):
            raise PlanningError("Codex pre-launch review findings must be an array")
        required_fields = {"id", "location", "problem", "required_change"}
        for index, finding in enumerate(findings):
            if not isinstance(finding, dict) or set(finding) != required_fields:
                raise PlanningError(f"Codex pre-launch review finding {index} has invalid fields")
            if any(not isinstance(finding[field], str) or not finding[field].strip() for field in required_fields):
                raise PlanningError(f"Codex pre-launch review finding {index} must contain non-empty text")
        if verdict == "pass" and findings:
            raise PlanningError("a passing pre-launch review cannot contain findings")
        if verdict == "revise" and not findings:
            raise PlanningError("a revise pre-launch review must contain findings")
        return response

    @staticmethod
    def _planner_template() -> str:
        return resources.files("sagitta.prompts").joinpath("planner.md").read_text(encoding="utf-8")

    @staticmethod
    def _prelaunch_review_template() -> str:
        return resources.files("sagitta.prompts").joinpath("prelaunch_review.md").read_text(encoding="utf-8")

    def _initial_prompt(self, intent: str, package_directory: Path) -> str:
        return (
            self._planner_template()
            .replace("{{TASK}}", intent)
            .replace("{{PLAN_DIRECTORY}}", str(package_directory))
        )

    def _answers_prompt(self, answers: list[dict[str, str]], package_directory: Path) -> str:
        rendered_answers = "\n\n".join(
            f"Question `{item['id']}`:\n{item['answer']}" for item in answers
        )
        return (
            "Continue the same planning task. The user has answered this planning round:\n\n"
            f"{rendered_answers}\n\n"
            "You may inspect the workspace and revise the planning contract package as needed. "
            f"Its only writable planning location is:\n{package_directory}\n\n"
            "Then return a fresh response that follows the output contract."
        )

    def _prelaunch_review_prompt(self, intent: str, package_directory: Path) -> str:
        return (
            self._prelaunch_review_template()
            .replace("{{TASK}}", intent)
            .replace("{{PLAN_DIRECTORY}}", str(package_directory))
        )

    @staticmethod
    def _prelaunch_revision_prompt(review: dict[str, Any], package_directory: Path) -> str:
        findings = "\n\n".join(
            (
                f"- [{finding['id']}] {finding['location']}\n"
                f"  Problem: {finding['problem']}\n"
                f"  Required change: {finding['required_change']}"
            )
            for finding in review["findings"]
        )
        return (
            "Continue the same planning task. A fresh read-only pre-launch reviewer rejected the current "
            "Plan Package. Treat these findings as new observations in the planning ReAct loop; inspect the "
            "workspace again where needed and revise the existing package in place. Do not begin delivery work.\n\n"
            f"Plan Package:\n{package_directory}\n\n"
            f"Review summary:\n{review['summary']}\n\n"
            f"Blocking findings:\n{findings}\n\n"
            "Resolve every finding. If resolution requires a material user decision, return needs_input with the "
            "relevant questions. Otherwise rewrite TASK_CONTRACT.md, affected phase contracts, and ir.json as "
            "needed, then return ready using the normal planning response contract."
        )

    @staticmethod
    def _format_prelaunch_review(review: dict[str, Any], sequence: int) -> str:
        lines = [
            "# Pre-launch Review",
            "",
            f"Review sequence: {sequence}",
            f"Verdict: `{review['verdict']}`",
            "",
            "## Summary",
            "",
            review["summary"],
            "",
            "## Findings",
            "",
        ]
        if not review["findings"]:
            lines.append("None. The Plan Package is approved for unattended Goal export.")
        else:
            for finding in review["findings"]:
                lines.extend(
                    [
                        f"### {finding['id']}",
                        "",
                        f"Location: `{finding['location']}`",
                        "",
                        f"Problem: {finding['problem']}",
                        "",
                        f"Required change: {finding['required_change']}",
                        "",
                    ]
                )
        return "\n".join(lines).rstrip() + "\n"

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
