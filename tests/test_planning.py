from __future__ import annotations

from importlib import resources
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sagitta.codex import CodexResult
from sagitta.config import ConfigStore, PlanningRunStore
from sagitta.planning import PlanningError, PlanningService


def write_contracts(plan_directory: Path, phase_ids: list[str], workflow: dict) -> None:
    (plan_directory / "TASK_CONTRACT.md").write_text("# Task contract\n", encoding="utf-8")
    for phase_id in phase_ids:
        (plan_directory / "phases" / f"{phase_id}.md").write_text(f"# {phase_id}\n", encoding="utf-8")
    (plan_directory / "ir.json").write_text(json.dumps(workflow), encoding="utf-8")


class FakeCodex:
    def __init__(self) -> None:
        self.start_prompt = ""
        self.resume_prompt = ""
        self.resume_workspace: Path | None = None
        self.review_prompt = ""

    def start(self, _workspace: Path, prompt: str, _plan_directory: Path) -> CodexResult:
        self.start_prompt = prompt
        return CodexResult(
            session_id="thread-1",
            stdout='{"thread_id":"thread-1"}\n',
            stderr="",
            response={
                "status": "needs_input",
                "summary": "Need one choice.",
                "questions": [
                    {"id": "mode", "question": "Which mode?", "reason": "It changes scope."}
                ],
            },
        )

    def resume(self, workspace: Path, _session_id: str, prompt: str, plan_directory: Path) -> CodexResult:
        self.resume_prompt = prompt
        self.resume_workspace = workspace
        workflow = {
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
        }
        write_contracts(plan_directory, ["implement"], workflow)
        return CodexResult(
            session_id="thread-1",
            stdout="",
            stderr="",
            response={
                "status": "ready",
                "summary": "Ready.",
                "questions": [],
            },
        )

    def review(self, _workspace: Path, prompt: str, _plan_directory: Path) -> CodexResult:
        self.review_prompt = prompt
        return CodexResult(
            session_id="review-thread-1",
            stdout='{"thread_id":"review-thread-1"}\n',
            stderr="",
            response={"verdict": "pass", "summary": "The package is launchable.", "findings": []},
        )


class FakeCodexWithInvalidIR:
    def __init__(self) -> None:
        self.resume_prompts: list[str] = []

    def start(self, _workspace: Path, _prompt: str, plan_directory: Path) -> CodexResult:
        invalid_workflow = {
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
        }
        write_contracts(plan_directory, ["implement"], invalid_workflow)
        return CodexResult(
            session_id="thread-1",
            stdout="",
            stderr="",
            response={
                "status": "ready",
                "summary": "This response has an invalid phase.",
                "questions": [],
            },
        )

    def resume(self, _workspace: Path, _session_id: str, prompt: str, plan_directory: Path) -> CodexResult:
        self.resume_prompts.append(prompt)
        workflow = {
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
        }
        write_contracts(plan_directory, ["implement"], workflow)
        return CodexResult(
            session_id="thread-1",
            stdout="",
            stderr="",
            response={
                "status": "ready",
                "summary": "Repaired.",
                "questions": [],
            },
        )

    def review(self, _workspace: Path, _prompt: str, _plan_directory: Path) -> CodexResult:
        return CodexResult(
            session_id="review-thread-1",
            stdout="",
            stderr="",
            response={"verdict": "pass", "summary": "The repaired package is launchable.", "findings": []},
        )


class FakeCodexWithPrelaunchRevision:
    def __init__(self, second_verdict: str = "pass") -> None:
        self.review_count = 0
        self.resume_prompts: list[str] = []
        self.second_verdict = second_verdict

    @staticmethod
    def _write_plan(plan_directory: Path) -> None:
        workflow = {
            "title": "Reviewed",
            "goal": "Deliver reviewed work.",
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
                    "outputs": ["The change."],
                    "expected_facts": ["The behavior is directly verified."],
                    "timeout_seconds": 60,
                    "on": {"implemented": "$complete"},
                }
            ],
        }
        write_contracts(plan_directory, ["implement"], workflow)

    def start(self, _workspace: Path, _prompt: str, plan_directory: Path) -> CodexResult:
        self._write_plan(plan_directory)
        return CodexResult(
            session_id="planner-thread",
            stdout="",
            stderr="",
            response={"status": "ready", "summary": "Drafted.", "questions": []},
        )

    def resume(self, _workspace: Path, session_id: str, prompt: str, plan_directory: Path) -> CodexResult:
        self.resume_prompts.append(prompt)
        self._write_plan(plan_directory)
        return CodexResult(
            session_id=session_id,
            stdout="",
            stderr="",
            response={"status": "ready", "summary": "Revised.", "questions": []},
        )

    def review(self, _workspace: Path, _prompt: str, _plan_directory: Path) -> CodexResult:
        self.review_count += 1
        verdict = "revise" if self.review_count == 1 else self.second_verdict
        findings = []
        if verdict == "revise":
            findings = [
                {
                    "id": "gate-implement",
                    "location": "phases/implement.md",
                    "problem": "The outcome gate is fakeable.",
                    "required_change": "Require direct behavior evidence.",
                }
            ]
        return CodexResult(
            session_id=f"review-thread-{self.review_count}",
            stdout="",
            stderr="",
            response={"verdict": verdict, "summary": "Review result.", "findings": findings},
        )


class FakeCodexWithInvalidPrelaunchReview(FakeCodexWithPrelaunchRevision):
    def review(self, _workspace: Path, _prompt: str, _plan_directory: Path) -> CodexResult:
        return CodexResult(
            session_id="review-thread-invalid",
            stdout='{"thread_id":"review-thread-invalid"}\n',
            stderr="",
            response={"verdict": "pass", "summary": "Incomplete transport."},
        )


class FakeCodexThatCrashes:
    def start(self, _workspace: Path, _prompt: str, _plan_directory: Path) -> CodexResult:
        raise RuntimeError("planner process crashed")


class PlanningServiceTests(unittest.TestCase):
    def test_planner_failure_is_persisted_instead_of_leaving_planning_running(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            runs = PlanningRunStore(root)
            service = PlanningService(config, runs, FakeCodexThatCrashes())  # type: ignore[arg-type]

            with self.assertRaisesRegex(RuntimeError, "planner process crashed"):
                service.plan("Plan this work")

            run_id = next((root / "plans").iterdir()).name
            failed = runs.load(run_id)
            self.assertEqual(failed["status"], "planning_failed")
            self.assertTrue(failed["planning_closed"])
            self.assertEqual(failed["last_error_type"], "RuntimeError")
            events = (root / "plans" / run_id / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("planning_exception_recorded", events)

    def test_planner_prompt_teaches_flat_graph_counter_windows(self) -> None:
        prompt = resources.files("sagitta.prompts").joinpath("planner.md").read_text(encoding="utf-8")

        self.assertIn("There are no `scope` objects", prompt)
        self.assertIn("`$phase.entercount.after.anchor`", prompt)
        self.assertIn("`$phase.retrycount.after.anchor`", prompt)
        self.assertIn('"when": "$inspect.retrycount < 2"', prompt)
        self.assertIn('"when": "$verify_change.entercount.after.inspect < 3"', prompt)
        self.assertNotIn('"type": "scope"', prompt)
        self.assertNotIn("$workflow.verify_change", prompt)
        self.assertIn("Every phase contract must contain an `## Outcome conditions` section", prompt)
        self.assertIn("Outcome names are labels, never definitions", prompt)
        self.assertIn('"reason": "The answer changes compatibility requirements', prompt)

    def test_ready_plan_requires_a_global_and_per_phase_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            runs = PlanningRunStore(root)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs.create({"id": run_id})
            runs.prepare_contract_package(run_id)
            service = PlanningService(config, runs, FakeCodex())  # type: ignore[arg-type]
            workflow = {
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
                        "outputs": ["The change."],
                        "expected_facts": ["The change exists."],
                        "timeout_seconds": 60,
                        "on": {"done": "$complete"},
                    }
                ],
            }

            with self.assertRaisesRegex(PlanningError, "TASK_CONTRACT.md"):
                service._validate_contract_package(run_id, workflow)

    def test_ready_plan_requires_a_valid_written_ir(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            runs = PlanningRunStore(root)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs.create({"id": run_id})
            package = runs.prepare_contract_package(run_id)
            workflow = {
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
                        "outputs": ["The change."],
                        "expected_facts": ["The change exists."],
                        "timeout_seconds": 60,
                        "on": {"done": "$complete"},
                    }
                ],
            }
            write_contracts(package, ["implement"], {"title": "different"})
            service = PlanningService(config, runs, FakeCodex())  # type: ignore[arg-type]

            with self.assertRaisesRegex(PlanningError, "workflow fields"):
                service._load_written_workflow(run_id)

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
            self.assertTrue((plan_directory / "PRELAUNCH_REVIEW.md").is_file())
            self.assertTrue((plan_directory / "reviews" / "000-prelaunch.response.json").is_file())
            self.assertIn("Plan Package Pre-launch Review", fake.review_prompt)

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

    def test_prelaunch_review_revises_the_original_planner_session_once(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            fake = FakeCodexWithPrelaunchRevision()
            service = PlanningService(config, PlanningRunStore(root), fake)  # type: ignore[arg-type]

            completed = service.plan("Plan reviewed work")

            self.assertEqual(completed["status"], "ready")
            self.assertEqual(completed["prelaunch_revision_count"], 1)
            self.assertEqual(completed["review_call_count"], 2)
            self.assertEqual(len(fake.resume_prompts), 1)
            self.assertIn("fresh read-only pre-launch reviewer rejected", fake.resume_prompts[0])
            self.assertIn("gate-implement", fake.resume_prompts[0])
            review = root / "plans" / completed["id"] / "PRELAUNCH_REVIEW.md"
            self.assertIn("Verdict: `pass`", review.read_text(encoding="utf-8"))

    def test_prelaunch_review_failure_prevents_ready_after_one_revision(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            fake = FakeCodexWithPrelaunchRevision(second_verdict="revise")
            service = PlanningService(config, PlanningRunStore(root), fake)  # type: ignore[arg-type]

            completed = service.plan("Plan reviewed work")

            self.assertEqual(completed["status"], "planning_review_failed")
            self.assertTrue(completed["planning_closed"])
            self.assertEqual(fake.review_count, 2)
            self.assertEqual(len(fake.resume_prompts), 1)
            events = (root / "plans" / completed["id"] / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("prelaunch_review_exhausted", events)

    def test_invalid_prelaunch_review_closes_the_plan_in_a_failed_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            config = ConfigStore(root)
            config.save_workspace(workspace)
            runs = PlanningRunStore(root)
            service = PlanningService(config, runs, FakeCodexWithInvalidPrelaunchReview())  # type: ignore[arg-type]

            with self.assertRaisesRegex(PlanningError, "invalid pre-launch review object"):
                service.plan("Plan reviewed work")

            run_id = next((root / "plans").iterdir()).name
            failed = runs.load(run_id)
            self.assertEqual(failed["status"], "planning_review_failed")
            self.assertTrue(failed["planning_closed"])
            self.assertEqual(failed["review_call_count"], 1)
            self.assertTrue((root / "plans" / run_id / "reviews" / "000-prelaunch.response.json").is_file())
            events = (root / "plans" / run_id / "events.jsonl").read_text(encoding="utf-8")
            self.assertIn("invalid_prelaunch_review_received", events)
