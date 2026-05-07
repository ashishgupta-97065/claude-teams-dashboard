from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.config import Settings
from app.services.agents import CANONICAL_AGENTS, AGENT_NAMES
from app.services import process_registry
from app.services.github_client import GitHubClient


def _load_json_array(path: Path) -> list:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []
    except (json.JSONDecodeError, OSError):
        return []


def register(app: FastAPI, settings: Settings, github: GitHubClient) -> None:

    @app.get("/api/tickets")
    async def api_tickets(request: Request) -> JSONResponse:
        issues, meta = await github.list_issues()

        tickets = []
        for issue in issues:
            if issue.github_state == "closed":
                status = "closed"
            elif process_registry.is_running(issue.number):
                status = "in-progress"
            else:
                status = "open"
            tickets.append({
                "number": issue.number,
                "title": issue.title,
                "status": status,
            })

        if not tickets and meta.stale and meta.error:
            return JSONResponse(
                status_code=503,
                content={
                    "tickets": [],
                    "fetched_at": meta.fetched_at.isoformat() + "Z",
                    "stale": True,
                    "error": meta.error,
                },
            )

        return JSONResponse({
            "tickets": tickets,
            "fetched_at": meta.fetched_at.isoformat() + "Z",
            "stale": meta.stale,
            "error": meta.error,
        })

    @app.get("/api/tickets/{ticket_number}/state")
    async def api_ticket_state(ticket_number: int) -> JSONResponse:
        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_number}"

        waiting_path = ticket_dir / "waiting_for_human.md"
        response_path = ticket_dir / "human_response.md"
        checkpoint_open = waiting_path.exists() and not response_path.exists()
        checkpoint_body: str | None = None
        if checkpoint_open:
            checkpoint_body = waiting_path.read_text(encoding="utf-8")

        agents_state: dict[str, dict] = {}
        for agent in CANONICAL_AGENTS:
            done_path = ticket_dir / f"{agent.file_basename}.done"
            conv_path = ticket_dir / "conversations" / f"{agent.file_basename}.json"

            if done_path.exists():
                status = "done"
            elif conv_path.exists():
                entries = _load_json_array(conv_path)
                status = "running" if entries else "waiting"
            else:
                status = "waiting"

            entry_count = 0
            if conv_path.exists():
                entry_count = len(_load_json_array(conv_path))

            agents_state[agent.name] = {"status": status, "entry_count": entry_count}

        all_done = all(agents_state[n]["status"] == "done" for n in AGENT_NAMES)

        return JSONResponse({
            "ticket_number": ticket_number,
            "agents": agents_state,
            "checkpoint": {"open": checkpoint_open, "body": checkpoint_body},
            "run_finished": all_done,
        })
