"""
JSON API endpoints for the post-run review page.
Wired into the FastAPI app via register(app, settings).

Endpoints:
  GET /api/review/{ticket}               — summary JSON
  GET /api/review/{ticket}/trace/{agent} — raw trace events JSON array
  GET /api/review/{ticket}/diff          — commits + diffs JSON
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException

from app.config import Settings
from app.services.review import (
    GitUnavailable,
    build_bundle,
    list_trace_files,
    safe_agent_name,
    safe_ticket_id,
)

logger = logging.getLogger(__name__)


def register(app: FastAPI, settings: Settings) -> None:

    @app.get("/api/review/{ticket}")
    async def review_summary(ticket: str) -> dict:
        """AC34–AC37, AC41: Summary JSON for a completed ticket."""
        ticket_id = safe_ticket_id(ticket)
        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_id}"
        if not ticket_dir.is_dir():
            raise HTTPException(status_code=404, detail="ticket not found")

        workspace_root = settings.worksite_path / "workspace"
        repo_root = settings.worksite_path / "repo"
        bundle = build_bundle(workspace_root, repo_root, ticket_id)

        # Serialize exactly six top-level keys (AC34, addresses Tech Review F2).
        # Do NOT use dataclasses.asdict(bundle) — that would expose internal fields.
        return {
            "agents": [
                {
                    "name": a.name,
                    "cost": a.cost,
                    "turns": a.turns,
                    "duration_s": a.duration_s,
                    "model": a.model,
                }
                for a in bundle.agents
            ],
            "verdict": bundle.verdict,
            "total_cost": bundle.total_cost,
            "total_turns": bundle.total_turns,
            "duration_s": bundle.duration_s,
            "artifacts": bundle.artifacts,
        }

    @app.get("/api/review/{ticket}/trace/{agent}")
    async def review_trace(ticket: str, agent: str) -> list:
        """AC38, AC39: Raw trace events in original file order."""
        ticket_id = safe_ticket_id(ticket)
        agent_name = safe_agent_name(agent)

        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_id}"
        if not ticket_dir.is_dir():
            raise HTTPException(status_code=404, detail="ticket not found")

        trace_path = ticket_dir / "traces" / f"{agent_name}.jsonl"

        # Defence-in-depth: ensure resolved path stays inside ticket_dir
        try:
            trace_path.resolve().relative_to(ticket_dir.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="path traversal rejected")

        if not trace_path.exists():
            raise HTTPException(status_code=404, detail="trace not found")

        # Return events in original file order (not sorted by ts — AC38).
        # Skip malformed lines and lines without ts (consistent with page renderer).
        events: list = []
        for raw_line in trace_path.read_text(encoding="utf-8").splitlines():
            raw_line = raw_line.strip()
            if not raw_line:
                continue
            try:
                obj = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            if obj.get("ts") is None:
                continue
            events.append(obj)

        return events

    @app.get("/api/review/{ticket}/diff")
    async def review_diff(ticket: str) -> dict:
        """AC40, AC29: Commits + per-file diffs for a ticket."""
        ticket_id = safe_ticket_id(ticket)
        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_id}"
        if not ticket_dir.is_dir():
            raise HTTPException(status_code=404, detail="ticket not found")

        from app.services import git_diff as git_diff_mod

        repo_root = settings.worksite_path / "repo"
        try:
            commit_pairs = git_diff_mod.matching_commits(repo_root, ticket_id)
        except GitUnavailable as exc:
            logger.warning("git unavailable: %s", exc)
            raise HTTPException(status_code=500, detail="git_unavailable")

        commits: list = []
        for sha, message in commit_pairs:
            try:
                diff_text = git_diff_mod.diff_for_commit(repo_root, sha)
                files = git_diff_mod.split_per_file(diff_text)
            except GitUnavailable as exc:
                logger.warning("git unavailable for commit %s: %s", sha, exc)
                raise HTTPException(status_code=500, detail="git_unavailable")

            commits.append({
                "sha": sha,
                "message": message,
                "files": [
                    {
                        "path": f.path,
                        "diff": f.diff,
                        "additions": f.additions,
                        "deletions": f.deletions,
                    }
                    for f in files
                ],
            })

        return {"commits": commits}
