from __future__ import annotations

import json
import os
import stat
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sagitta.assistant import AssistantService, PydanticAIGateway
from sagitta.codex import CodexResult
from sagitta.collaboration import CollaborationStore, ProjectError
from sagitta.config import ModelSettingsStore, PlanningRunStore
from sagitta.planning import PlanBusyError, PlanningService
from sagitta.web import _ir_graph, _terminate_process, create_app


def workflow() -> dict:
    return {
        "title": "Console example",
        "goal": "Deliver the console.",
        "project_summary": "Temporary project.",
        "assumptions": [],
        "entry_phase": "implement",
        "phases": [{"type": "phase", "id": "implement", "title": "Implement", "kind": "implement", "objective": "Change one thing.", "outputs": ["Source"], "expected_facts": ["It exists."], "timeout_seconds": 60, "on": {"done": "$complete"}}],
    }


class ProjectConfig:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def load(self) -> dict[str, str]:
        return {"workspace": str(self.workspace)}


class FakeCodex:
    def __init__(self, *, block_resume: bool = False) -> None:
        self.started_workspace: Path | None = None
        self.resume_count = 0
        self.entered_resume = threading.Event()
        self.release_resume = threading.Event()
        self.block_resume = block_resume

    def start(self, workspace: Path, _prompt: str, _directory: Path) -> CodexResult:
        self.started_workspace = workspace
        questions = [
            {"id": "format", "question": "Which input format?", "reason": "Changes parsing."},
            {"id": "overwrite", "question": "Allow overwrite?", "reason": "Changes safety."},
        ]
        return CodexResult({"status": "needs_input", "summary": "Need two decisions.", "questions": questions}, "session-1", "", "")

    def resume(self, _workspace: Path, _session: str, _prompt: str, directory: Path) -> CodexResult:
        self.resume_count += 1
        self.entered_resume.set()
        if self.block_resume:
            self.release_resume.wait(timeout=3)
        (directory / "TASK_CONTRACT.md").write_text("# task\n", encoding="utf-8")
        (directory / "phases" / "implement.md").write_text("# phase\n", encoding="utf-8")
        (directory / "ir.json").write_text(json.dumps(workflow()), encoding="utf-8")
        return CodexResult({"status": "ready", "summary": "Ready", "questions": []}, "session-1", "", "")

    def review(self, _workspace: Path, _prompt: str, _directory: Path) -> CodexResult:
        return CodexResult({"verdict": "pass", "summary": "Launchable.", "findings": []}, "review-1", "", "")


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def reply(self, project_id: str, message: str, *, task_id: str | None = None) -> str:
        self.calls.append((project_id, message))
        return "Sagitta understood the message."


class CollaborationTests(unittest.TestCase):
    def test_server_cleanup_escalates_only_after_a_stubborn_sigterm(self) -> None:
        with patch("sagitta.web.os.kill", side_effect=[None, None, None, None]), patch(
            "sagitta.web.time.monotonic", side_effect=[0.0, 4.0]
        ):
            _terminate_process(123, timeout_seconds=3.0)

    def test_workspace_registration_is_inferred_and_never_self_bootstraps(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "客户项目"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            record = store.register_workspace(workspace)
            self.assertEqual(record["label"], "客户项目")
            self.assertTrue(record["id"].startswith("project-"))
            self.assertEqual(store.register_workspace(workspace)["id"], record["id"])
            self.assertNotIn("self_hosting", json.dumps(store.list_projects()))

    def test_model_settings_are_private_and_never_return_a_key(self) -> None:
        with TemporaryDirectory() as directory:
            store = ModelSettingsStore(Path(directory))
            display = store.save(model="deepseek-chat", base_url="https://api.deepseek.com", api_key="top-secret")
            self.assertTrue(display["api_key_configured"])
            self.assertNotIn("top-secret", json.dumps(display))
            self.assertEqual(stat.S_IMODE(store.path.stat().st_mode), 0o600)
            self.assertEqual(store.effective()["api_key"], "top-secret")

    def test_batch_answers_resume_once_and_capture_the_whole_round(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "project"
            workspace.mkdir()
            codex = FakeCodex()
            runs = PlanningRunStore(root / "home")
            service = PlanningService(ProjectConfig(workspace), runs, codex)  # type: ignore[arg-type]
            started = service.plan("Plan it")
            finished = service.answer_many(started["id"], [{"id": "format", "answer": "JSON"}, {"id": "overwrite", "answer": "No"}])
            self.assertEqual(finished["status"], "ready")
            self.assertEqual(codex.resume_count, 1)
            self.assertEqual(len(finished["qa"]), 2)

    def test_sagitta_task_planning_starts_codex_after_creating_the_plan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "project"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            project = store.register_workspace(workspace)
            task = store.create_task(project["id"], "Task")
            codex = FakeCodex()
            service = AssistantService(store, codex)  # type: ignore[arg-type]
            result = service.start_task_codex_planning(project["id"], task["id"], "Plan it")
            self.assertEqual(result["status"], "needs_input")
            self.assertEqual(codex.started_workspace.resolve(), workspace.resolve())
            self.assertEqual(store.task(project["id"], task["id"])["plan"]["id"], result["id"])

    def test_duplicate_batch_is_rejected_while_the_first_resume_owns_the_plan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "project"
            workspace.mkdir()
            codex = FakeCodex(block_resume=True)
            runs = PlanningRunStore(root / "home")
            service = PlanningService(ProjectConfig(workspace), runs, codex)  # type: ignore[arg-type]
            started = service.plan("Plan it")
            answers = [{"id": "format", "answer": "JSON"}, {"id": "overwrite", "answer": "No"}]
            errors: list[Exception] = []

            def run_first() -> None:
                try:
                    service.answer_many(started["id"], answers)
                except Exception as error:  # pragma: no cover - assertion below covers it
                    errors.append(error)

            thread = threading.Thread(target=run_first)
            thread.start()
            self.assertTrue(codex.entered_resume.wait(timeout=1))
            with self.assertRaises(PlanBusyError):
                service.answer_many(started["id"], answers)
            codex.release_resume.set()
            thread.join(timeout=2)
            self.assertFalse(errors)
            self.assertEqual(codex.resume_count, 1)

    def test_pydantic_gateway_persists_structured_history_between_turns(self) -> None:
        class Result:
            output = "Persistent reply."

            def all_messages(self) -> list[object]:
                return []

        class FakeAgent:
            histories: list[object] = []

            def __init__(self, _model: object, instructions: str) -> None:
                self.instructions = instructions

            def tool_plain(self, function: object) -> object:
                return function

            def run_sync(self, _message: str, *, message_history: object = None) -> Result:
                FakeAgent.histories.append(message_history)
                return Result()

        from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelRequest, UserPromptPart

        with TemporaryDirectory() as directory, patch("pydantic_ai.Agent", FakeAgent), patch("pydantic_ai.models.openai.OpenAIChatModel"), patch("pydantic_ai.providers.deepseek.DeepSeekProvider"):
            root = Path(directory)
            workspace = root / "project"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            project = store.register_workspace(workspace)
            service = AssistantService(store)
            service.save_model_settings(model="deepseek-chat", base_url="", api_key="key")
            gateway = PydanticAIGateway(service)
            prior = [ModelRequest(parts=[UserPromptPart(content="Earlier confirmed decision")])]
            store.write_agent_history(project["id"], ModelMessagesTypeAdapter.dump_json(prior).decode("utf-8"))
            self.assertEqual(gateway.reply(project["id"], "Second"), "Persistent reply.")
            self.assertEqual(len(FakeAgent.histories[0]), 1)
            self.assertEqual(FakeAgent.histories[0][0].parts[0].content, "Earlier confirmed decision")
            self.assertTrue(store.agent_history_path(project["id"]).is_file())


class WebConsoleTests(unittest.TestCase):
    def _client(self, root: Path, *, codex: FakeCodex | None = None, gateway: FakeGateway | None = None) -> tuple[TestClient, Path]:
        workspace = root / "feedback-tool"
        workspace.mkdir()
        client = TestClient(create_app(home=root / "home", codex=codex, gateway=gateway))
        registered = client.post("/api/projects", json={"workspace": str(workspace)}).json()["data"]["project"]
        self.assertNotEqual(registered["id"], "sagitta-self-hosting")
        return client, workspace

    def test_directory_picker_registers_the_selected_workspace(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "picked-project"
            workspace.mkdir()
            client = TestClient(create_app(home=root / "home"))
            with patch("sagitta.web._choose_directory", return_value=str(workspace)):
                selected = client.post("/api/system/select-directory").json()["data"]
            self.assertEqual(Path(selected["workspace"]).resolve(), workspace.resolve())
            registered = client.post("/api/projects", json={"workspace": selected["workspace"]}).json()["data"]["project"]
            self.assertEqual(registered["label"], "picked-project")

    def test_api_handles_batch_answers_artifacts_and_goal_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            codex = FakeCodex()
            client, _workspace = self._client(root, codex=codex, gateway=FakeGateway())
            project = client.get("/api/projects").json()["data"]["projects"][0]
            started = client.post(f"/api/projects/{project['id']}/plans", json={"intent": "Build it"}).json()["data"]
            deadline = time.monotonic() + 2
            pending = None
            while time.monotonic() < deadline:
                pending = client.get(f"/api/projects/{project['id']}/pending-question").json()["data"]["pending_questions"]
                if pending:
                    break
                time.sleep(0.02)
            self.assertIsNotNone(pending)
            self.assertEqual(len(pending["questions"]), 2)
            completed = client.post(f"/api/projects/{project['id']}/answers", json={"run_id": started["id"], "answers": [{"id": "format", "answer": "JSON"}, {"id": "overwrite", "answer": "No"}]}).json()["data"]
            self.assertEqual(completed["status"], "ready")
            self.assertEqual(codex.resume_count, 1)
            artifacts = client.get(f"/api/projects/{project['id']}/plans/{started['id']}/artifacts").json()["data"]["artifacts"]
            self.assertIn("task-contract", {item["id"] for item in artifacts})
            graph = client.get(f"/api/projects/{project['id']}/plans/{started['id']}").json()["data"]["graph"]
            self.assertEqual(graph["nodes"][0]["id"], "implement")

    def test_api_allows_multiple_plans_for_one_project(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            codex = FakeCodex()
            client, _workspace = self._client(root, codex=codex, gateway=FakeGateway())
            project_id = client.get("/api/projects").json()["data"]["projects"][0]["id"]
            started = client.post(f"/api/projects/{project_id}/plans", json={"intent": "Build it"}).json()["data"]
            second = client.post(f"/api/projects/{project_id}/plans", json={"intent": "Build it again"})
            self.assertEqual(second.status_code, 200)
            self.assertNotEqual(second.json()["data"]["id"], started["id"])
            client.post(f"/api/projects/{project_id}/answers", json={"run_id": started["id"], "answers": [{"id": "format", "answer": "JSON"}, {"id": "overwrite", "answer": "No"}]})
            deleted = client.delete(f"/api/projects/{project_id}/plans/{started['id']}")
            self.assertEqual(deleted.status_code, 200)
            self.assertEqual(deleted.json()["data"]["status"], "deleted")
            self.assertFalse((root / "home" / "plans" / started["id"]).exists())
            plans = client.get(f"/api/projects/{project_id}/plans").json()["data"]["plans"]
            self.assertEqual([plan["id"] for plan in plans], [second.json()["data"]["id"]])

    def test_direct_plan_returns_before_codex_finishes_and_exposes_ag_ui_events(self) -> None:
        class SlowCodex(FakeCodex):
            def __init__(self) -> None:
                super().__init__()
                self.started = threading.Event()
                self.release = threading.Event()

            def start(self, workspace: Path, prompt: str, directory: Path) -> CodexResult:
                self.started.set()
                self.release.wait(timeout=3)
                return super().start(workspace, prompt, directory)

        with TemporaryDirectory() as directory:
            root = Path(directory)
            codex = SlowCodex()
            client, _workspace = self._client(root, codex=codex, gateway=FakeGateway())
            project_id = client.get("/api/projects").json()["data"]["projects"][0]["id"]
            started_at = time.monotonic()
            response = client.post(f"/api/projects/{project_id}/plans", json={"intent": "Build it"})
            self.assertLess(time.monotonic() - started_at, 0.5)
            plan = response.json()["data"]
            self.assertEqual(plan["status"], "planning")
            self.assertTrue(codex.started.wait(timeout=1))
            codex.release.set()
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                state = client.get(f"/api/projects/{project_id}/plans/{plan['id']}").json()["data"]
                if state["status"] == "needs_input":
                    break
                time.sleep(0.02)
            else:
                self.fail("planner did not finish")
            activity_path = PlanningRunStore(root / "home").directory_for(plan["id"]) / "activity.jsonl"
            activity_path.write_text(
                json.dumps(
                    {
                        "at": "2026-08-14T00:00:00Z",
                        "source": "codex",
                        "operation": "planning",
                        "event": {
                            "type": "item.completed",
                            "item": {"type": "command_execution", "command": "pytest", "exit_code": 0},
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            stream = client.get(f"/api/projects/{project_id}/plans/{plan['id']}/activity")
            self.assertEqual(stream.status_code, 200)
            self.assertIn('"type": "RUN_STARTED"', stream.text)
            self.assertIn('"activityType": "sagitta.executor_activity"', stream.text)
            self.assertIn("pytest", stream.text)
            self.assertIn('"type": "RUN_FINISHED"', stream.text)

    def test_api_refuses_to_delete_a_running_plan(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client, _workspace = self._client(root, codex=FakeCodex(), gateway=FakeGateway())
            project_id = client.get("/api/projects").json()["data"]["projects"][0]["id"]
            started = client.post(f"/api/projects/{project_id}/plans", json={"intent": "Build it"}).json()["data"]
            runs = PlanningRunStore(root / "home")
            record = json.loads(runs.path_for(started["id"]).read_text(encoding="utf-8"))
            record["status"] = "planning"
            runs.path_for(started["id"]).write_text(json.dumps(record), encoding="utf-8")
            response = client.delete(f"/api/projects/{project_id}/plans/{started['id']}")
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.json()["error"]["code"], "plan_busy")

    def test_settings_and_chat_are_local_and_key_safe(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            gateway = FakeGateway()
            client, _workspace = self._client(root, gateway=gateway)
            saved = client.put("/api/settings", json={"model": "deepseek-chat", "base_url": "https://example.test/v1", "api_key": "private-value", "clear_api_key": False}).json()["data"]
            self.assertTrue(saved["api_key_configured"])
            self.assertNotIn("private-value", json.dumps(saved))
            project_id = client.get("/api/projects").json()["data"]["projects"][0]["id"]
            reply = client.post(f"/api/projects/{project_id}/messages", json={"content": "Help me plan"}).json()["data"]
            self.assertEqual(reply["reply"], "Sagitta understood the message.")
            self.assertEqual(gateway.calls[0][0], project_id)

    def test_tasks_isolate_their_thread_and_delete_their_plan_package(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            client, _workspace = self._client(root, codex=FakeCodex(), gateway=FakeGateway())
            project_id = client.get("/api/projects").json()["data"]["projects"][0]["id"]
            first = client.post(f"/api/projects/{project_id}/tasks", json={"title": "First task"}).json()["data"]
            second = client.post(f"/api/projects/{project_id}/tasks", json={"title": "Second task"}).json()["data"]

            client.post(
                f"/api/projects/{project_id}/tasks/{first['id']}/messages",
                json={"content": "Keep this task separate."},
            )
            first_messages = client.get(
                f"/api/projects/{project_id}/tasks/{first['id']}/conversation"
            ).json()["data"]["messages"]
            second_messages = client.get(
                f"/api/projects/{project_id}/tasks/{second['id']}/conversation"
            ).json()["data"]["messages"]
            self.assertEqual([entry["content"] for entry in first_messages], ["Keep this task separate.", "Sagitta understood the message."])
            self.assertEqual(second_messages, [])

            planned = client.post(
                f"/api/projects/{project_id}/tasks/{first['id']}/plans",
                json={"intent": "Plan the first task"},
            ).json()["data"]
            self.assertEqual(planned["task_id"], first["id"])
            self.assertIsNone(client.get(f"/api/projects/{project_id}/tasks/{second['id']}").json()["data"]["plan"])
            self.assertTrue((root / "home" / "plans" / planned["id"]).is_dir())

            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                current = client.get(f"/api/projects/{project_id}/tasks/{first['id']}").json()["data"]["plan"]
                if current and current["status"] == "needs_input":
                    break
                time.sleep(0.02)
            else:
                self.fail("task planner did not reach its first decision round")

            shared_thread = client.get(
                f"/api/projects/{project_id}/tasks/{first['id']}/conversation"
            ).json()["data"]["messages"]
            self.assertEqual(
                [entry["content"] for entry in shared_thread[:3]],
                ["Keep this task separate.", "Sagitta understood the message.", "Plan the first task"],
            )
            activity_path = PlanningRunStore(root / "home").directory_for(planned["id"]) / "activity.jsonl"
            activity_path.write_text(
                json.dumps(
                    {
                        "at": "2026-08-14T00:00:00Z",
                        "source": "codex",
                        "operation": "planning",
                        "event": {"type": "item.completed", "item": {"type": "command_execution", "command": "pytest", "exit_code": 0}},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            activity = client.get(
                f"/api/projects/{project_id}/tasks/{first['id']}/activity?snapshot=1"
            ).text
            self.assertIn(f'"threadId": "{first["id"]}"', activity)

            deleted = client.delete(f"/api/projects/{project_id}/tasks/{first['id']}")
            self.assertEqual(deleted.status_code, 200)
            self.assertFalse((root / "home" / "plans" / planned["id"]).exists())
            self.assertEqual(
                client.get(f"/api/projects/{project_id}/tasks/{first['id']}").status_code,
                404,
            )
            self.assertEqual(
                client.get(f"/api/projects/{project_id}/tasks/{second['id']}/conversation").json()["data"]["messages"],
                [],
            )

    def test_presentation_graph_keeps_only_whitelisted_fields(self) -> None:
        graph = _ir_graph(workflow())
        self.assertEqual(set(graph["nodes"][0]), {"id", "type", "title", "kind", "parent", "objective", "outputs", "expected_facts", "outcomes"})


if __name__ == "__main__":
    unittest.main()
