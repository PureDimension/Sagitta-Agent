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
    for phase_id in ("implement", "test"):
        (directory / "phases" / f"{phase_id}.md").write_text(f"# {phase_id}\n", encoding="utf-8")


def workflow() -> dict:
    return {
        "title": "Example workflow",
        "goal": "Make a bounded change.",
        "project_summary": "A Python project with tests.",
        "assumptions": ["Use the existing test command."],
        "entry_phase": "major",
        "phases": [
            {
                "type": "scope",
                "id": "major",
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
                                {"when": "$implement.retry < 2", "target": "implement"},
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
                                {"when": "$major.implement <= 1 and $workflow.test < 3", "target": "implement"},
                                {"target": "$complete"},
                            ],
                        },
                    },
                ],
            }
        ],
    }


class GoalCompilerTests(unittest.TestCase):
    def test_compiles_all_execution_context_and_navigation(self) -> None:
        goal = compile_goal(
            workflow(),
            "Add the bounded change.",
            [{"id": "scope", "question": "Which scope?", "answer": "Only the API."}],
            Path("/managed-plan"),
        )

        self.assertIn("Add the bounded change.", goal)
        self.assertIn("Answer: Only the API.", goal)
        self.assertIn("Scope `major`", goal)
        self.assertIn("Phase `implement`", goal)
        self.assertIn("If you observe `blocked`", goal)
        self.assertIn("phase `implement` has directly retried itself fewer than 2 times", goal)
        self.assertIn("otherwise, finish the workflow", goal)
        self.assertIn("this run of scope `major` has entered its direct child `implement` at most 1 times", goal)
        self.assertIn("the workflow has entered `test` fewer than 3 times", goal)
        self.assertNotIn("$implement.retry", goal)
        self.assertNotIn("$complete", goal)
        self.assertNotIn("$major.implement", goal)
        self.assertNotIn("$workflow.test", goal)
        self.assertNotIn("$", goal)
        self.assertNotIn('{"when"', goal)
        self.assertIn("/managed-plan/TASK_CONTRACT.md", goal)
        self.assertIn("/managed-plan/phases/implement.md", goal)
        self.assertIn(".sagitta-goal-state.json", goal)

    def test_exports_only_a_ready_plan_to_its_plan_directory(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready"})
            runs.save_ir(run_id, workflow())
            write_contracts(runs, run_id)

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

    def test_rejects_a_ready_plan_without_its_contract_package(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready"})
            runs.save_ir(run_id, workflow())

            with self.assertRaisesRegex(GoalCompilationError, "missing required non-empty contracts"):
                GoalService(runs).export(run_id)

    def test_goal_command_exports_and_prints_the_paste_ready_goal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            run_id = "12345678-1234-1234-1234-123456789abc"
            runs = PlanningRunStore(root)
            runs.create({"id": run_id, "intent": "Add the bounded change.", "qa": [], "status": "ready"})
            runs.save_ir(run_id, workflow())
            write_contracts(runs, run_id)
            stdout = StringIO()

            with redirect_stdout(stdout):
                status = main(["--home", str(root), "goal", run_id])

            self.assertEqual(status, 0)
            self.assertIn("Saved paste-ready Codex Goal to:", stdout.getvalue())
            self.assertIn("# Sagitta Goal: Example workflow", stdout.getvalue())
