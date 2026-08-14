"""Loopback FastAPI application for Sagitta's local project console."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

from .assistant import AgentConfigurationError, AssistantService, ConversationGateway, PydanticAIGateway
from .codex import CodexError, CodexPlanner
from .collaboration import CollaborationStore, ProjectError
from .config import StorageError
from .goal import GoalCompilationError
from .planning import PlanningError


def _ok(data: Any) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def load_local_environment(path: Path | None = None) -> bool:
    """Load the local console's optional .env without replacing exported values."""
    return load_dotenv(dotenv_path=path or Path.cwd() / ".env", override=False)


def _error(code: str, message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": {"code": code, "message": message}}, status_code=status_code)


async def _body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except Exception as error:
        raise ProjectError("invalid_request", "Request body must be a JSON object.") from error
    if not isinstance(value, dict):
        raise ProjectError("invalid_request", "Request body must be a JSON object.")
    return value


def _ir_graph(workflow: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(workflow, dict):
        return {"nodes": [], "edges": []}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def visit(items: list[dict[str, Any]], parent: str | None = None) -> None:
        for item in items:
            node_id = item.get("id")
            if not isinstance(node_id, str):
                continue
            node = {
                "id": node_id,
                "type": item.get("type"),
                "title": item.get("title", node_id),
                "kind": item.get("kind"),
                "parent": parent,
                "objective": item.get("objective"),
                "outputs": item.get("outputs", []),
                "expected_facts": item.get("expected_facts", []),
                "outcomes": list(item.get("on", {})) if isinstance(item.get("on"), dict) else [],
            }
            nodes.append(node)
            if item.get("type") == "scope":
                entry = item.get("entry_phase")
                if isinstance(entry, str):
                    edges.append({"from": node_id, "to": entry, "label": "entry"})
                children = item.get("phases")
                if isinstance(children, list):
                    visit(children, node_id)
                continue
            for outcome, route in (item.get("on") or {}).items():
                routes = [route] if isinstance(route, str) else route if isinstance(route, list) else []
                for choice in routes:
                    target = choice if isinstance(choice, str) else choice.get("target") if isinstance(choice, dict) else None
                    if isinstance(target, str) and target != "$complete":
                        edges.append({"from": node_id, "to": target, "label": outcome})

    phases = workflow.get("phases")
    if isinstance(phases, list):
        visit(phases)
    return {"nodes": nodes, "edges": edges}


def create_app(
    *,
    home: Path | None = None,
    gateway: ConversationGateway | None = None,
    codex: CodexPlanner | None = None,
    self_hosting_workspace: Path | None = None,
) -> FastAPI:
    """Create an isolated app; tests can inject a fake gateway and temporary home."""
    store = CollaborationStore(home)
    store.ensure_profile()
    if self_hosting_workspace is not None:
        store.bootstrap_self_hosting(self_hosting_workspace)
    service = AssistantService(store, codex)
    active_gateway = gateway or PydanticAIGateway(service)
    static = Path(__file__).parent / "web" / "static"
    app = FastAPI(title="Sagitta local console", docs_url=None, redoc_url=None)
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.exception_handler(ProjectError)
    async def project_error(_request: Request, error: ProjectError) -> JSONResponse:
        status = 404 if error.code in {"project_not_found", "plan_not_found", "goal_not_found"} else 400
        return _error(error.code, str(error), status)

    @app.exception_handler(PlanningError)
    @app.exception_handler(GoalCompilationError)
    @app.exception_handler(CodexError)
    @app.exception_handler(StorageError)
    async def planning_error(_request: Request, error: Exception) -> JSONResponse:
        return _error("operation_failed", str(error), 400)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return _ok({"binding": "loopback", "configuration": service.configuration_status()})

    @app.get("/api/profile")
    async def profile() -> JSONResponse:
        return _ok({"content": store.read_profile()})

    @app.put("/api/profile")
    async def update_profile(request: Request) -> JSONResponse:
        payload = await _body(request)
        content = payload.get("content")
        if not isinstance(content, str):
            raise ProjectError("invalid_request", "Profile content must be text.")
        store.write_profile(content)
        return _ok({"content": store.read_profile()})

    @app.get("/api/projects")
    async def projects() -> JSONResponse:
        return _ok({"projects": store.list_projects()})

    @app.post("/api/projects")
    async def register_project(request: Request) -> JSONResponse:
        payload = await _body(request)
        project_id, label, workspace = payload.get("id"), payload.get("label"), payload.get("workspace")
        if not all(isinstance(value, str) for value in (project_id, label, workspace)):
            raise ProjectError("invalid_request", "id, label, and workspace are required text fields.")
        return _ok({"project": store.register_project(project_id, label, Path(workspace))})

    @app.get("/api/projects/{project_id}")
    async def project_detail(project_id: str) -> JSONResponse:
        return _ok(service.project_status(project_id))

    @app.get("/api/projects/{project_id}/conversation")
    async def conversation(project_id: str) -> JSONResponse:
        return _ok({"messages": store.messages(project_id), "summary_location": "reserved for future conversation compression"})

    @app.post("/api/projects/{project_id}/messages")
    async def send_message(project_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProjectError("invalid_request", "Message content must be non-empty text.")
        try:
            return _ok(service.chat(active_gateway, project_id, content))
        except AgentConfigurationError as error:
            return _error("missing_deepseek_key", str(error), 503)

    @app.get("/api/projects/{project_id}/pending-question")
    async def pending_question(project_id: str) -> JSONResponse:
        return _ok({"pending_question": store.pending_question(project_id)})

    @app.post("/api/projects/{project_id}/answers")
    async def answer(project_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        values = (payload.get("run_id"), payload.get("question_id"), payload.get("answer"))
        if not all(isinstance(value, str) and value.strip() for value in values):
            raise ProjectError("invalid_request", "run_id, question_id, and answer are required text fields.")
        result = service.submit_planner_answer(project_id, values[0], values[1], values[2])
        store.append_message(project_id, "assistant", "Codex planning resumed after your explicit answer.", metadata={"plan_id": values[0]})
        return _ok(result)

    @app.get("/api/projects/{project_id}/plans")
    async def plans(project_id: str) -> JSONResponse:
        return _ok({"plans": store.plans(project_id)})

    @app.get("/api/projects/{project_id}/plans/{run_id}")
    async def plan(project_id: str, run_id: str) -> JSONResponse:
        value = store.plan(project_id, run_id)
        value["graph"] = _ir_graph(value.get("ir"))
        return _ok(value)

    @app.post("/api/projects/{project_id}/plans/{run_id}/goal")
    async def export_goal(project_id: str, run_id: str) -> JSONResponse:
        return _ok(service.export_goal(project_id, run_id))

    @app.get("/api/projects/{project_id}/plans/{run_id}/goal")
    async def goal(project_id: str, run_id: str) -> JSONResponse:
        return _ok(store.read_goal(project_id, run_id))

    @app.get("/api/projects/{project_id}/goal-state")
    async def goal_state(project_id: str) -> JSONResponse:
        return _ok(store.goal_state(project_id))

    return app


def main() -> None:
    """Run the console on a loopback address unless explicitly overridden."""
    import uvicorn

    load_local_environment()
    host = os.environ.get("SAGITTA_HOST", "127.0.0.1")
    port = int(os.environ.get("SAGITTA_PORT", "8123"))
    uvicorn.run(create_app(self_hosting_workspace=Path.cwd()), host=host, port=port)


if __name__ == "__main__":
    main()
