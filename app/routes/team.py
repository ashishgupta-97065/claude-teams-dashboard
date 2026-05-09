from __future__ import annotations

import logging
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, PositiveInt

from app.config import Settings
from app.services.team_agents import (
    AgentNotFoundError,
    FrontmatterParseError,
    InvalidModelError,
    list_agents,
    load_agent,
    patch_agent_model,
    to_api_dict,
)
from app.services.team_config import (
    ConfigNotFoundError,
    ConfigParseError,
    load_config,
    save_config_partial,
)
from app.services.team_queue import QueueParseError, load_queue, save_queue

logger = logging.getLogger(__name__)

_TRAVERSAL_CHARS = frozenset(["/", "\\", "."])


class AgentPatch(BaseModel):
    model: Literal["claude-opus-4-7", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"]


class ConfigPatch(BaseModel):
    loop_cap: int = Field(ge=1)
    human_mode: Literal["active_discussion", "task_confirmation_only", "no_human"]
    agents: list[str]


class QueuePatch(BaseModel):
    tickets: list[PositiveInt]


def _safe_agent_name(name: str) -> str:
    """Reject path traversal characters. Returns clean name or raises HTTPException 400."""
    if not name:
        raise HTTPException(status_code=400, detail="Agent name must not be empty")
    if name.startswith("."):
        raise HTTPException(status_code=400, detail=f"Invalid agent name: {name!r}")
    for ch in ("/", "\\", ".."):
        if ch in name:
            raise HTTPException(status_code=400, detail=f"Invalid agent name: {name!r}")
    if ".." in name:
        raise HTTPException(status_code=400, detail=f"Invalid agent name: {name!r}")
    return name


def register(
    app: FastAPI,
    templates: Jinja2Templates,
    settings: Settings,
) -> None:
    """Register seven routes (one HTML, six JSON) on app. Closure captures
    settings.worksite_path (for config + queue) and settings.agents_dir."""

    agents_dir = settings.agents_dir
    config_path = settings.worksite_path / "team.config.json"
    queue_path = settings.worksite_path / "queue.json"

    # ── Pydantic validation → 400 (not 422) ─────────────────────────────────
    # We install a RequestValidationError handler scoped to /api/ paths.
    # If the path is not a team API route we re-raise so the default handler wins.

    @app.exception_handler(RequestValidationError)
    async def _validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Only translate validation errors on our three mutation endpoints
        team_api_prefixes = (
            "/api/agents/",
            "/api/config",
            "/api/queue",
        )
        path = request.url.path
        if any(path == prefix or path.startswith(prefix) for prefix in team_api_prefixes):
            errors = exc.errors()
            first_msg = errors[0]["msg"] if errors else "Validation error"
            return JSONResponse(status_code=400, content={"error": first_msg})
        # Fall through for other routes (return the default 422 behavior)
        from fastapi.exception_handlers import request_validation_exception_handler
        return await request_validation_exception_handler(request, exc)

    # ── HTML page ─────────────────────────────────────────────────────────────

    @app.get("/team", response_class=HTMLResponse)
    async def team_page(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "team.html",
            {"repo": settings.github_repo, "request": request},
        )

    # ── GET /api/agents ───────────────────────────────────────────────────────

    @app.get("/api/agents")
    async def get_agents() -> list[dict]:
        try:
            records = list_agents(agents_dir)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Cannot read agents directory: {exc}")
        return [to_api_dict(r) for r in records]

    # ── PATCH /api/agents/{name} ──────────────────────────────────────────────

    @app.patch("/api/agents/{name}")
    async def patch_agent(name: str, body: AgentPatch) -> dict:
        safe_name = _safe_agent_name(name)
        try:
            rec = patch_agent_model(agents_dir, safe_name, body.model)
        except AgentNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except InvalidModelError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except FrontmatterParseError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Write failure: {exc}")
        return to_api_dict(rec)

    # ── GET /api/config ───────────────────────────────────────────────────────

    @app.get("/api/config")
    async def get_config() -> dict:
        try:
            return load_config(config_path)
        except ConfigNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ConfigParseError as exc:
            raise HTTPException(status_code=500, detail=str(exc))

    # ── POST /api/config ──────────────────────────────────────────────────────

    @app.post("/api/config")
    async def post_config(body: ConfigPatch) -> dict:
        try:
            return save_config_partial(
                config_path,
                loop_cap=body.loop_cap,
                human_mode=body.human_mode,
                agents=body.agents,
            )
        except ConfigNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        except ConfigParseError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Write failure: {exc}")

    # ── GET /api/queue ────────────────────────────────────────────────────────

    @app.get("/api/queue")
    async def get_queue() -> dict:
        try:
            tickets = load_queue(queue_path)
        except QueueParseError as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        return {"tickets": tickets}

    # ── POST /api/queue ───────────────────────────────────────────────────────

    @app.post("/api/queue")
    async def post_queue(body: QueuePatch) -> dict:
        tickets = [int(t) for t in body.tickets]
        try:
            result = save_queue(queue_path, tickets)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Write failure: {exc}")
        return {"tickets": result}
