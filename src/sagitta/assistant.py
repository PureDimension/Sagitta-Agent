"""Controlled Sagitta conversation and delegation boundary."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Protocol

from .codex import CodexPlanner
from .collaboration import CollaborationStore, ProjectError
from .config import PlanningRunStore
from .goal import GoalService
from .planning import PlanningService


class AgentConfigurationError(RuntimeError):
    """Raised before a real model call when local configuration is absent."""


class ConversationGateway(Protocol):
    def reply(self, project_id: str, message: str) -> str: ...


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

    def configuration_status(self) -> dict[str, str]:
        if not os.environ.get("DEEPSEEK_API_KEY"):
            return {"status": "missing_key", "message": "Set DEEPSEEK_API_KEY before sending a live chat message."}
        return {"status": "configured", "message": "DeepSeek key is available to the local process."}

    def project_status(self, project_id: str) -> dict[str, Any]:
        project = self.store.resolve_project(project_id)
        return {"project": project, "plans": self.store.plans(project_id), "pending_question": self.store.pending_question(project_id), "goal_state": self.store.goal_state(project_id)}

    def _planner(self, project_id: str) -> PlanningService:
        project = self.store.resolve_project(project_id)
        return PlanningService(_ProjectConfig(Path(project["workspace"])), PlanningRunStore(self.store.home), self.codex)

    def start_codex_planning(self, project_id: str, intent: str) -> dict[str, Any]:
        result = self._planner(project_id).plan(intent)
        return {key: result.get(key) for key in ("id", "status", "intent", "response", "updated_at")}

    def submit_planner_answer(self, project_id: str, run_id: str, question_id: str, answer: str) -> dict[str, Any]:
        self.store.plan(project_id, run_id)
        result = self._planner(project_id).answer(run_id, question_id, answer)
        return {key: result.get(key) for key in ("id", "status", "response", "updated_at")}

    def export_goal(self, project_id: str, run_id: str) -> dict[str, str]:
        self.store.plan(project_id, run_id)
        GoalService(PlanningRunStore(self.store.home)).export(run_id)
        return {"path": "goal/GOAL.md", "status": "exported"}

    def chat(self, gateway: ConversationGateway, project_id: str, message: str) -> dict[str, Any]:
        self.store.resolve_project(project_id)
        self.store.append_message(project_id, "user", message)
        reply = gateway.reply(project_id, message)
        self.store.append_message(project_id, "assistant", reply)
        return {"reply": reply, "pending_question": self.store.pending_question(project_id)}


SYSTEM_INSTRUCTIONS = """You are Sagitta, a high-agency development collaborator. Understand a task before starting Codex planning, point out material blind spots, and preserve the user's control over decisions. You may inspect a registered project's status, start Codex planning only after understanding the intent, and export a ready Goal. Codex planner questions must be returned to the user with context; never answer or resume a planner question yourself. You have no shell, source-edit, arbitrary filesystem, API-key, or environment access."""


class PydanticAIGateway:
    """Creates the real PydanticAI/DeepSeek loop lazily, at request time only."""

    def __init__(self, service: AssistantService) -> None:
        self.service = service

    def reply(self, project_id: str, message: str) -> str:
        key = os.environ.get("DEEPSEEK_API_KEY")
        if not key:
            raise AgentConfigurationError("DEEPSEEK_API_KEY is not configured. Run: export DEEPSEEK_API_KEY=...")
        base_url = os.environ.get("DEEPSEEK_BASE_URL")
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.deepseek import DeepSeekProvider

        if base_url:
            from openai import AsyncOpenAI

            provider = DeepSeekProvider(openai_client=AsyncOpenAI(api_key=key, base_url=base_url))
        else:
            provider = DeepSeekProvider(api_key=key)
        model = OpenAIChatModel("deepseek-chat", provider=provider)
        agent = Agent(model, instructions=SYSTEM_INSTRUCTIONS)

        @agent.tool_plain
        def project_status() -> str:
            return json.dumps(self.service.project_status(project_id), ensure_ascii=False)

        @agent.tool_plain
        def start_codex_planning(intent: str) -> str:
            return json.dumps(self.service.start_codex_planning(project_id, intent), ensure_ascii=False)

        @agent.tool_plain
        def export_ready_goal(run_id: str) -> str:
            return json.dumps(self.service.export_goal(project_id, run_id), ensure_ascii=False)

        result = agent.run_sync(message)
        return str(result.output)
