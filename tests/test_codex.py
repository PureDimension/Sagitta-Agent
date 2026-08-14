from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sagitta.codex import CodexError, CodexPlanner


def transport_response(response: dict, envelope_key: str = "planning_response_json") -> str:
    return json.dumps({envelope_key: json.dumps(response)})


class CodexPlannerTests(unittest.TestCase):
    def test_start_uses_sol_high_and_writable_contract_package(self) -> None:
        captured: list[str] = []
        captured_cwd: Path | None = None

        def fake_run(command, **_kwargs):
            nonlocal captured_cwd
            captured.extend(command)
            captured_cwd = _kwargs["cwd"]
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                transport_response(
                    {
                        "status": "needs_input",
                        "summary": "Need a decision.",
                        "questions": [
                            {"id": "mode", "question": "Which mode?", "reason": "It changes scope."}
                        ],
                    }
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout='{"thread_id":"thread-1"}\n', stderr="")

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan_directory = workspace / "plan"
            plan_directory.mkdir()
            result = CodexPlanner(run_command=fake_run).start(workspace, "Plan this task", plan_directory)

        self.assertEqual(result.session_id, "thread-1")
        self.assertIn("gpt-5.6-sol", captured)
        self.assertIn('model_reasoning_effort="high"', captured)
        self.assertIn("workspace-write", captured)
        self.assertIn("--add-dir", captured)
        self.assertIn(str(plan_directory), captured)
        self.assertIn("--output-schema", captured)
        self.assertNotIn("-a", captured)
        self.assertEqual(captured_cwd, Path(directory))

    def test_resume_runs_from_the_plan_workspace(self) -> None:
        captured_cwd: Path | None = None
        captured: list[str] = []

        def fake_run(command, **kwargs):
            nonlocal captured_cwd
            captured.extend(command)
            captured_cwd = kwargs["cwd"]
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                transport_response({"status": "needs_input", "summary": "Need input.", "questions": [{"id": "mode", "question": "Which mode?", "reason": "It matters."}]}),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan_directory = workspace / "plan"
            plan_directory.mkdir()
            result = CodexPlanner(run_command=fake_run).resume(workspace, "thread-1", "Continue", plan_directory)

        self.assertEqual(result.session_id, "thread-1")
        self.assertEqual(captured_cwd, workspace)
        self.assertEqual(captured[:3], ["codex", "exec", "resume"])
        self.assertEqual(captured[-2:], ["thread-1", "Continue"])
        self.assertNotIn("-C", captured)
        self.assertNotIn("--add-dir", captured)
        self.assertNotIn("workspace-write", captured)

    def test_review_uses_a_fresh_read_only_session_and_review_schema(self) -> None:
        captured: list[str] = []

        def fake_run(command, **_kwargs):
            captured.extend(command)
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                transport_response(
                    {"verdict": "pass", "summary": "Launchable.", "findings": []},
                    "review_response_json",
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(command, 0, stdout='{"thread_id":"review-1"}\n', stderr="")

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan_directory = workspace / "plan"
            plan_directory.mkdir()
            result = CodexPlanner(run_command=fake_run).review(workspace, "Review", plan_directory)

        self.assertEqual(result.response["verdict"], "pass")
        self.assertEqual(result.session_id, "review-1")
        self.assertIn("read-only", captured)
        self.assertNotIn("workspace-write", captured)
        schema = captured[captured.index("--output-schema") + 1]
        self.assertTrue(schema.endswith("prelaunch_review_response.json"))
        self.assertNotEqual(captured[:4], ["codex", "exec", "resume", "thread-1"])

    def test_rejects_an_invalid_transport_envelope(self) -> None:
        def fake_run(command, **_kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(json.dumps({"planning_response_json": "not JSON"}), encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, stdout='{"thread_id":"thread-1"}\n', stderr="")

        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CodexError, "transport envelope"):
                workspace = Path(directory)
                plan_directory = workspace / "plan"
                plan_directory.mkdir()
                CodexPlanner(run_command=fake_run).start(workspace, "Plan this task", plan_directory)

    def test_prefers_a_structured_codex_error_over_stderr_warnings(self) -> None:
        def fake_run(command, **_kwargs):
            return subprocess.CompletedProcess(
                command,
                1,
                stdout='{"type":"error","message":"structured provider failure"}\n',
                stderr="unrelated startup warning",
            )

        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(CodexError, "structured provider failure"):
                workspace = Path(directory)
                plan_directory = workspace / "plan"
                plan_directory.mkdir()
                CodexPlanner(run_command=fake_run).start(workspace, "Plan this task", plan_directory)

    def test_records_jsonl_activity_for_the_frontend(self) -> None:
        def fake_run(command, **_kwargs):
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text(
                transport_response(
                    {"status": "needs_input", "summary": "Need input.", "questions": []},
                ),
                encoding="utf-8",
            )
            return subprocess.CompletedProcess(
                command,
                0,
                stdout='{"type":"thread.started","thread_id":"thread-1"}\n{"type":"turn.started"}\n{"type":"item.completed","item":{"type":"command_execution","command":"pytest","exit_code":0}}\n{"type":"turn.completed"}\n',
                stderr="",
            )

        with TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan_directory = workspace / "plan"
            plan_directory.mkdir()
            CodexPlanner(run_command=fake_run).start(workspace, "Plan this task", plan_directory)
            events = [
                json.loads(line)
                for line in (plan_directory / "activity.jsonl").read_text(encoding="utf-8").splitlines()
            ]

        self.assertEqual([event["event"]["type"] for event in events], ["thread.started", "turn.started", "item.completed", "turn.completed"])
        self.assertTrue(all(event["source"] == "codex" for event in events))
