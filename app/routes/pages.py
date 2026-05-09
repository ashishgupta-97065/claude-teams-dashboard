from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings
from app.services.agents import CANONICAL_AGENTS, ORCHESTRATOR_AGENT
from app.services import process_registry
from app.services.github_client import GitHubClient


def _worksite_name(settings: Settings) -> str:
    """Return the worksite identifier for SSE URLs — parent directory name of worksite_path."""
    return settings.worksite_path.parent.name


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


def register(
    app: FastAPI,
    templates: Jinja2Templates,
    settings: Settings,
    github: GitHubClient,
) -> None:

    @app.get("/", response_class=HTMLResponse)
    async def list_page(request: Request) -> HTMLResponse:
        issues, meta = await github.list_issues()
        for issue in issues:
            if issue.github_state == "closed":
                issue.status = "closed"
            elif process_registry.is_running(issue.number):
                issue.status = "in-progress"
            else:
                issue.status = "open"

        return templates.TemplateResponse(
            request,
            "list.html",
            {
                "tickets": issues,
                "repo": settings.github_repo,
                "stale": meta.stale,
                "error": meta.error,
                "fetched_at": meta.fetched_at.strftime("%H:%M:%S"),
            },
        )

    @app.get("/run/{ticket_number}", response_class=HTMLResponse)
    async def viewer_page(request: Request, ticket_number: int) -> HTMLResponse:
        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_number}"

        issues, _ = await github.list_issues()
        issue_title = f"Ticket #{ticket_number}"
        for issue in issues:
            if issue.number == ticket_number:
                issue_title = issue.title
                break

        waiting_path = ticket_dir / "waiting_for_human.md"
        response_path = ticket_dir / "human_response.md"
        checkpoint_open = waiting_path.exists() and not response_path.exists()
        checkpoint_body = ""
        if checkpoint_open:
            checkpoint_body = waiting_path.read_text(encoding="utf-8")

        is_running = process_registry.is_running(ticket_number)
        orch_status = "running" if is_running else "waiting"
        agent_panels = [
            {
                "name": ORCHESTRATOR_AGENT.name,
                "display": ORCHESTRATOR_AGENT.display,
                "status": orch_status,
                "entries": [],
                "expanded": orch_status == "running",
            }
        ]

        for agent in CANONICAL_AGENTS:
            done_path = ticket_dir / f"{agent.file_basename}.done"
            conv_path = ticket_dir / "conversations" / f"{agent.file_basename}.json"

            if done_path.exists():
                status = "done"
            elif conv_path.exists():
                entries_raw = _load_json_array(conv_path)
                status = "running" if entries_raw else "waiting"
            else:
                entries_raw = []
                status = "waiting"

            entries = []
            if conv_path.exists():
                for entry in _load_json_array(conv_path):
                    entries.append({
                        "text": entry.get("content") or json.dumps(entry),
                        "timestamp": entry.get("timestamp", ""),
                    })

            agent_panels.append({
                "name": agent.name,
                "display": agent.display,
                "status": status,
                "entries": entries,
                "expanded": status == "running",
            })

        done_count = sum(1 for p in agent_panels if p["status"] == "done")

        worksite = _worksite_name(settings)
        sse_base = settings.pipeline_runner_url

        return templates.TemplateResponse(
            request,
            "viewer.html",
            {
                "ticket_number": ticket_number,
                "ticket_id": ticket_number,
                "ticket_title": issue_title,
                "worksite": worksite,
                "sse_base": sse_base,
                "agent_panels": agent_panels,
                "repo": settings.github_repo,
                "checkpoint_open": checkpoint_open,
                "checkpoint_body": checkpoint_body,
                "done_count": done_count,
                "total_agents": len(CANONICAL_AGENTS) + 1,
            },
        )

    @app.get("/tickets/{ticket_number}", response_class=HTMLResponse)
    async def tickets_viewer_page(request: Request, ticket_number: int) -> HTMLResponse:
        """New viewer page (Ticket #5 redesign). Injects __VIEWER_CTX__ for app.js."""
        issues, _ = await github.list_issues()
        issue_title = f"Ticket #{ticket_number}"
        for issue in issues:
            if issue.number == ticket_number:
                issue_title = issue.title
                break

        worksite = _worksite_name(settings)
        sse_base = settings.pipeline_runner_url

        return templates.TemplateResponse(
            request,
            "viewer.html",
            {
                "ticket_id": ticket_number,
                "ticket_title": issue_title,
                "worksite": worksite,
                "sse_base": sse_base,
                "repo": settings.github_repo,
            },
        )
