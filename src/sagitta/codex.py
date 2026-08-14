"""A minimal Codex CLI adapter for planning sessions with a contract package."""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Callable, Sequence


class CodexError(RuntimeError):
    """Raised when the Codex CLI cannot produce a usable planning response."""


@dataclass(frozen=True)
class CodexResult:
    response: dict[str, Any]
    session_id: str
    stdout: str
    stderr: str


RunCommand = Callable[..., subprocess.CompletedProcess[str]]


class CodexPlanner:
    """Runs a persistent planner plus fresh read-only package reviews."""

    model = "gpt-5.6-sol"
    reasoning_effort = "high"

    def __init__(self, run_command: RunCommand = subprocess.run) -> None:
        self.run_command = run_command

    def start(self, workspace: Path, prompt: str, plan_directory: Path) -> CodexResult:
        command_prefix: list[str] = [
            "codex",
            "exec",
            "-m",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-C",
            str(workspace),
            "-s",
            "workspace-write",
            "--add-dir",
            str(plan_directory),
        ]
        return self._invoke(command_prefix, prompt, workspace=workspace)

    def resume(self, workspace: Path, session_id: str, prompt: str, plan_directory: Path) -> CodexResult:
        command_prefix = [
            "codex",
            "exec",
            "resume",
            session_id,
            "-m",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-C",
            str(workspace),
            "-s",
            "workspace-write",
            "--add-dir",
            str(plan_directory),
        ]
        return self._invoke(
            command_prefix,
            prompt,
            workspace=workspace,
            fallback_session_id=session_id,
        )

    def review(self, workspace: Path, prompt: str, plan_directory: Path) -> CodexResult:
        """Review a complete Plan Package in a fresh read-only Codex session."""
        command_prefix = [
            "codex",
            "exec",
            "-m",
            self.model,
            "-c",
            f'model_reasoning_effort="{self.reasoning_effort}"',
            "-C",
            str(workspace),
            "-s",
            "read-only",
            "--add-dir",
            str(plan_directory),
        ]
        return self._invoke(
            command_prefix,
            prompt,
            workspace=workspace,
            schema_name="prelaunch_review_response.json",
            envelope_key="review_response_json",
            operation="pre-launch review",
        )

    def _invoke(
        self,
        command_prefix: Sequence[str],
        prompt: str,
        workspace: Path,
        fallback_session_id: str | None = None,
        schema_name: str = "planning_response.json",
        envelope_key: str = "planning_response_json",
        operation: str = "planning",
    ) -> CodexResult:
        with tempfile.TemporaryDirectory(prefix="sagitta-codex-") as directory:
            output_path = Path(directory) / "response.json"
            schema_path = resources.files("sagitta.schemas").joinpath(schema_name)
            command = [
                *command_prefix,
                "--json",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                prompt,
            ]
            completed = self.run_command(
                command,
                text=True,
                capture_output=True,
                check=False,
                cwd=workspace,
            )
            if completed.returncode != 0:
                detail = self._error_detail(completed.stdout, completed.stderr)
                raise CodexError(f"Codex {operation} failed ({completed.returncode}): {detail}")
            try:
                transport = json.loads(output_path.read_text(encoding="utf-8"))
            except FileNotFoundError as error:
                raise CodexError("Codex did not write its final planning response") from error
            except json.JSONDecodeError as error:
                raise CodexError(f"Codex {operation} final response is not JSON: {error}") from error
            try:
                response_json = transport[envelope_key]
                if not isinstance(response_json, str):
                    raise TypeError(f"{envelope_key} is not a string")
                response = json.loads(response_json)
            except (KeyError, TypeError, json.JSONDecodeError) as error:
                raise CodexError(f"Codex final response has an invalid {operation} transport envelope") from error
            session_id = self._find_session_id(completed.stdout) or fallback_session_id
            if not session_id:
                raise CodexError(f"Codex did not expose a {operation} session id")
            if not isinstance(response, dict):
                raise CodexError("Codex final response must be a JSON object")
            return CodexResult(
                response=response,
                session_id=session_id,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )

    @staticmethod
    def _find_session_id(stdout: str) -> str | None:
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            for key in ("thread_id", "threadId", "session_id", "sessionId"):
                candidate = event.get(key)
                if isinstance(candidate, str) and candidate:
                    return candidate
            thread = event.get("thread")
            if isinstance(thread, dict):
                candidate = thread.get("id")
                if isinstance(candidate, str) and candidate:
                    return candidate
            params = event.get("params")
            if isinstance(params, dict):
                thread = params.get("thread")
                if isinstance(thread, dict):
                    candidate = thread.get("id")
                    if isinstance(candidate, str) and candidate:
                        return candidate
        return None

    @staticmethod
    def _error_detail(stdout: str, stderr: str) -> str:
        """Prefer Codex's structured JSONL error over startup warnings on stderr."""
        for line in stdout.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "error" and isinstance(event.get("message"), str):
                return event["message"]
            error = event.get("error")
            if isinstance(error, dict) and isinstance(error.get("message"), str):
                return error["message"]
        return stderr.strip() or stdout.strip() or "no CLI output"
