from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from sagitta.assistant import AgentConfigurationError, AssistantService, PydanticAIGateway
from sagitta.codex import CodexResult
from sagitta.collaboration import CollaborationStore, ProjectError
from sagitta.config import ConfigStore, PlanningRunStore
from sagitta.web import _ir_graph, create_app, load_local_environment


def workflow() -> dict:
    return {
        "title": "Console example",
        "goal": "Deliver the console.",
        "project_summary": "Temporary project.",
        "assumptions": [],
        "entry_phase": "implement",
        "phases": [{"type": "phase", "id": "implement", "title": "Implement", "kind": "implement", "objective": "Change one thing.", "outputs": ["Source"], "expected_facts": ["It exists."], "timeout_seconds": 60, "on": {"done": "$complete"}}],
    }


def ready_plan(home: Path, workspace: Path, run_id: str = "12345678-1234-1234-1234-123456789abc") -> str:
    runs = PlanningRunStore(home)
    runs.create({"id": run_id, "workspace": str(workspace.resolve()), "intent": "Build it", "qa": [], "status": "ready", "prelaunch_review": {"verdict": "pass"}, "updated_at": "2026-01-01T00:00:00Z"})
    package = runs.prepare_contract_package(run_id)
    (package / "TASK_CONTRACT.md").write_text("# task\n", encoding="utf-8")
    (package / "PRELAUNCH_REVIEW.md").write_text("# review\n\nVerdict: `pass`\n", encoding="utf-8")
    (package / "phases" / "implement.md").write_text("# phase\n", encoding="utf-8")
    runs.save_ir(run_id, workflow())
    record = runs.load(run_id)
    record["reviewed_package_hashes"] = runs.plan_package_hashes(run_id)
    record["prelaunch_review_sha256"] = runs.file_sha256(runs.prelaunch_review_path(run_id))
    runs.save(record)
    return run_id


class FakeCodex:
    def __init__(self) -> None:
        self.started_workspace: Path | None = None
        self.resumed = False

    def start(self, workspace: Path, _prompt: str, _directory: Path) -> CodexResult:
        self.started_workspace = workspace
        return CodexResult({"status": "needs_input", "summary": "Need decision", "questions": [{"id": "choice", "question": "Which path?", "reason": "Scope changes."}]}, "session-1", "", "")

    def resume(self, _workspace: Path, _session: str, _prompt: str, directory: Path) -> CodexResult:
        self.resumed = True
        (directory / "TASK_CONTRACT.md").write_text("# task\n", encoding="utf-8")
        (directory / "phases" / "implement.md").write_text("# phase\n", encoding="utf-8")
        (directory / "ir.json").write_text(json.dumps(workflow()), encoding="utf-8")
        return CodexResult({"status": "ready", "summary": "Ready", "questions": []}, "session-1", "", "")

    def review(self, _workspace: Path, _prompt: str, _directory: Path) -> CodexResult:
        return CodexResult(
            {"verdict": "pass", "summary": "Launchable.", "findings": []},
            "review-session-1",
            "",
            "",
        )


class FakeGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def reply(self, project_id: str, message: str) -> str:
        self.calls.append((project_id, message))
        return "I understand the task; inspect the pending planning choice before delegating."


class CollaborationStoreTests(unittest.TestCase):
    def test_local_environment_loads_a_dotenv_file_without_overwriting_exported_values(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "exported-key"}, clear=True):
            dotenv_path = Path(directory) / ".env"
            dotenv_path.write_text(
                "DEEPSEEK_API_KEY=file-key\nSAGITTA_PORT=9234\n",
                encoding="utf-8",
            )

            loaded = load_local_environment(dotenv_path)

            self.assertTrue(loaded)
            self.assertEqual(os.environ["DEEPSEEK_API_KEY"], "exported-key")
            self.assertEqual(os.environ["SAGITTA_PORT"], "9234")

    def test_profile_registry_transcript_and_goal_state_are_project_scoped(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            self.assertTrue(store.ensure_profile().is_file())
            store.bootstrap_self_hosting(workspace)
            store.bootstrap_self_hosting(workspace)
            self.assertEqual(len(store.list_projects()), 1)
            store.append_message("sagitta-self-hosting", "user", "Hello")
            self.assertEqual(store.messages("sagitta-self-hosting")[0]["content"], "Hello")
            self.assertIn("conversation-summaries", str(store.summary_path("sagitta-self-hosting")))
            self.assertEqual(store.goal_state("sagitta-self-hosting")["status"], "absent")
            (workspace / ".sagitta-goal-state.json").write_text("not-json", encoding="utf-8")
            self.assertEqual(store.goal_state("sagitta-self-hosting")["status"], "invalid")
            (workspace / ".sagitta-goal-state.json").write_text(json.dumps({"current_phase": "verify", "final_result": "ready", "outcomes": [{"phase": "verify", "outcome": "passed"}], "secret": "must-not-reach-browser"}), encoding="utf-8")
            available = store.goal_state("sagitta-self-hosting")
            self.assertEqual(available["state"]["current_phase"], "verify")
            self.assertNotIn("secret", available["state"])
            self.assertNotIn("must-not-reach-browser", json.dumps(available))
            with self.assertRaises(ProjectError):
                store.resolve_project("../../escape")

    def test_planning_is_registered_project_scoped_and_keeps_cli_config(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            configured = root / "configured"
            workspace = root / "workspace"
            configured.mkdir()
            workspace.mkdir()
            home = root / "home"
            ConfigStore(home).save_workspace(configured)
            store = CollaborationStore(home)
            store.bootstrap_self_hosting(workspace)
            fake = FakeCodex()
            service = AssistantService(store, fake)  # type: ignore[arg-type]
            first = service.start_codex_planning("sagitta-self-hosting", "Plan the console")
            self.assertEqual(first["status"], "needs_input")
            self.assertEqual(fake.started_workspace, workspace.resolve())
            self.assertEqual(ConfigStore(home).load()["workspace"], str(configured.resolve()))
            pending = store.pending_question("sagitta-self-hosting")
            self.assertEqual(pending["question"]["id"], "choice")  # type: ignore[index]
            completed = service.submit_planner_answer("sagitta-self-hosting", first["id"], "choice", "Use the local path")
            self.assertEqual(completed["status"], "ready")
            self.assertTrue(fake.resumed)
            self.assertEqual(service.export_goal("sagitta-self-hosting", first["id"])["path"], "goal/GOAL.md")

    def test_missing_key_is_reported_without_importing_or_calling_provider(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            store.bootstrap_self_hosting(workspace)
            gateway = PydanticAIGateway(AssistantService(store))
            with self.assertRaisesRegex(AgentConfigurationError, "DEEPSEEK_API_KEY"):
                gateway.reply("sagitta-self-hosting", "Hello")

    def test_real_gateway_constructs_the_official_deepseek_model_lazily(self) -> None:
        class FakeResult:
            output = "A bounded reply."

        class FakeAgent:
            last: "FakeAgent | None" = None

            def __init__(self, model: object, instructions: str) -> None:
                self.model = model
                self.instructions = instructions
                FakeAgent.last = self

            def tool_plain(self, function: object) -> object:
                return function

            def run_sync(self, message: str) -> FakeResult:
                self.message = message
                return FakeResult()

        with TemporaryDirectory() as directory, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True), patch("pydantic_ai.Agent", FakeAgent), patch("pydantic_ai.models.openai.OpenAIChatModel") as model, patch("pydantic_ai.providers.deepseek.DeepSeekProvider") as provider:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            store.bootstrap_self_hosting(workspace)
            reply = PydanticAIGateway(AssistantService(store)).reply("sagitta-self-hosting", "Check this")
            self.assertEqual(reply, "A bounded reply.")
            provider.assert_called_once_with(api_key="test-key")
            model.assert_called_once_with("deepseek-chat", provider=provider.return_value)
            self.assertIn("never answer", FakeAgent.last.instructions)  # type: ignore[union-attr]

    def test_real_gateway_uses_an_explicit_openai_compatible_base_url(self) -> None:
        class FakeResult:
            output = "A bounded reply."

        class FakeAgent:
            def __init__(self, _model: object, instructions: str) -> None:
                self.instructions = instructions

            def tool_plain(self, function: object) -> object:
                return function

            def run_sync(self, _message: str) -> FakeResult:
                return FakeResult()

        environment = {
            "DEEPSEEK_API_KEY": "school-key",
            "DEEPSEEK_BASE_URL": "https://relay.school.example/v1",
        }
        with TemporaryDirectory() as directory, patch.dict(os.environ, environment, clear=True), patch("pydantic_ai.Agent", FakeAgent), patch("pydantic_ai.models.openai.OpenAIChatModel"), patch("pydantic_ai.providers.deepseek.DeepSeekProvider") as provider, patch("openai.AsyncOpenAI") as client:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            store.bootstrap_self_hosting(workspace)

            PydanticAIGateway(AssistantService(store)).reply("sagitta-self-hosting", "Check relay")

            client.assert_called_once_with(api_key="school-key", base_url="https://relay.school.example/v1")
            provider.assert_called_once_with(openai_client=client.return_value)

    def test_installed_pydantic_agent_registers_tools_without_a_provider_turn(self) -> None:
        class Result:
            output = "Offline provider boundary check."

        with TemporaryDirectory() as directory, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True), patch("pydantic_ai.Agent.run_sync", return_value=Result()) as run_turn:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            store.bootstrap_self_hosting(workspace)
            reply = PydanticAIGateway(AssistantService(store)).reply("sagitta-self-hosting", "Check setup")
            self.assertEqual(reply, "Offline provider boundary check.")
            run_turn.assert_called_once()


class WebConsoleTests(unittest.TestCase):
    def test_api_dashboard_chat_plan_goal_and_boundary_behavior(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "SECRET-SENTINEL"}, clear=True):
            root = Path(directory)
            workspace = root / "workspace"
            other = root / "other"
            workspace.mkdir()
            other.mkdir()
            run_id = ready_plan(root / "home", workspace)
            fake = FakeGateway()
            app = create_app(home=root / "home", gateway=fake, self_hosting_workspace=workspace)
            client = TestClient(app)
            health = client.get("/api/health")
            self.assertEqual(health.status_code, 200)
            self.assertNotIn("SECRET-SENTINEL", health.text)
            self.assertIn("SAGITTA", client.get("/").text)
            self.assertIn("project", client.get("/assets/app.js").text)
            projects = client.get("/api/projects").json()["data"]["projects"]
            self.assertEqual(projects[0]["id"], "sagitta-self-hosting")
            self.assertEqual(client.post("/api/projects", json={"id": "bad", "label": "Bad", "workspace": str(root / "missing")}).status_code, 400)
            chat = client.post("/api/projects/sagitta-self-hosting/messages", json={"content": "Please inspect this."}).json()
            self.assertTrue(chat["ok"])
            self.assertEqual(fake.calls[0][0], "sagitta-self-hosting")
            self.assertEqual(len(client.get("/api/projects/sagitta-self-hosting/conversation").json()["data"]["messages"]), 2)
            detail = client.get(f"/api/projects/sagitta-self-hosting/plans/{run_id}").json()["data"]
            self.assertEqual(detail["graph"]["nodes"][0]["id"], "implement")
            self.assertEqual(client.post(f"/api/projects/sagitta-self-hosting/plans/{run_id}/goal").json()["data"]["status"], "exported")
            goal = client.get(f"/api/projects/sagitta-self-hosting/plans/{run_id}/goal").json()["data"]
            self.assertIn("Sagitta Goal", goal["content"])
            self.assertEqual(goal["path"], "goal/GOAL.md")
            client.post("/api/projects", json={"id": "other-project", "label": "Other", "workspace": str(other)})
            self.assertEqual(client.get(f"/api/projects/other-project/plans/{run_id}").status_code, 404)
            (workspace / ".sagitta-goal-state.json").write_text("[]", encoding="utf-8")
            self.assertEqual(client.get("/api/projects/sagitta-self-hosting/goal-state").json()["data"]["status"], "invalid")

    def test_browser_cannot_bypass_sagitta_to_start_planning_but_can_submit_an_explicit_answer(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            fake_codex = FakeCodex()
            store = CollaborationStore(root / "home")
            store.bootstrap_self_hosting(workspace)
            started = AssistantService(store, fake_codex).start_codex_planning("sagitta-self-hosting", "Plan a bounded change")  # type: ignore[arg-type]
            client = TestClient(create_app(home=root / "home", gateway=FakeGateway(), codex=fake_codex, self_hosting_workspace=workspace))
            self.assertEqual(client.post("/api/projects/sagitta-self-hosting/plans", json={"intent": "Bypass Sagitta"}).status_code, 405)
            self.assertEqual(started["status"], "needs_input")
            pending = client.get("/api/projects/sagitta-self-hosting/pending-question").json()["data"]["pending_question"]
            self.assertEqual(pending["question"]["id"], "choice")
            completed = client.post("/api/projects/sagitta-self-hosting/answers", json={"run_id": started["id"], "question_id": "choice", "answer": "Use the existing boundary"}).json()["data"]
            self.assertEqual(completed["status"], "ready")
            self.assertTrue(fake_codex.resumed)

    def test_pydantic_agent_exposes_only_named_delegation_tools(self) -> None:
        class Result:
            output = "I checked the registered project."

        class CapturingAgent:
            last: "CapturingAgent | None" = None

            def __init__(self, _model: object, instructions: str) -> None:
                self.instructions = instructions
                self.tools: dict[str, object] = {}
                CapturingAgent.last = self

            def tool_plain(self, function: object) -> object:
                self.tools[function.__name__] = function  # type: ignore[attr-defined]
                return function

            def run_sync(self, _message: str) -> Result:
                return Result()

        with TemporaryDirectory() as directory, patch.dict(os.environ, {"DEEPSEEK_API_KEY": "test-key"}, clear=True), patch("pydantic_ai.Agent", CapturingAgent), patch("pydantic_ai.models.openai.OpenAIChatModel"), patch("pydantic_ai.providers.deepseek.DeepSeekProvider"):
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            store = CollaborationStore(root / "home")
            store.bootstrap_self_hosting(workspace)
            fake_codex = FakeCodex()
            PydanticAIGateway(AssistantService(store, fake_codex)).reply("sagitta-self-hosting", "Please understand this task")  # type: ignore[arg-type]
            tools = CapturingAgent.last.tools  # type: ignore[union-attr]
            self.assertEqual(set(tools), {"project_status", "start_codex_planning", "export_ready_goal"})
            started = json.loads(tools["start_codex_planning"]("Plan only after understanding"))  # type: ignore[operator]
            self.assertEqual(started["status"], "needs_input")
            self.assertIsNotNone(store.pending_question("sagitta-self-hosting"))

    def test_message_endpoint_serializes_missing_key_error(self) -> None:
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            client = TestClient(create_app(home=root / "home", self_hosting_workspace=workspace))
            response = client.post("/api/projects/sagitta-self-hosting/messages", json={"content": "Hello"})
            self.assertEqual(response.status_code, 503)
            self.assertEqual(response.json()["error"]["code"], "missing_deepseek_key")

    def test_console_exposes_profile_goal_and_selectable_ir_contract_details(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            run_id = ready_plan(root / "home", workspace)
            client = TestClient(create_app(home=root / "home", gateway=FakeGateway(), self_hosting_workspace=workspace))
            page = client.get("/").text
            self.assertIn('id="profile"', page)
            self.assertIn('id="plan-detail"', page)
            self.assertNotIn('id="plan"', page)
            self.assertIn("Discuss the task with Sagitta first", page)
            script = client.get("/assets/app.js").text
            self.assertIn("exportGoal", script)
            self.assertIn("renderPlanDetail", script)
            node = client.get(f"/api/projects/sagitta-self-hosting/plans/{run_id}").json()["data"]["graph"]["nodes"][0]
            self.assertEqual(node["objective"], "Change one thing.")
            self.assertEqual(node["outputs"], ["Source"])

    def test_profile_api_and_scope_graph_have_only_presentation_data(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = root / "workspace"
            workspace.mkdir()
            client = TestClient(create_app(home=root / "home", gateway=FakeGateway(), self_hosting_workspace=workspace))
            saved = client.put("/api/profile", json={"content": "# Profile\n\nPrefer small plans."}).json()["data"]
            self.assertEqual(saved["content"], "# Profile\n\nPrefer small plans.")
            self.assertEqual(client.get("/api/profile").json()["data"]["content"], saved["content"])
        graph = _ir_graph({
            "phases": [{
                "type": "scope", "id": "delivery", "entry_phase": "implement", "phases": [{
                    "type": "phase", "id": "implement", "title": "Implement", "kind": "implement",
                    "objective": "Build it.", "outputs": ["Source"], "expected_facts": ["Source exists."],
                    "on": {"done": [{"when": "$workflow.implement < 2", "target": "$complete"}, {"target": "$complete"}]},
                }],
            }],
        })
        self.assertEqual({node["id"] for node in graph["nodes"]}, {"delivery", "implement"})
        self.assertEqual(graph["nodes"][1]["outcomes"], ["done"])
        self.assertNotIn("when", json.dumps(graph))
