from __future__ import annotations

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.services import process_registry
from app.services.github_client import GitHubClient
from app.services.pipeline_runner import build_command


def register(app: FastAPI, settings: Settings, github: GitHubClient) -> None:

    @app.post("/run/{ticket_number}")
    async def trigger_run(request: Request, ticket_number: int) -> JSONResponse:
        issues, _ = await github.list_issues()
        for issue in issues:
            if issue.number == ticket_number and issue.github_state == "closed":
                raise HTTPException(status_code=409, detail={"error": "ticket_closed"})

        if process_registry.is_running(ticket_number):
            return JSONResponse(
                status_code=202,
                content={"ticket_number": ticket_number, "running": True, "spawned": False},
            )

        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_number}"
        ticket_dir.mkdir(parents=True, exist_ok=True)

        command, cwd = build_command(ticket_number, settings)
        spawned = process_registry.start(ticket_number, command, cwd)

        return JSONResponse(
            status_code=202,
            content={"ticket_number": ticket_number, "running": True, "spawned": spawned},
        )

    @app.post("/run/{ticket_number}/human_response")
    async def human_response(
        ticket_number: int,
        body: str = Form(..., max_length=65536),
    ) -> JSONResponse:
        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_number}"
        if not ticket_dir.exists():
            raise HTTPException(status_code=404, detail="Ticket workspace not found")

        response_path = ticket_dir / "human_response.md"
        if response_path.exists():
            return JSONResponse(
                status_code=409,
                content={"written": False, "error": "already_exists"},
            )

        response_path.write_text(body, encoding="utf-8")
        return JSONResponse({"written": True})
