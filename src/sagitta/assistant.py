"""Controlled Sagitta conversation and delegation boundary."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

from .codex import CodexPlanner
from .collaboration import CollaborationStore, ProjectError
from .config import ModelSettingsStore, PlanningRunStore
from .goal import GoalService
from .planning import PlanningService


class AgentConfigurationError(RuntimeError):
    """Raised before a real model call when local configuration is absent."""


class ConversationGateway(Protocol):
    def reply(self, project_id: str, message: str, *, task_id: str | None = None) -> str: ...


class _ProjectConfig:
    """PlanningService-compatible config that never changes global CLI config."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def load(self) -> dict[str, str]:
        return {"workspace": str(self.workspace)}


class AssistantService:
    """Owns the user-visible operations; it never exposes arbitrary workspace access."""

    def __init__(self, store: CollaborationStore, codex: CodexPlanner | None = None) -> None:
        self.store = store
        self.codex = codex or CodexPlanner()
        self.model_settings = ModelSettingsStore(store.home)

    def configuration_status(self) -> dict[str, Any]:
        settings = self.model_settings.display()
        if not settings["api_key_configured"]:
            return {**settings, "status": "missing_key", "message": "Configure a model API key to send a live Sagitta message."}
        return {**settings, "status": "configured", "message": f"{settings['model']} is configured for the local Sagitta agent."}

    def save_model_settings(self, *, model: str, base_url: str, api_key: str | None, clear_api_key: bool = False) -> dict[str, Any]:
        return self.model_settings.save(model=model, base_url=base_url, api_key=api_key, clear_api_key=clear_api_key)

    def project_status(self, project_id: str) -> dict[str, Any]:
        project = self.store.resolve_project(project_id)
        return {"project": project, "plans": self.store.plans(project_id), "pending_questions": self.store.pending_questions(project_id), "goal_state": self.store.goal_state(project_id)}

    def task_status(self, project_id: str, task_id: str) -> dict[str, Any]:
        project = self.store.resolve_project(project_id)
        task = self.store.task(project_id, task_id)
        return {"project": project, "task": task, "plan": self.store.task_plan(project_id, task_id)}

    def _planner(self, project_id: str) -> PlanningService:
        project = self.store.resolve_project(project_id)
        return PlanningService(_ProjectConfig(Path(project["workspace"])), PlanningRunStore(self.store.home), self.codex)

    def start_codex_planning(self, project_id: str, intent: str) -> dict[str, Any]:
        result = self._planner(project_id).plan(intent)
        return {key: result.get(key) for key in ("id", "status", "intent", "response", "updated_at")}

    def begin_codex_planning(self, project_id: str, intent: str) -> dict[str, Any]:
        """Create a visible Plan record before the web console dispatches Codex."""
        result = self._planner(project_id).begin(intent)
        return {key: result.get(key) for key in ("id", "status", "intent", "response", "updated_at")}

    def begin_task_codex_planning(self, project_id: str, task_id: str, intent: str) -> dict[str, Any]:
        if self.store.task_plan(project_id, task_id) is not None:
            raise ProjectError("task_already_planned", "This Task already has a Plan package.")
        result = self._planner(project_id).begin(intent, task_id=task_id)
        self.store.attach_plan(project_id, task_id, str(result["id"]))
        self.store.append_task_message(project_id, task_id, "user", intent, metadata={"route": "direct"})
        return {key: result.get(key) for key in ("id", "task_id", "status", "intent", "response", "updated_at")}

    def run_initial_codex_planning(self, project_id: str, run_id: str) -> dict[str, Any]:
        self.store.plan(project_id, run_id)
        result = self._planner(project_id).run_initial(run_id)
        return {key: result.get(key) for key in ("id", "status", "intent", "response", "updated_at")}

    def run_initial_task_codex_planning(self, project_id: str, task_id: str) -> dict[str, Any]:
        plan = self.store.task_plan(project_id, task_id)
        if plan is None:
            raise ProjectError("plan_not_found", "Task has no Plan package.")
        result = self.run_initial_codex_planning(project_id, str(plan["id"]))
        self._append_planner_update(project_id, task_id, result)
        return result

    def start_task_codex_planning(self, project_id: str, task_id: str, intent: str) -> dict[str, Any]:
        """Tool-facing Sagitta path: create and immediately run the Task Plan."""
        self.begin_task_codex_planning(project_id, task_id, intent)
        return self.run_initial_task_codex_planning(project_id, task_id)

    def submit_planner_answer(self, project_id: str, run_id: str, question_id: str, answer: str) -> dict[str, Any]:
        self.store.plan(project_id, run_id)
        result = self._planner(project_id).answer(run_id, question_id, answer)
        return {key: result.get(key) for key in ("id", "status", "response", "updated_at")}

    def submit_planner_answers(self, project_id: str, run_id: str, answers: list[dict[str, str]]) -> dict[str, Any]:
        self.store.plan(project_id, run_id)
        result = self._planner(project_id).answer_many(run_id, answers)
        return {key: result.get(key) for key in ("id", "status", "response", "updated_at")}

    def submit_task_planner_answers(self, project_id: str, task_id: str, answers: list[dict[str, str]]) -> dict[str, Any]:
        plan = self.store.task_plan(project_id, task_id)
        if plan is None:
            raise ProjectError("plan_not_found", "Task has no Plan package.")
        answer_text = "\n".join(f"{item['id']}: {item['answer']}" for item in answers)
        self.store.append_task_message(project_id, task_id, "user", answer_text, metadata={"route": "direct", "kind": "planner_answers"})
        result = self.submit_planner_answers(project_id, str(plan["id"]), answers)
        self._append_planner_update(project_id, task_id, result)
        return result

    def export_goal(self, project_id: str, run_id: str) -> dict[str, str]:
        self.store.plan(project_id, run_id)
        GoalService(PlanningRunStore(self.store.home)).export(run_id)
        return {"path": "goal/GOAL.md", "status": "exported"}

    def chat(self, gateway: ConversationGateway, project_id: str, message: str) -> dict[str, Any]:
        self.store.resolve_project(project_id)
        self.store.append_message(project_id, "user", message)
        reply = gateway.reply(project_id, message)
        self.store.append_message(project_id, "assistant", reply)
        return {"reply": reply, "pending_questions": self.store.pending_questions(project_id)}

    def chat_task(self, gateway: ConversationGateway, project_id: str, task_id: str, message: str) -> dict[str, Any]:
        self.store.task(project_id, task_id)
        self.store.append_task_message(project_id, task_id, "user", message, metadata={"route": "sagitta"})
        reply = gateway.reply(project_id, message, task_id=task_id)
        self.store.append_task_message(project_id, task_id, "assistant", reply, metadata={"route": "sagitta"})
        return {"reply": reply, "plan": self.store.task_plan(project_id, task_id)}

    def _append_planner_update(self, project_id: str, task_id: str, result: dict[str, Any]) -> None:
        response = result.get("response")
        if not isinstance(response, dict):
            return
        summary = response.get("summary")
        questions = response.get("questions")
        parts = [summary] if isinstance(summary, str) and summary.strip() else []
        if isinstance(questions, list) and questions:
            parts.append("Questions to settle before offline work:\n" + "\n".join(
                f"{index + 1}. {item.get('question', '')}\n   Why: {item.get('reason', '')}"
                for index, item in enumerate(questions) if isinstance(item, dict)
            ))
        if parts:
            self.store.append_task_message(project_id, task_id, "assistant", "\n\n".join(parts), metadata={"route": "direct", "kind": "planner_update"})


SYSTEM_INSTRUCTIONS = """You are Sagitta, a high-agency development collaborator. Understand a task before starting Codex planning, point out material blind spots, and preserve the user's control over decisions. You may inspect a registered project's status, start Codex planning only after understanding the intent, submit a complete planner-answer round when the user's conversation already settles each question, and export a ready Goal. You may make an informed recommendation, but never fabricate a user decision: return unresolved planner questions to the user with context. You have no shell, source-edit, arbitrary filesystem, API-key, or environment access."""


class PydanticAIGateway:
    """Creates the real PydanticAI/DeepSeek loop lazily, at request time only."""

    def __init__(self, service: AssistantService) -> None:
        self.service = service

    def reply(self, project_id: str, message: str, *, task_id: str | None = None) -> str:
        settings = self.service.model_settings.effective()
        key = settings["api_key"]
        if not key:
            raise AgentConfigurationError("Sagitta model API key is not configured. Open Settings to add one.")
        base_url = settings["base_url"]
        from pydantic_ai import Agent
        from pydantic_ai.messages import ModelMessagesTypeAdapter
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider

        if base_url:
            from openai import AsyncOpenAI

            provider = DeepSeekProvider(openai_client=AsyncOpenAI(api_key=key, base_url=base_url))
        else:
            provider = DeepSeekProvider(api_key=key)
        model = OpenAIChatModel(str(settings["model"]), provider=provider)
        agent = Agent(model, instructions=SYSTEM_INSTRUCTIONS)

        @agent.tool_plain
        def project_status() -> str:
            status = self.service.task_status(project_id, task_id) if task_id else self.service.project_status(project_id)
            return json.dumps(status, ensure_ascii=False)

        @agent.tool_plain
        def start_codex_planning(intent: str) -> str:
            if task_id:
                started = self.service.start_task_codex_planning(project_id, task_id, intent)
                return json.dumps(started, ensure_ascii=False)
            return json.dumps(self.service.start_codex_planning(project_id, intent), ensure_ascii=False)

        @agent.tool_plain
        def submit_planner_answers(run_id: str, answers: list[dict[str, str]]) -> str:
            """Advance a planner only when this user turn settles every currently pending question."""
            if task_id:
                return json.dumps(self.service.submit_task_planner_answers(project_id, task_id, answers), ensure_ascii=False)
            return json.dumps(self.service.submit_planner_answers(project_id, run_id, answers), ensure_ascii=False)

        @agent.tool_plain
        def export_ready_goal(run_id: str) -> str:
            return json.dumps(self.service.export_goal(project_id, run_id), ensure_ascii=False)

        history_text = self.service.store.read_task_agent_history(project_id, task_id) if task_id else self.service.store.read_agent_history(project_id)
        history = ModelMessagesTypeAdapter.validate_json(history_text) if history_text else None
        result = agent.run_sync(message, message_history=history)
        if hasattr(result, "all_messages"):
            serialized = ModelMessagesTypeAdapter.dump_json(result.all_messages()).decode("utf-8")
            if task_id:
                self.service.store.write_task_agent_history(project_id, task_id, serialized)
            else:
                self.service.store.write_agent_history(project_id, serialized)
        return str(result.output)
