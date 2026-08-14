"""Persistent local configuration and planning-run records."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any


class StorageError(RuntimeError):
    """Raised when a Sagitta configuration or planning record is unavailable."""


def default_home() -> Path:
    return Path.home() / ".sagitta"


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _write_private_json(path: Path, value: dict[str, Any]) -> None:
    """Atomically write credentials with owner-only permissions."""
    _write_json(path, value)
    os.chmod(path, 0o600)


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise StorageError(f"missing file: {path}") from error
    except json.JSONDecodeError as error:
        raise StorageError(f"invalid JSON in {path}: {error}") from error
    if not isinstance(value, dict):
        raise StorageError(f"expected a JSON object in {path}")
    return value


class ConfigStore:
    """Stores the single v1 RunConfig: a configured workspace."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or default_home()
        self.path = self.home / "config.json"

    def save_workspace(self, workspace: Path) -> dict[str, str]:
        resolved = workspace.expanduser().resolve()
        if not resolved.is_dir():
            raise StorageError(f"workspace is not a directory: {resolved}")
        config = {"workspace": str(resolved)}
        _write_json(self.path, config)
        return config

    def load(self) -> dict[str, str]:
        config = _read_json(self.path)
        workspace = config.get("workspace")
        if not isinstance(workspace, str) or not workspace:
            raise StorageError(f"config has no workspace: {self.path}")
        path = Path(workspace)
        if not path.is_dir():
            raise StorageError(f"configured workspace is unavailable: {path}")
        return {"workspace": str(path)}


class ModelSettingsStore:
    """Local OpenAI-compatible model settings for the Sagitta collaboration agent."""

    default_model = "deepseek-chat"

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or default_home()
        self.path = self.home / "model.json"

    def _stored(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        return _read_json(self.path)

    def effective(self) -> dict[str, str | None]:
        stored = self._stored()
        model = stored.get("model")
        base_url = stored.get("base_url")
        api_key = stored.get("api_key")
        if not isinstance(model, str) or not model.strip():
            model = os.environ.get("SAGITTA_MODEL") or self.default_model
        if not isinstance(base_url, str) or not base_url.strip():
            base_url = os.environ.get("DEEPSEEK_BASE_URL") or None
        if not isinstance(api_key, str) or not api_key.strip():
            api_key = os.environ.get("DEEPSEEK_API_KEY") or None
        return {"model": model.strip(), "base_url": base_url.strip() if isinstance(base_url, str) else None, "api_key": api_key.strip() if isinstance(api_key, str) else None}

    def display(self) -> dict[str, Any]:
        effective = self.effective()
        return {
            "model": effective["model"],
            "base_url": effective["base_url"] or "",
            "api_key_configured": bool(effective["api_key"]),
        }

    def save(self, *, model: str, base_url: str, api_key: str | None, clear_api_key: bool = False) -> dict[str, Any]:
        if not model.strip():
            raise StorageError("model must be non-empty")
        normalized_base_url = base_url.strip()
        if normalized_base_url and not normalized_base_url.startswith(("https://", "http://")):
            raise StorageError("base_url must start with http:// or https://")
        stored = self._stored()
        stored["model"] = model.strip()
        stored["base_url"] = normalized_base_url
        if clear_api_key:
            stored.pop("api_key", None)
        elif api_key is not None and api_key.strip():
            stored["api_key"] = api_key.strip()
        _write_private_json(self.path, stored)
        return self.display()


class PlanningRunStore:
    """Persists each planning session as an inspectable local plan directory."""

    def __init__(self, home: Path | None = None) -> None:
        self.home = home or default_home()
        self.plans = self.home / "plans"

    def directory_for(self, run_id: str) -> Path:
        if not run_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in run_id):
            raise StorageError(f"invalid planning run id: {run_id!r}")
        return self.plans / run_id

    def path_for(self, run_id: str) -> Path:
        """Return the current-state path for compatibility with simple callers."""
        return self.directory_for(run_id) / "state.json"

    def create(self, record: dict[str, Any]) -> None:
        run_id = record.get("id")
        if not isinstance(run_id, str):
            raise StorageError("planning record has no id")
        directory = self.directory_for(run_id)
        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError as error:
            raise StorageError(f"planning run already exists: {run_id}") from error
        _write_json(directory / "state.json", record)

    def prepare_contract_package(self, run_id: str) -> Path:
        """Create the planner-writable contract locations for one planning run."""
        directory = self.directory_for(run_id)
        if not directory.is_dir():
            raise StorageError(f"planning run is unavailable: {run_id}")
        (directory / "phases").mkdir(exist_ok=True)
        return directory

    def task_contract_path(self, run_id: str) -> Path:
        return self.directory_for(run_id) / "TASK_CONTRACT.md"

    def phase_contract_path(self, run_id: str, phase_id: str) -> Path:
        return self.directory_for(run_id) / "phases" / f"{phase_id}.md"

    def prelaunch_review_path(self, run_id: str) -> Path:
        return self.directory_for(run_id) / "PRELAUNCH_REVIEW.md"

    def save(self, record: dict[str, Any]) -> None:
        run_id = record.get("id")
        if not isinstance(run_id, str):
            raise StorageError("planning record has no id")
        _write_json(self.path_for(run_id), record)

    def load(self, run_id: str) -> dict[str, Any]:
        return _read_json(self.path_for(run_id))

    def append_event(self, run_id: str, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise StorageError("planning event must be an object")
        path = self.directory_for(run_id) / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True))
            handle.write("\n")

    def save_codex_call(
        self,
        run_id: str,
        sequence: int,
        label: str,
        stdout: str,
        stderr: str,
        response: dict[str, Any],
    ) -> None:
        if sequence < 0:
            raise StorageError("Codex call sequence must be non-negative")
        if label not in {"initial", "resume"}:
            raise StorageError(f"unknown Codex call label: {label}")
        prefix = self.directory_for(run_id) / "codex" / f"{sequence:03d}-{label}"
        _write_text(prefix.with_suffix(".events.jsonl"), stdout)
        _write_text(prefix.with_suffix(".stderr.log"), stderr)
        _write_json(prefix.with_suffix(".response.json"), response)

    def save_review_call(
        self,
        run_id: str,
        sequence: int,
        stdout: str,
        stderr: str,
        response: dict[str, Any],
    ) -> None:
        if sequence < 0:
            raise StorageError("review call sequence must be non-negative")
        prefix = self.directory_for(run_id) / "reviews" / f"{sequence:03d}-prelaunch"
        _write_text(prefix.with_suffix(".events.jsonl"), stdout)
        _write_text(prefix.with_suffix(".stderr.log"), stderr)
        _write_json(prefix.with_suffix(".response.json"), response)

    def save_prelaunch_review(self, run_id: str, review: str) -> Path:
        path = self.prelaunch_review_path(run_id)
        _write_text(path, review)
        return path

    def plan_package_hashes(self, run_id: str) -> dict[str, str]:
        directory = self.directory_for(run_id)
        paths = [directory / "TASK_CONTRACT.md", directory / "ir.json"]
        paths.extend(sorted((directory / "phases").glob("*.md")))
        missing = [str(path) for path in paths if not path.is_file()]
        if missing:
            raise StorageError("cannot fingerprint incomplete Plan Package: " + ", ".join(missing))
        return {
            str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        }

    @staticmethod
    def file_sha256(path: Path) -> str:
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except FileNotFoundError as error:
            raise StorageError(f"missing file: {path}") from error

    def save_ir(self, run_id: str, workflow: dict[str, Any]) -> None:
        _write_json(self.directory_for(run_id) / "ir.json", workflow)

    def load_ir(self, run_id: str) -> dict[str, Any]:
        return _read_json(self.directory_for(run_id) / "ir.json")

    def save_goal(self, run_id: str, goal: str) -> Path:
        path = self.directory_for(run_id) / "goal" / "GOAL.md"
        _write_text(path, goal)
        return path
