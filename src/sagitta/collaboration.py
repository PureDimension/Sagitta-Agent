"""Durable local collaboration records and registered-project access."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import PlanningRunStore, StorageError, _read_json, _write_json, _write_text, default_home


REGISTRY_VERSION = 1
MAX_GOAL_STATE_BYTES = 128 * 1024
_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_TASK_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_GOAL_STATE_TEXT_KEYS = ("current_phase", "final_result")
_GOAL_STATE_LIST_KEYS = ("entered_nodes",)
_GOAL_STATE_OUTCOMES = "outcomes"
_GOAL_STATE_COVERAGE = "coverage"


class ProjectError(RuntimeError):
    """Raised for a registered-project boundary violation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _goal_state_summary(value: dict[str, Any]) -> dict[str, Any]:
    """Project untrusted Goal data into a bounded presentation contract."""
    summary: dict[str, Any] = {}
    for key in _GOAL_STATE_TEXT_KEYS:
        item = value.get(key)
        if isinstance(item, str):
            summary[key] = item[:500]
    for key in _GOAL_STATE_LIST_KEYS:
        item = value.get(key)
        if isinstance(item, list):
            summary[key] = [entry[:120] for entry in item[:30] if isinstance(entry, str)]
    outcomes = value.get(_GOAL_STATE_OUTCOMES)
    if isinstance(outcomes, list):
        safe_outcomes = []
        for item in outcomes[:30]:
            if not isinstance(item, dict):
                continue
            phase, outcome = item.get("phase"), item.get("outcome")
            if isinstance(phase, str) and isinstance(outcome, str):
                safe_outcomes.append({"phase": phase[:120], "outcome": outcome[:120]})
        summary[_GOAL_STATE_OUTCOMES] = safe_outcomes
    coverage = value.get(_GOAL_STATE_COVERAGE)
    if isinstance(coverage, dict):
        summary[_GOAL_STATE_COVERAGE] = {
            key[:120]: item[:300]
            for key, item in list(coverage.items())[:30]
            if isinstance(key, str) and isinstance(item, str)
        }
    return summary


class CollaborationStore:
    """Owns profile, project registry, transcripts, and safe project-scoped reads."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or default_home()
        self.registry_path = self.home / "projects.json"

    @property
    def profile_path(self) -> Path:
        return self.home / "profile.md"

    def ensure_profile(self) -> Path:
        if not self.profile_path.exists():
            _write_text(self.profile_path, "# Profile\n\nAdd the preferences Sagitta should consider here.\n")
        return self.profile_path

    def read_profile(self) -> str:
        return self.ensure_profile().read_text(encoding="utf-8")

    def write_profile(self, content: str) -> None:
        _write_text(self.profile_path, content)

    def _registry(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": REGISTRY_VERSION, "projects": []}
        try:
            registry = _read_json(self.registry_path)
        except StorageError as error:
            raise ProjectError("invalid_registry", "Sagitta project registry is invalid.") from error
        if registry.get("version") != REGISTRY_VERSION or not isinstance(registry.get("projects"), list):
            raise ProjectError("invalid_registry", "Sagitta project registry has an unsupported schema.")
        return registry

    def _save_registry(self, registry: dict[str, Any]) -> None:
        _write_json(self.registry_path, registry)

    def list_projects(self) -> list[dict[str, Any]]:
        projects: list[dict[str, Any]] = []
        for record in self._registry()["projects"]:
            if not isinstance(record, dict):
                continue
            project_id = record.get("id")
            workspace = record.get("workspace")
            if not isinstance(project_id, str) or not isinstance(workspace, str):
                continue
            projects.append({
                "id": project_id,
                "label": record.get("label", project_id),
                "workspace": workspace,
                "relationship": record.get("relationship", "external"),
                "available": Path(workspace).is_dir(),
            })
        return projects

    def register_project(self, project_id: str, label: str, workspace: Path, *, relationship: str = "external") -> dict[str, Any]:
        if not _PROJECT_ID.fullmatch(project_id):
            raise ProjectError("invalid_project_id", "Project ID must contain lowercase letters, numbers, or hyphens.")
        if not label.strip():
            raise ProjectError("invalid_project", "Project label must be non-empty.")
        resolved = workspace.expanduser().resolve()
        if not resolved.is_dir():
            raise ProjectError("invalid_workspace", "Project workspace must be an existing directory.")
        registry = self._registry()
        existing = next((item for item in registry["projects"] if isinstance(item, dict) and item.get("id") == project_id), None)
        record = {
            "id": project_id,
            "label": label.strip(),
            "workspace": str(resolved),
            "relationship": relationship,
            "created_at": existing.get("created_at", _now()) if isinstance(existing, dict) else _now(),
        }
        if existing is None:
            registry["projects"].append(record)
        elif existing.get("workspace") == str(resolved):
            registry["projects"][registry["projects"].index(existing)] = record
        else:
            raise ProjectError("project_id_conflict", "That project ID is already registered to another workspace.")
        self._save_registry(registry)
        return record

    def register_workspace(self, workspace: Path) -> dict[str, Any]:
        """Register a Finder-selected directory with a stable inferred identity."""
        resolved = workspace.expanduser().resolve()
        if not resolved.is_dir():
            raise ProjectError("invalid_workspace", "Project workspace must be an existing directory.")
        registry = self._registry()
        existing_path = next(
            (
                item for item in registry["projects"]
                if isinstance(item, dict) and item.get("workspace") == str(resolved)
            ),
            None,
        )
        if isinstance(existing_path, dict):
            return existing_path
        label = resolved.name or str(resolved)
        normalized = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        if not normalized:
            normalized = "project-" + hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:8]
        normalized = normalized[:63].rstrip("-") or "project"
        candidate = normalized
        suffix = 2
        used_ids = {item.get("id") for item in registry["projects"] if isinstance(item, dict)}
        while candidate in used_ids:
            tail = f"-{suffix}"
            candidate = normalized[: 63 - len(tail)].rstrip("-") + tail
            suffix += 1
        return self.register_project(candidate, label, resolved)

    def resolve_project(self, project_id: str) -> dict[str, Any]:
        if not _PROJECT_ID.fullmatch(project_id):
            raise ProjectError("invalid_project_id", "Project ID is invalid.")
        record = next((item for item in self._registry()["projects"] if isinstance(item, dict) and item.get("id") == project_id), None)
        if not isinstance(record, dict):
            raise ProjectError("project_not_found", "Registered project was not found.")
        workspace = record.get("workspace")
        if not isinstance(workspace, str):
            raise ProjectError("invalid_project", "Registered project has no workspace.")
        path = Path(workspace)
        if not path.is_dir():
            raise ProjectError("workspace_unavailable", "Registered project workspace is unavailable.")
        return {**record, "workspace": str(path.resolve())}

    def transcript_path(self, project_id: str) -> Path:
        self.resolve_project(project_id)
        return self.home / "conversations" / f"{project_id}.jsonl"

    def summary_path(self, project_id: str) -> Path:
        self.resolve_project(project_id)
        return self.home / "conversation-summaries" / f"{project_id}.md"

    def agent_history_path(self, project_id: str) -> Path:
        self.resolve_project(project_id)
        return self.home / "agent-history" / f"{project_id}.json"

    def read_agent_history(self, project_id: str) -> str | None:
        path = self.agent_history_path(project_id)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write_agent_history(self, project_id: str, history: str) -> None:
        self.agent_history_path(project_id).parent.mkdir(parents=True, exist_ok=True)
        _write_text(self.agent_history_path(project_id), history)

    def append_message(self, project_id: str, role: str, content: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if role not in {"user", "assistant"} or not content.strip():
            raise ProjectError("invalid_message", "Message role and content are required.")
        entry = {"id": str(uuid.uuid4()), "at": _now(), "role": role, "content": content, "metadata": metadata or {}}
        path = self.transcript_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return entry

    def messages(self, project_id: str) -> list[dict[str, Any]]:
        path = self.transcript_path(project_id)
        if not path.exists():
            return []
        messages: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("content"), str):
                messages.append(entry)
        return messages

    def goal_state(self, project_id: str) -> dict[str, Any]:
        project = self.resolve_project(project_id)
        path = Path(project["workspace"]) / ".sagitta-goal-state.json"
        try:
            if not path.exists():
                return {"status": "absent", "message": "No transitional Goal state exists in this workspace."}
            if path.stat().st_size > MAX_GOAL_STATE_BYTES:
                return {"status": "invalid", "message": "Transitional Goal state exceeds the display size limit."}
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, RecursionError):
            return {"status": "invalid", "message": "Transitional Goal state is not valid JSON."}
        if not isinstance(value, dict):
            return {"status": "invalid", "message": "Transitional Goal state must be a JSON object."}
        return {
            "status": "available",
            "state": _goal_state_summary(value),
            "message": "Executor-owned transitional state; Sagitta is not supervising this Goal run.",
        }

    def _project_runs(self, project_id: str) -> list[dict[str, Any]]:
        project = self.resolve_project(project_id)
        runs = PlanningRunStore(self.home)
        if not runs.plans.exists():
            return []
        result: list[dict[str, Any]] = []
        for state_path in runs.plans.glob("*/state.json"):
            try:
                record = _read_json(state_path)
                workspace = record.get("workspace")
                if isinstance(workspace, str) and Path(workspace).resolve() == Path(project["workspace"]).resolve():
                    result.append(record)
            except (StorageError, OSError):
                continue
        return sorted(result, key=lambda record: str(record.get("updated_at", "")), reverse=True)

    def plans(self, project_id: str) -> list[dict[str, Any]]:
        return [{key: record.get(key) for key in ("id", "intent", "status", "updated_at", "response")} for record in self._project_runs(project_id)]

    def plan(self, project_id: str, run_id: str) -> dict[str, Any]:
        record = next((item for item in self._project_runs(project_id) if item.get("id") == run_id), None)
        if not isinstance(record, dict):
            raise ProjectError("plan_not_found", "Plan was not found for this registered project.")
        runs = PlanningRunStore(self.home)
        result = {key: record.get(key) for key in ("id", "intent", "status", "updated_at", "response", "qa")}
        if record.get("status") == "ready":
            try:
                result["ir"] = runs.load_ir(run_id)
            except StorageError:
                result["ir"] = None
        return result

    def delete_plan(self, project_id: str, run_id: str) -> dict[str, str]:
        """Delete a dormant plan package belonging to one registered project."""
        record = next((item for item in self._project_runs(project_id) if item.get("id") == run_id), None)
        if not isinstance(record, dict):
            raise ProjectError("plan_not_found", "Plan was not found for this registered project.")
        if record.get("status") in {"planning", "repairing_ir", "reviewing_plan", "revising_plan"}:
            raise ProjectError("plan_busy", "A running Codex planning session cannot be deleted.")
        runs = PlanningRunStore(self.home)
        directory = runs.directory_for(run_id)
        if directory.parent != runs.plans:
            raise ProjectError("invalid_plan", "Plan package path is outside the local plans directory.")
        if not directory.is_dir():
            raise ProjectError("plan_not_found", "Plan package is unavailable.")
        shutil.rmtree(directory)
        return {"id": run_id, "status": "deleted"}

    def pending_questions(self, project_id: str) -> dict[str, Any] | None:
        for record in self._project_runs(project_id):
            if record.get("status") == "needs_input" and isinstance(record.get("response"), dict):
                questions = record["response"].get("questions")
                if isinstance(questions, list) and questions:
                    return {"run_id": record["id"], "questions": questions}
        return None

    def pending_question(self, project_id: str) -> dict[str, Any] | None:
        """Compatibility helper for callers that still need the first question."""
        pending = self.pending_questions(project_id)
        if pending is None:
            return None
        return {"run_id": pending["run_id"], "question": pending["questions"][0]}

    def plan_artifacts(self, project_id: str, run_id: str) -> list[dict[str, str]]:
        self.plan(project_id, run_id)
        directory = PlanningRunStore(self.home).directory_for(run_id)
        artifacts: list[dict[str, str]] = []

        def add(artifact_id: str, title: str, relative_path: str, kind: str) -> None:
            if (directory / relative_path).is_file():
                artifacts.append({"id": artifact_id, "title": title, "path": relative_path, "kind": kind})

        add("task-contract", "Task contract", "TASK_CONTRACT.md", "markdown")
        for phase_path in sorted((directory / "phases").glob("*.md")):
            add(f"phase:{phase_path.stem}", f"Phase · {phase_path.stem}", str(phase_path.relative_to(directory)), "markdown")
        add("prelaunch-review", "Pre-launch review", "PRELAUNCH_REVIEW.md", "markdown")
        add("workflow", "Workflow IR", "ir.json", "workflow")
        add("planning-state", "Planning state", "state.json", "state")
        add("events", "Planning events", "events.jsonl", "events")
        add("goal", "Codex Goal", "goal/GOAL.md", "goal")
        for trace_directory, title in (("codex", "Codex trace"), ("reviews", "Review trace")):
            for trace_path in sorted((directory / trace_directory).glob("*")):
                if trace_path.is_file():
                    add(
                        f"trace:{trace_directory}:{trace_path.name}",
                        f"{title} · {trace_path.stem}",
                        str(trace_path.relative_to(directory)),
                        "trace",
                    )
        return artifacts

    def read_plan_artifact(self, project_id: str, run_id: str, artifact_id: str) -> dict[str, str]:
        artifact = next((item for item in self.plan_artifacts(project_id, run_id) if item["id"] == artifact_id), None)
        if artifact is None:
            raise ProjectError("artifact_not_found", "Requested Plan artifact was not found.")
        path = PlanningRunStore(self.home).directory_for(run_id) / artifact["path"]
        return {**artifact, "content": path.read_text(encoding="utf-8")}

    def read_goal(self, project_id: str, run_id: str) -> dict[str, str]:
        self.plan(project_id, run_id)
        path = PlanningRunStore(self.home).directory_for(run_id) / "goal" / "GOAL.md"
        if not path.is_file():
            raise ProjectError("goal_not_found", "No exported Goal exists for this plan.")
        return {"path": "goal/GOAL.md", "content": path.read_text(encoding="utf-8")}

    # Tasks are the collaboration and execution boundary. A Project only names
    # a workspace; every user-visible thread, Plan package, and future run is
    # owned by exactly one Task.
    @property
    def tasks_directory(self) -> Path:
        return self.home / "tasks"

    def task_directory(self, task_id: str) -> Path:
        if not _TASK_ID.fullmatch(task_id):
            raise ProjectError("invalid_task_id", "Task ID is invalid.")
        return self.tasks_directory / task_id

    def _task_record(self, task_id: str) -> dict[str, Any]:
        path = self.task_directory(task_id) / "state.json"
        try:
            record = _read_json(path)
        except StorageError as error:
            raise ProjectError("task_not_found", "Task was not found.") from error
        if record.get("id") != task_id or not isinstance(record.get("project_id"), str):
            raise ProjectError("invalid_task", "Task record has an invalid schema.")
        return record

    def _task_summary(self, record: dict[str, Any]) -> dict[str, Any]:
        result = {key: record.get(key) for key in ("id", "project_id", "title", "created_at", "updated_at", "run_id")}
        run_id = record.get("run_id")
        if isinstance(run_id, str):
            try:
                run = PlanningRunStore(self.home).load(run_id)
                result["plan"] = {key: run.get(key) for key in ("id", "intent", "status", "updated_at", "response", "qa")}
            except StorageError:
                result["plan"] = None
        else:
            result["plan"] = None
        return result

    def create_task(self, project_id: str, title: str) -> dict[str, Any]:
        self.resolve_project(project_id)
        if not isinstance(title, str) or not title.strip():
            raise ProjectError("invalid_task", "Task title must be non-empty.")
        task_id = str(uuid.uuid4())
        record = {
            "id": task_id,
            "project_id": project_id,
            "title": title.strip()[:240],
            "created_at": _now(),
            "updated_at": _now(),
            "run_id": None,
        }
        directory = self.task_directory(task_id)
        directory.mkdir(parents=True, exist_ok=False)
        _write_json(directory / "state.json", record)
        return self._task_summary(record)

    def _save_task(self, record: dict[str, Any]) -> None:
        record["updated_at"] = _now()
        _write_json(self.task_directory(str(record["id"])) / "state.json", record)

    def _legacy_task_for_run(self, project_id: str, run: dict[str, Any]) -> dict[str, Any]:
        """Materialize a Task shell for an existing package without changing it."""
        run_id = run.get("id")
        if not isinstance(run_id, str):
            raise ProjectError("invalid_plan", "Plan record has no ID.")
        existing = None
        if self.tasks_directory.exists():
            for path in self.tasks_directory.glob("*/state.json"):
                try:
                    candidate = self._task_record(path.parent.name)
                except ProjectError:
                    continue
                if candidate.get("run_id") == run_id:
                    existing = candidate
                    break
        if isinstance(existing, dict):
            return existing
        task = self.create_task(project_id, str(run.get("intent") or "Imported Plan"))
        record = self._task_record(str(task["id"]))
        record["run_id"] = run_id
        self._save_task(record)
        self._seed_task_conversation(project_id, record)
        return record

    def _seed_task_conversation(self, project_id: str, record: dict[str, Any]) -> None:
        """Give an imported package one readable Task transcript, once only."""
        task_id = record.get("id")
        run_id = record.get("run_id")
        if not isinstance(task_id, str) or not isinstance(run_id, str):
            return
        path = self.task_directory(task_id) / "conversation.jsonl"
        if path.exists():
            return
        try:
            plan = self.plan(project_id, run_id)
        except ProjectError:
            return
        intent = plan.get("intent")
        if isinstance(intent, str) and intent.strip():
            self.append_task_message(project_id, task_id, "user", intent, metadata={"route": "direct", "imported": True})
        for entry in plan.get("qa", []):
            if not isinstance(entry, dict):
                continue
            question = entry.get("question")
            answer = entry.get("answer")
            if isinstance(question, str) and question.strip():
                self.append_task_message(project_id, task_id, "assistant", question, metadata={"route": "direct", "imported": True})
            if isinstance(answer, str) and answer.strip():
                self.append_task_message(project_id, task_id, "user", answer, metadata={"route": "direct", "imported": True})
        response = plan.get("response")
        if isinstance(response, dict):
            summary = response.get("summary")
            questions = response.get("questions")
            parts = [summary] if isinstance(summary, str) and summary.strip() else []
            if isinstance(questions, list) and questions:
                parts.append("Questions to settle before offline work:\n" + "\n".join(
                    f"{index + 1}. {item.get('question', '')}\n   Why: {item.get('reason', '')}"
                    for index, item in enumerate(questions) if isinstance(item, dict)
                ))
            if parts:
                self.append_task_message(project_id, task_id, "assistant", "\n\n".join(parts), metadata={"route": "direct", "imported": True})

    def tasks(self, project_id: str) -> list[dict[str, Any]]:
        self.resolve_project(project_id)
        records: list[dict[str, Any]] = []
        if self.tasks_directory.exists():
            for state_path in self.tasks_directory.glob("*/state.json"):
                try:
                    record = self._task_record(state_path.parent.name)
                except ProjectError:
                    continue
                if record.get("project_id") == project_id:
                    self._seed_task_conversation(project_id, record)
                    records.append(record)
        attached = {record.get("run_id") for record in records}
        for run in self._project_runs(project_id):
            if run.get("id") not in attached:
                records.append(self._legacy_task_for_run(project_id, run))
        return [self._task_summary(record) for record in sorted(records, key=lambda item: str(item.get("updated_at", "")), reverse=True)]

    def task(self, project_id: str, task_id: str) -> dict[str, Any]:
        self.resolve_project(project_id)
        record = self._task_record(task_id)
        if record.get("project_id") != project_id:
            raise ProjectError("task_not_found", "Task was not found for this registered project.")
        return self._task_summary(record)

    def attach_plan(self, project_id: str, task_id: str, run_id: str) -> dict[str, Any]:
        record = self._task_record(task_id)
        if record.get("project_id") != project_id:
            raise ProjectError("task_not_found", "Task was not found for this registered project.")
        if record.get("run_id") is not None:
            raise ProjectError("task_already_planned", "This Task already has a Plan package.")
        self.plan(project_id, run_id)
        record["run_id"] = run_id
        self._save_task(record)
        return self._task_summary(record)

    def task_plan(self, project_id: str, task_id: str) -> dict[str, Any] | None:
        record = self._task_record(task_id)
        if record.get("project_id") != project_id:
            raise ProjectError("task_not_found", "Task was not found for this registered project.")
        run_id = record.get("run_id")
        return self.plan(project_id, run_id) if isinstance(run_id, str) else None

    def task_transcript_path(self, project_id: str, task_id: str) -> Path:
        self.task(project_id, task_id)
        return self.task_directory(task_id) / "conversation.jsonl"

    def task_agent_history_path(self, project_id: str, task_id: str) -> Path:
        self.task(project_id, task_id)
        return self.task_directory(task_id) / "agent-history.json"

    def append_task_message(self, project_id: str, task_id: str, role: str, content: str, *, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if role not in {"user", "assistant"} or not content.strip():
            raise ProjectError("invalid_message", "Message role and content are required.")
        entry = {"id": str(uuid.uuid4()), "at": _now(), "role": role, "content": content, "metadata": metadata or {}}
        path = self.task_transcript_path(project_id, task_id)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True))
            handle.write("\n")
        return entry

    def task_messages(self, project_id: str, task_id: str) -> list[dict[str, Any]]:
        path = self.task_transcript_path(project_id, task_id)
        if not path.exists():
            return []
        messages: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict) and isinstance(entry.get("content"), str):
                messages.append(entry)
        return messages

    def read_task_agent_history(self, project_id: str, task_id: str) -> str | None:
        path = self.task_agent_history_path(project_id, task_id)
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def write_task_agent_history(self, project_id: str, task_id: str, history: str) -> None:
        path = self.task_agent_history_path(project_id, task_id)
        _write_text(path, history)

    def delete_task(self, project_id: str, task_id: str) -> dict[str, str]:
        record = self._task_record(task_id)
        if record.get("project_id") != project_id:
            raise ProjectError("task_not_found", "Task was not found for this registered project.")
        run_id = record.get("run_id")
        if isinstance(run_id, str):
            self.delete_plan(project_id, run_id)
        shutil.rmtree(self.task_directory(task_id))
        return {"id": task_id, "status": "deleted"}
