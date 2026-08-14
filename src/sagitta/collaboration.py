"""Durable local collaboration records and registered-project access."""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import PlanningRunStore, StorageError, _read_json, _write_json, _write_text, default_home


REGISTRY_VERSION = 1
MAX_GOAL_STATE_BYTES = 128 * 1024
_PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
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

    def bootstrap_self_hosting(self, workspace: Path) -> dict[str, Any]:
        return self.register_project("sagitta-self-hosting", "Sagitta self-hosting project", workspace, relationship="self_hosting_inner")

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

    def pending_question(self, project_id: str) -> dict[str, Any] | None:
        for record in self._project_runs(project_id):
            if record.get("status") == "needs_input" and isinstance(record.get("response"), dict):
                questions = record["response"].get("questions")
                if isinstance(questions, list) and questions:
                    return {"run_id": record["id"], "question": questions[0]}
        return None

    def read_goal(self, project_id: str, run_id: str) -> dict[str, str]:
        self.plan(project_id, run_id)
        path = PlanningRunStore(self.home).directory_for(run_id) / "goal" / "GOAL.md"
        if not path.is_file():
            raise ProjectError("goal_not_found", "No exported Goal exists for this plan.")
        return {"path": "goal/GOAL.md", "content": path.read_text(encoding="utf-8")}
