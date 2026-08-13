from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sagitta.codex import CodexResult
from sagitta.config import ConfigStore, PlanningRunStore
from sagitta.planning import PlanningService


class FakeCodex:
    def __init__(self) -> None:
        self.start_prompt = ""
        self.resume_prompt = ""
        self.resume_workspace: Path | None = None

    def start(self, _workspace: Path, prompt: str) -> CodexResult:
        self.start_prompt = prompt
        return CodexResult(
            session_id="thread-1",
            stdout='{"thread_id":"thread-1"}\n',
            stderr="",
            response={
                "status": "needs_input",
                "summary": "Need one choice.",
                "workflow": None,
                "questions": [
                    {"id": "mode", "question": "Which mode?", "reason": "It changes scope."}
                ],
            },
        )

    def resume(self, workspace: Path, _session_id: str, prompt: str) -> CodexResult:
        self.resume_prompt = prompt
        self.resume_workspace = workspace
        return CodexResult(
            session_id="thread-1",
            stdout="",
            stderr="",
            response={
                "status": "ready",
                "summary": "Ready.",
                "questions": [],
                "workflow": {
                    "title": "Example",
                    "goal": "Do the work.",
                    "project_summary": "A project.",
                    "assumptions": [],
                    "entry_phase": "implement",
                    "phases": [
                        {
                            "type": "phase",
                            "id": "implement",
                            "title": "Implement",
                            "kind": "implement",
                            "objective": "Make the change.",
                            "outputs": ["The requested change."],
                            "expected_facts": ["The change is present."],
                            "timeout_seconds": 60,
                            "on": {"done": "$complete"},
                        }
                    ],
                },
            },
        )


class FakeCodexWithInvalidIR:
    def __init__(self) -> None:
        self.resume_prompts: list[str] = []

    def start(self, _workspace: Path, _prompt: str) -> CodexResult:
        return CodexResult(
            session_id="thread-1",
            stdout="",
            stderr="",
            response={
                "status": "ready",
                "summary": "This response has an invalid phase.",
                "questions": [],
                "workflow": {
                    "title": "Invalid",
                    "goal": "Repair this.",
                    "project_summary": "A project.",
                    "assumptions": [],
                    "entry_phase": "implement",
                    "phases": [
                        {
                            "type": "phase",
                            "id": "implement",
                            "title": "Implement",
                            "kind": "implement",
                            "objective": "Make the change.",
                            "outputs": ["The attempted change."],
                            "expected_facts": ["The response intentionally contains an invalid target."],
                            "timeout_seconds": 60,
                            "on": {"done": "missing"},
                        }
                    ],
                },
            },
        )

    def resume(self, _workspace: Path, _session_id: str, prompt: str) -> CodexResult:
        self.resume_prompts.append(prompt)
        return CodexResult(
            session_id="thread-1",
            stdout="",
            stderr="",
            response={
                "status": "ready",
                "summary": "Repaired.",
                "questions": [],
                "workflow": {
                    "title": "Repaired",
                    "goal": "Do the work.",
                    "project_summary": "A project.",
                    "assumptions": [],
                    "entry_phase": "implement",
                    "phases": [
                        {
                            "type": "phase",
                            "id": "implement",
                            "title": "Implement",
                            "kind": "implement",
                            "objective": "Make the change.",
                            "outputs": ["The corrected change."],
                            "expected_facts": ["The target is valid."],
                            "timeout_seconds": 60,
                            "on": {"done": "$complete"},
                        }
                    ],
                },
            },
        )


class PlanningServiceTests(unittest.TestCase):
    def test_answer_is_saved_and_sent_when_resuming_the_same_session(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            fake = FakeCodex()
            service = PlanningService(config, PlanningRunStore(root), fake)  # type: ignore[arg-type]

            first = service.plan("Plan this work")
            completed = service.answer(first["id"], "mode", "Use session mode")

            self.assertEqual(completed["status"], "ready")
            self.assertIn("Plan this work", fake.start_prompt)
            self.assertNotIn("Existing user Q&A", fake.start_prompt)
            self.assertNotIn("{{Q_AND_A}}", fake.start_prompt)
            self.assertIn("Use session mode", fake.resume_prompt)
            self.assertEqual(completed["qa"][0]["id"], "mode")
            self.assertEqual(fake.resume_workspace, workspace.resolve())
            plan_directory = root / "plans" / first["id"]
            self.assertTrue((plan_directory / "state.json").is_file())
            self.assertTrue((plan_directory / "ir.json").is_file())
            self.assertTrue((plan_directory / "events.jsonl").is_file())
            self.assertTrue((plan_directory / "codex" / "000-initial.events.jsonl").is_file())
            self.assertTrue((plan_directory / "codex" / "001-resume.response.json").is_file())

    def test_invalid_ir_is_repaired_once_in_the_same_session(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            fake = FakeCodexWithInvalidIR()
            service = PlanningService(config, PlanningRunStore(root), fake)  # type: ignore[arg-type]

            completed = service.plan("Plan this work")

            self.assertEqual(completed["status"], "ready")
            self.assertEqual(completed["codex_call_count"], 2)
            self.assertEqual(len(fake.resume_prompts), 1)
            self.assertIn("unknown target", fake.resume_prompts[0])
            events = (root / "plans" / completed["id"] / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("invalid_ir_received", events)
