from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncIterator

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.services.conversations_tail import tail


async def _make_stream(ticket_dir: Path, settings: Settings, ticket_number: int) -> AsyncIterator[str]:
    """Generate SSE data lines, merging file-tail events with orchestrator proxy events."""
    heartbeat_interval = 0.5
    pending: list[str] = []
    finished = False

    async def collect_file_tail() -> None:
        nonlocal finished
        try:
            async for event in tail(ticket_dir):
                data = json.dumps({
                    "agent": event.agent,
                    "text": event.text,
                    "timestamp": event.timestamp,
                })
                pending.append(f"data: {data}\n\n")
                if event.agent == "_system":
                    inner = json.loads(event.text)
                    if inner.get("event") == "run_finished":
                        break
        except asyncio.CancelledError:
            pass
        finally:
            finished = True

    async def collect_orchestrator() -> None:
        """Proxy agent=orchestrator events from 900_pipeline_runner SSE stream."""
        worksite = settings.worksite_path.parent.name
        url = f"{settings.pipeline_runner_url}/stream/{worksite}/{ticket_number}"
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("GET", url) as resp:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            continue
                        if event.get("agent") != "orchestrator":
                            continue
                        data = json.dumps({
                            "agent": "orchestrator",
                            "text": event.get("text", ""),
                            "timestamp": event.get("ts", ""),
                        })
                        pending.append(f"data: {data}\n\n")
        except (httpx.HTTPError, asyncio.CancelledError, Exception):
            pass

    tail_task = asyncio.create_task(collect_file_tail())
    orch_task = asyncio.create_task(collect_orchestrator())

    try:
        while not finished or pending:
            if pending:
                yield pending.pop(0)
                continue
            done, _ = await asyncio.wait([tail_task], timeout=heartbeat_interval)
            if pending:
                continue
            if not finished:
                yield ": keepalive\n\n"
    finally:
        for task in (tail_task, orch_task):
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


def register(app: FastAPI, settings: Settings) -> None:

    @app.get("/stream/{ticket_number}")
    async def stream_events(ticket_number: int) -> StreamingResponse:
        ticket_dir = settings.worksite_path / "workspace" / f"ticket_{ticket_number}"
        ticket_dir.mkdir(parents=True, exist_ok=True)

        return StreamingResponse(
            _make_stream(ticket_dir, settings, ticket_number),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )
