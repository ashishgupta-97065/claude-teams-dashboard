from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import Settings, load_settings
from app.services import process_registry
from app.services import workspace_fs as workspace_fs_mod
from app.services.github_client import GitHubClient
from app.services.agents import CANONICAL_AGENTS


def create_app(settings: Settings | None = None, github: GitHubClient | None = None) -> FastAPI:
    """Build the FastAPI instance. Returns the app — exposed for tests."""
    if settings is None:
        settings = load_settings()

    _settings = settings

    # Wire workspace_fs WORKSPACE_ROOT so routes resolve correctly for this worksite
    workspace_fs_mod.WORKSPACE_ROOT = _settings.worksite_path / "workspace"

    http_client = httpx.AsyncClient()
    if github is None:
        github = GitHubClient(
            repo=_settings.github_repo,
            token=_settings.github_token,
            http=http_client,
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.github = github

        async def reap_loop() -> None:
            while True:
                await asyncio.sleep(5)
                process_registry.reap_finished()

        reaper_task = asyncio.ensure_future(reap_loop())
        try:
            yield
        finally:
            reaper_task.cancel()
            try:
                await reaper_task
            except asyncio.CancelledError:
                pass
            await http_client.aclose()

    app = FastAPI(title="Claude Teams Dashboard", lifespan=lifespan)

    static_dir = Path(__file__).parent.parent / "static"
    templates_dir = Path(__file__).parent.parent / "templates"

    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    templates = Jinja2Templates(directory=str(templates_dir))
    templates.env.globals["CANONICAL_AGENTS"] = CANONICAL_AGENTS

    from app.routes import pages as pages_mod
    from app.routes import tickets as tickets_mod
    from app.routes import run as run_mod
    from app.routes import stream as stream_mod
    from app.routes import team as team_mod
    from app.routes import workspace as workspace_mod
    from app.routes import review as review_mod
    from app.services.review import format_duration

    templates.env.filters["duration"] = format_duration  # AC8 single source of truth

    pages_mod.register(app, templates, _settings, github)
    tickets_mod.register(app, _settings, github)
    run_mod.register(app, _settings, github)
    stream_mod.register(app, _settings)
    team_mod.register(app, templates, _settings)
    app.include_router(workspace_mod.router)
    review_mod.register(app, _settings)  # JSON endpoints (§3.2–§3.4)

    return app


if __name__ == "__main__":
    settings = load_settings()
    uvicorn.run(
        create_app(settings),
        host=settings.bind_host,
        port=settings.port,
    )
