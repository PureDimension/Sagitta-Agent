"""Loopback FastAPI application for Sagitta's local project console."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import sys
from threading import Thread
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from starlette.concurrency import run_in_threadpool

from .assistant import AgentConfigurationError, AssistantService, ConversationGateway, PydanticAIGateway
from .codex import CodexError, CodexPlanner
from .collaboration import CollaborationStore, ProjectError
from .config import PlanningRunStore, StorageError, default_home
from .goal import GoalCompilationError
from .planning import PlanBusyError, PlanningError


LOGGER = logging.getLogger(__name__)
_ACTIVE_PLAN_STATUSES = {"planning", "repairing_ir", "reviewing_plan", "revising_plan"}


def _ok(data: Any) -> JSONResponse:
    return JSONResponse({"ok": True, "data": data})


def load_local_environment(path: Path | None = None) -> bool:
    """Load the local console's optional .env without replacing exported values."""
    return load_dotenv(dotenv_path=path or Path.cwd() / ".env", override=False)


def _server_pid_path(port: int) -> Path:
    return default_home() / f"sagitta-web-{port}.pid"


def _read_pid(path: Path) -> int | None:
    try:
        value = int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, OSError, ValueError):
        return None
    return value if value > 0 else None


def _listener_pids(port: int) -> set[int]:
    """Return listener PIDs when lsof is available on the local platform."""
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return set()
    return {int(line) for line in result.stdout.splitlines() if line.strip().isdigit()}


def _process_command(pid: int) -> str:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError:
        return ""
    return result.stdout.strip()


def _is_sagitta_web_process(pid: int) -> bool:
    command = _process_command(pid)
    return "sagitta-web" in command or "sagitta.web" in command


def _terminate_process(pid: int, timeout_seconds: float = 3.0) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    # Callers have already verified the command belongs to Sagitta. A hung
    # local server must not prevent the replacement console from starting.
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return


def _stop_previous_server(port: int, pid_path: Path) -> None:
    """Stop only prior Sagitta listeners; never terminate an unrelated port owner."""
    candidates = _listener_pids(port)
    recorded = _read_pid(pid_path)
    if recorded is not None:
        candidates.add(recorded)
    for pid in sorted(candidates):
        if pid != os.getpid() and _is_sagitta_web_process(pid):
            _terminate_process(pid)
    pid_path.unlink(missing_ok=True)


def _release_server_pid(pid_path: Path, pid: int) -> None:
    if _read_pid(pid_path) == pid:
        pid_path.unlink(missing_ok=True)


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


def _choose_directory() -> str | None:
    """Ask Finder for one project directory after an explicit local UI click."""
    if sys.platform != "darwin":
        raise ProjectError("directory_picker_unavailable", "The native project directory picker is currently available on macOS only.")
    result = subprocess.run(
        ["osascript", "-e", 'POSIX path of (choose folder with prompt "Choose a Sagitta project folder")'],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        if "User canceled" in result.stderr:
            return None
        raise ProjectError("directory_picker_failed", "Finder could not select a project directory.")
    selected = result.stdout.strip()
    if not selected:
        return None
    path = Path(selected).expanduser().resolve()
    if not path.is_dir():
        raise ProjectError("invalid_workspace", "The selected project directory is unavailable.")
    return str(path)


def _ir_graph(workflow: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(workflow, dict):
        return {"nodes": [], "edges": []}
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    phases = workflow.get("phases")
    if not isinstance(phases, list):
        return {"nodes": nodes, "edges": edges}
    for phase in phases:
        phase_id = phase.get("id")
        if not isinstance(phase_id, str):
            continue
        nodes.append(
            {
                "id": phase_id,
                "type": "phase",
                "title": phase.get("title", phase_id),
                "kind": phase.get("kind"),
                "objective": phase.get("objective"),
                "outputs": phase.get("outputs", []),
                "expected_facts": phase.get("expected_facts", []),
                "outcomes": list(phase.get("on", {})) if isinstance(phase.get("on"), dict) else [],
            }
        )
        for outcome, route in (phase.get("on") or {}).items():
            routes = [route] if isinstance(route, str) else route if isinstance(route, list) else []
            for choice in routes:
                target = choice if isinstance(choice, str) else choice.get("target") if isinstance(choice, dict) else None
                if isinstance(target, str) and target != "$complete":
                    edges.append({"from": phase_id, "to": target, "label": outcome})
    return {"nodes": nodes, "edges": edges}


def _sse(value: dict[str, Any], event_name: str = "message") -> str:
    return f"event: {event_name}\ndata: {json.dumps(value, ensure_ascii=False)}\n\n"


def _ag_ui_activity(thread_id: str, run_id: str, sequence: int, activity: dict[str, Any]) -> dict[str, Any]:
    """Map one persisted Codex JSONL event into an AG-UI custom activity."""
    raw = activity.get("event") if isinstance(activity.get("event"), dict) else {}
    item = raw.get("item") if isinstance(raw.get("item"), dict) else {}
    raw_type = raw.get("type") if isinstance(raw.get("type"), str) else "codex.event"
    item_type = item.get("type") if isinstance(item.get("type"), str) else ""
    status = "running" if raw_type.endswith("started") else "completed" if raw_type.endswith("completed") else "reported"
    kind, title, detail = "status", "Codex activity", ""
    if item_type == "command_execution":
        kind = "command"
        title = str(item.get("command") or "Codex command")
        detail = str(item.get("aggregated_output") or item.get("output") or "")
        status = "failed" if item.get("exit_code") not in {None, 0} else status
    elif item_type in {"agent_message", "reasoning"}:
        kind = "message"
        title = "Codex update"
        detail = str(item.get("text") or item.get("content") or raw.get("message") or "")
    elif raw_type == "error":
        kind, title, status = "error", "Codex reported an error", "failed"
        detail = str(raw.get("message") or raw.get("error") or "")
    elif raw_type.startswith("turn."):
        title = "Codex turn " + ("started" if raw_type.endswith("started") else "completed")
    elif raw_type.startswith("thread."):
        title = "Codex session " + ("started" if raw_type.endswith("started") else "updated")
    return {
        "type": "ACTIVITY_SNAPSHOT",
        "activityType": "sagitta.executor_activity",
        "content": {
            "id": f"codex-{sequence}",
            "at": activity.get("at"),
            "source": "codex",
            "operation": activity.get("operation", "planning"),
            "kind": kind,
            "status": status,
            "title": title[:500],
            "detail": detail[:2000],
            "raw_type": raw_type,
        },
        "threadId": thread_id,
        "runId": run_id,
    }


def create_app(
    *,
    home: Path | None = None,
    gateway: ConversationGateway | None = None,
    codex: CodexPlanner | None = None,
) -> FastAPI:
    """Create an isolated app; tests can inject a fake gateway and temporary home."""
    store = CollaborationStore(home)
    store.ensure_profile()
    service = AssistantService(store, codex)
    active_gateway = gateway or PydanticAIGateway(service)
    static = Path(__file__).parent / "web" / "static"
    app = FastAPI(title="Sagitta local console", docs_url=None, redoc_url=None)
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.middleware("http")
    async def prevent_console_asset_caching(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ProjectError)
    async def project_error(_request: Request, error: ProjectError) -> JSONResponse:
        status = 404 if error.code in {"project_not_found", "task_not_found", "plan_not_found", "goal_not_found"} else 400
        return _error(error.code, str(error), status)

    @app.exception_handler(PlanBusyError)
    async def plan_busy(_request: Request, error: PlanBusyError) -> JSONResponse:
        return _error("plan_busy", str(error), 409)

    @app.exception_handler(PlanningError)
    @app.exception_handler(GoalCompilationError)
    @app.exception_handler(CodexError)
    @app.exception_handler(StorageError)
    async def planning_error(_request: Request, error: Exception) -> JSONResponse:
        return _error("operation_failed", str(error), 400)

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, error: Exception) -> JSONResponse:
        LOGGER.exception("Unhandled Sagitta web operation", exc_info=error)
        return _error("internal_error", "Sagitta encountered an unexpected backend error. Check the server log.", 500)

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(static / "index.html")

    @app.get("/api/health")
    async def health() -> JSONResponse:
        return _ok({"binding": "loopback", "configuration": service.configuration_status()})

    @app.get("/api/settings")
    async def settings() -> JSONResponse:
        return _ok(service.configuration_status())

    @app.put("/api/settings")
    async def update_settings(request: Request) -> JSONResponse:
        payload = await _body(request)
        model = payload.get("model")
        base_url = payload.get("base_url", "")
        api_key = payload.get("api_key")
        clear_api_key = payload.get("clear_api_key", False)
        if not isinstance(model, str) or not isinstance(base_url, str) or api_key is not None and not isinstance(api_key, str) or not isinstance(clear_api_key, bool):
            raise ProjectError("invalid_request", "model, base_url, optional api_key, and clear_api_key have invalid values.")
        return _ok(service.save_model_settings(model=model, base_url=base_url, api_key=api_key, clear_api_key=clear_api_key))

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
        workspace = payload.get("workspace")
        if not isinstance(workspace, str):
            raise ProjectError("invalid_request", "workspace is required text.")
        return _ok({"project": store.register_workspace(Path(workspace))})

    @app.post("/api/system/select-directory")
    async def select_directory() -> JSONResponse:
        workspace = await run_in_threadpool(_choose_directory)
        return _ok({"status": "cancelled"} if workspace is None else {"status": "selected", "workspace": workspace})

    @app.get("/api/projects/{project_id}")
    async def project_detail(project_id: str) -> JSONResponse:
        return _ok(service.project_status(project_id))

    @app.get("/api/projects/{project_id}/tasks")
    async def tasks(project_id: str) -> JSONResponse:
        return _ok({"tasks": store.tasks(project_id)})

    @app.post("/api/projects/{project_id}/tasks")
    async def create_task(project_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ProjectError("invalid_request", "Task title must be non-empty text.")
        return _ok(store.create_task(project_id, title))

    @app.get("/api/projects/{project_id}/tasks/{task_id}")
    async def task(project_id: str, task_id: str) -> JSONResponse:
        return _ok(store.task(project_id, task_id))

    @app.delete("/api/projects/{project_id}/tasks/{task_id}")
    async def delete_task(project_id: str, task_id: str) -> JSONResponse:
        return _ok(store.delete_task(project_id, task_id))

    @app.get("/api/projects/{project_id}/tasks/{task_id}/conversation")
    async def task_conversation(project_id: str, task_id: str) -> JSONResponse:
        return _ok({"messages": store.task_messages(project_id, task_id)})

    @app.post("/api/projects/{project_id}/tasks/{task_id}/messages")
    async def send_task_message(project_id: str, task_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        content = payload.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProjectError("invalid_request", "Message content must be non-empty text.")
        try:
            return _ok(await run_in_threadpool(service.chat_task, active_gateway, project_id, task_id, content))
        except AgentConfigurationError as error:
            return _error("missing_deepseek_key", str(error), 503)

    @app.post("/api/projects/{project_id}/tasks/{task_id}/plans")
    async def start_task_plan(project_id: str, task_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        intent = payload.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise ProjectError("invalid_request", "Planning intent must be non-empty text.")
        record = service.begin_task_codex_planning(project_id, task_id, intent)

        def dispatch() -> None:
            try:
                service.run_initial_task_codex_planning(project_id, task_id)
            except Exception:
                LOGGER.exception("Codex task planning worker failed", extra={"project_id": project_id, "task_id": task_id, "run_id": record["id"]})

        Thread(target=dispatch, daemon=True, name=f"sagitta-task-{task_id[:8]}").start()
        return _ok(record)

    @app.post("/api/projects/{project_id}/tasks/{task_id}/answers")
    async def answer_task(project_id: str, task_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        answers = payload.get("answers")
        if not isinstance(answers, list):
            raise ProjectError("invalid_request", "answers are required.")
        normalized = [{"id": item.get("id"), "answer": item.get("answer")} for item in answers if isinstance(item, dict)]
        if len(normalized) != len(answers) or any(not isinstance(item["id"], str) or not isinstance(item["answer"], str) for item in normalized):
            raise ProjectError("invalid_request", "every answer requires text id and answer fields.")
        return _ok(await run_in_threadpool(service.submit_task_planner_answers, project_id, task_id, normalized))

    @app.get("/api/projects/{project_id}/tasks/{task_id}/activity")
    async def task_activity(
        project_id: str,
        task_id: str,
        request: Request,
        watch: bool = False,
        snapshot: bool = False,
    ) -> StreamingResponse:
        plan = store.task_plan(project_id, task_id)
        if plan is None:
            raise ProjectError("plan_not_found", "Task has no Plan package.")
        run_id = str(plan["id"])
        activity_path = PlanningRunStore(store.home).directory_for(run_id) / "activity.jsonl"

        async def event_stream() -> Any:
            sequence = 0
            yield _sse({"type": "RUN_STARTED", "threadId": task_id, "runId": run_id})
            while True:
                if activity_path.is_file():
                    lines = activity_path.read_text(encoding="utf-8").splitlines()
                    for raw in lines[sequence:]:
                        sequence += 1
                        try:
                            activity = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(activity, dict):
                            yield _sse(_ag_ui_activity(task_id, run_id, sequence, activity))
                if snapshot:
                    return
                record = store.task_plan(project_id, task_id)
                if record is None or record.get("status") not in _ACTIVE_PLAN_STATUSES and not (watch and record.get("status") == "needs_input"):
                    yield _sse({"type": "RUN_FINISHED", "threadId": task_id, "runId": run_id})
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.2)

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

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
            return _ok(await run_in_threadpool(service.chat, active_gateway, project_id, content))
        except AgentConfigurationError as error:
            return _error("missing_deepseek_key", str(error), 503)

    @app.get("/api/projects/{project_id}/pending-question")
    async def pending_question(project_id: str) -> JSONResponse:
        return _ok({"pending_questions": store.pending_questions(project_id)})

    @app.post("/api/projects/{project_id}/answers")
    async def answer(project_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        run_id, answers = payload.get("run_id"), payload.get("answers")
        if not isinstance(run_id, str) or not isinstance(answers, list):
            raise ProjectError("invalid_request", "run_id and answers are required.")
        normalized = [{"id": item.get("id"), "answer": item.get("answer")} for item in answers if isinstance(item, dict)]
        if len(normalized) != len(answers) or any(not isinstance(item["id"], str) or not isinstance(item["answer"], str) for item in normalized):
            raise ProjectError("invalid_request", "every answer requires text id and answer fields.")
        result = await run_in_threadpool(service.submit_planner_answers, project_id, run_id, normalized)
        store.append_message(project_id, "assistant", "Sagitta submitted the complete planner answer round.", metadata={"plan_id": run_id})
        return _ok(result)

    @app.get("/api/projects/{project_id}/plans")
    async def plans(project_id: str) -> JSONResponse:
        return _ok({"plans": store.plans(project_id)})

    @app.post("/api/projects/{project_id}/plans")
    async def start_plan(project_id: str, request: Request) -> JSONResponse:
        payload = await _body(request)
        intent = payload.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise ProjectError("invalid_request", "Planning intent must be non-empty text.")
        record = service.begin_codex_planning(project_id, intent)

        def dispatch() -> None:
            try:
                service.run_initial_codex_planning(project_id, record["id"])
            except Exception:
                LOGGER.exception("Codex planning worker failed", extra={"project_id": project_id, "run_id": record["id"]})

        Thread(target=dispatch, daemon=True, name=f"sagitta-plan-{record['id'][:8]}").start()
        return _ok(record)

    @app.get("/api/projects/{project_id}/plans/{run_id}")
    async def plan(project_id: str, run_id: str) -> JSONResponse:
        value = store.plan(project_id, run_id)
        value["graph"] = _ir_graph(value.get("ir"))
        return _ok(value)

    @app.get("/api/projects/{project_id}/plans/{run_id}/activity")
    async def plan_activity(
        project_id: str,
        run_id: str,
        request: Request,
        watch: bool = False,
        snapshot: bool = False,
    ) -> StreamingResponse:
        """Expose one Plan's Codex trace as an AG-UI-compatible SSE event stream."""
        store.plan(project_id, run_id)
        activity_path = PlanningRunStore(store.home).directory_for(run_id) / "activity.jsonl"

        async def event_stream() -> Any:
            sequence = 0
            yield _sse({"type": "RUN_STARTED", "threadId": project_id, "runId": run_id})
            while True:
                if activity_path.is_file():
                    lines = activity_path.read_text(encoding="utf-8").splitlines()
                    for raw in lines[sequence:]:
                        sequence += 1
                        try:
                            activity = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if isinstance(activity, dict):
                            yield _sse(_ag_ui_activity(project_id, run_id, sequence, activity))
                if snapshot:
                    return
                record = store.plan(project_id, run_id)
                if record.get("status") not in _ACTIVE_PLAN_STATUSES and not (watch and record.get("status") == "needs_input"):
                    yield _sse({"type": "RUN_FINISHED", "threadId": project_id, "runId": run_id})
                    return
                if await request.is_disconnected():
                    return
                await asyncio.sleep(0.2)

        return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.delete("/api/projects/{project_id}/plans/{run_id}")
    async def delete_plan(project_id: str, run_id: str) -> JSONResponse:
        return _ok(store.delete_plan(project_id, run_id))

    @app.post("/api/projects/{project_id}/plans/{run_id}/goal")
    async def export_goal(project_id: str, run_id: str) -> JSONResponse:
        return _ok(service.export_goal(project_id, run_id))

    @app.get("/api/projects/{project_id}/plans/{run_id}/goal")
    async def goal(project_id: str, run_id: str) -> JSONResponse:
        return _ok(store.read_goal(project_id, run_id))

    @app.get("/api/projects/{project_id}/goal-state")
    async def goal_state(project_id: str) -> JSONResponse:
        return _ok(store.goal_state(project_id))

    @app.get("/api/projects/{project_id}/plans/{run_id}/artifacts")
    async def plan_artifacts(project_id: str, run_id: str) -> JSONResponse:
        return _ok({"artifacts": store.plan_artifacts(project_id, run_id)})

    @app.get("/api/projects/{project_id}/plans/{run_id}/artifacts/{artifact_id}")
    async def plan_artifact(project_id: str, run_id: str, artifact_id: str) -> JSONResponse:
        return _ok(store.read_plan_artifact(project_id, run_id, artifact_id))

    return app


def main() -> None:
    """Replace a prior Sagitta instance, then run on the configured local address."""
    import uvicorn

    load_local_environment()
    host = os.environ.get("SAGITTA_HOST", "127.0.0.1")
    port = int(os.environ.get("SAGITTA_PORT", "8123"))
    pid_path = _server_pid_path(port)
    _stop_previous_server(port, pid_path)
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid = os.getpid()
    pid_path.write_text(f"{pid}\n", encoding="utf-8")
    try:
        uvicorn.run(create_app(), host=host, port=port)
    finally:
        _release_server_pid(pid_path, pid)


if __name__ == "__main__":
    main()
