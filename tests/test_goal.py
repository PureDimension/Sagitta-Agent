from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sagitta.config import PlanningRunStore
from sagitta.cli import main
from sagitta.goal import GoalCompilationError, GoalService, compile_goal


def write_contracts(runs: PlanningRunStore, run_id: str) -> None:
    directory = runs.prepare_contract_package(run_id)
    (directory / "TASK_CONTRACT.md").write_text("# Task contract\n", encoding="utf-8")
    (directory / "PRELAUNCH_REVIEW.md").write_text(
        "# Pre-launch Review\n\nVerdict: `pass`\n",
        encoding="utf-8",
    )
    for phase_id in ("implement", "test"):
        (directory / "phases" / f"{phase_id}.md").write_text(f"# {phase_id}\n", encoding="utf-8")


def freeze_reviewed_package(runs: PlanningRunStore, run_id: str) -> None:
    record = runs.load(run_id)
    record["reviewed_package_hashes"] = runs.plan_package_hashes(run_id)
    record["prelaunch_review_sha256"] = runs.file_sha256(runs.prelaunch_review_path(run_id))
    runs.save(record)


def workflow() -> dict:
    return {
        "title": "Example workflow",
        "goal": "Make a bounded change.",
        "project_summary": "A Python project with tests.",
        "assumptions": ["Use the existing test command."],
        "entry_phase": "implement",
        "phases": [
            {
                "type": "phase",
                "id": "implement",
                "title": "Implement the change",
                "kind": "implement",
                "objective": "Make the requested change.",
                "outputs": ["The changed source files."],
                "expected_facts": ["The requested behavior is present."],
                "timeout_seconds": 120,
                "on": {
                    "implemented": "test",
                    "blocked": [
                        {"when": "$implement.retrycount.after.test < 2", "target": "implement"},
                        {"target": "$complete"},
                    ],
                },
            },
            {
                "type": "phase",
                "id": "test",
                "title": "Run verification",
                "kind": "test",
                "objective": "Run the project tests.",
                "outputs": ["A test log."],
                "expected_facts": ["The test command exits successfully."],
                "timeout_seconds": 60,
                "on": {
                    "passed": "$complete",
                    "needs_fix": [
                        {"when": "$test.entercount.after.implement <= 1 and $test.entercount < 3", "target": "implement"},
                        {"target": "$complete"},
                    ],
                },
            }
        ],
    }


class GoalCompilerTests(unittest.TestCase):
    def test_compiles_all_execution_context_and_navigation(self) -> None:
        goal = compile_goal(
            workflow(),
            "Add the bounded change.",
            [{"id": "boundary", "question": "Which boundary?", "answer": "Only the API."}],
            Path("/managed-plan"),
        )

        self.assertIn("Add the bounded change.", goal)
        self.assertIn("Answer: Only the API.", goal)
        self.assertIn("Phase `implement`", goal)
        self.assertIn("If you observe `blocked`", goal)
        self.assertIn("since phase `test` was most recently entered, phase `implement` has directly retried itself fewer than 2 times", goal)
        self.assertIn("otherwise, finish the workflow", goal)
        self.assertIn("since phase `implement` was most recently entered, phase `test` has been entered at most 1 times", goal)
        self.assertIn("phase `test` has been entered fewer than 3 times", goal)
        self.assertIn("Keep the following counters explicitly", goal)
        self.assertNotIn("Scope `", goal)
        self.assertNotIn("$implement.retrycount", goal)
        self.assertNotIn("$complete", goal)
        self.assertNotIn("$", goal)
        self.assertNotIn('{"when"', goal)
        self.assertIn("/managed-plan/TASK_CONTRACT.md", goal)
        self.assertIn("/managed-plan/PRELAUNCH_REVIEW.md", goal)
        self.assertIn("/managed-plan/phases/implement.md", goal)
        self.assertIn(".sagitta-goal-state.json", goal)
        self.assertIn(".sagitta-goal/RUN_LEDGER.jsonl", goal)
        self.assertIn(".sagitta-goal/CHECKPOINT.md", goal)
        self.assertIn("Select an outcome only when its complete condition is evidenced", goal)
        self.assertIn("ready_for_human_audit", goal)
        self.assertIn("Do not write `delivery_complete`", goal)

    def test_exports_only_a_ready_plan_to_its_plan_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready", "prelaunch_review": {"verdict": "pass"}})
            runs.save_ir(run_id, workflow())
            write_contracts(runs, run_id)
            freeze_reviewed_package(runs, run_id)

            path, goal = GoalService(runs).export(run_id)

            self.assertEqual(path, root / "plans" / run_id / "goal" / "GOAL.md")
            self.assertEqual(path.read_text(encoding="utf-8"), goal)
            self.assertIn("Example workflow", goal)

    def test_rejects_an_unready_plan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "needs_input"})

            with self.assertRaisesRegex(GoalCompilationError, "only a ready"):
                GoalService(runs).export(run_id)

    def test_rejects_a_ready_plan_without_a_passing_prelaunch_review(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready"})

            with self.assertRaisesRegex(GoalCompilationError, "passing pre-launch review"):
                GoalService(runs).export(run_id)

    def test_rejects_a_ready_plan_without_its_contract_package(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready", "prelaunch_review": {"verdict": "pass"}})
            runs.save_ir(run_id, workflow())

            with self.assertRaisesRegex(GoalCompilationError, "missing required non-empty contracts"):
                GoalService(runs).export(run_id)

    def test_rejects_a_reviewed_plan_changed_after_review(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready", "prelaunch_review": {"verdict": "pass"}})
            runs.save_ir(run_id, workflow())
            write_contracts(runs, run_id)
            freeze_reviewed_package(runs, run_id)
            runs.task_contract_path(run_id).write_text("# Changed after review\n", encoding="utf-8")

            with self.assertRaisesRegex(GoalCompilationError, "no longer matches"):
                GoalService(runs).export(run_id)

    def test_goal_command_exports_and_prints_the_paste_ready_goal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready", "prelaunch_review": {"verdict": "pass"}})
            runs.save_ir(run_id, workflow())
            write_contracts(runs, run_id)
            freeze_reviewed_package(runs, run_id)
            stdout = StringIO()

            with redirect_stdout(stdout):
                status = main(["--home", str(root), "goal", run_id])

            self.assertEqual(status, 0)
            self.assertIn("Saved paste-ready Codex Goal to:", stdout.getvalue())
            self.assertIn("# Sagitta Goal: Example workflow", stdout.getvalue())
