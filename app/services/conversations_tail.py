from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator

import watchfiles

from app.services.agents import AGENT_NAMES, CANONICAL_AGENTS, SYSTEM_AGENT, agent_from_filename


@dataclass
class StreamEvent:
    agent: str
    text: str
    timestamp: str


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _load_json_array(path: Path) -> list[dict]:
    """Read a JSON file, tolerating single-object files and mid-write corruption."""
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return data
        return []
    except (json.JSONDecodeError, OSError):
        return []


def _entry_to_event(entry: dict, agent_name: str) -> StreamEvent:
    text = entry.get("content") or json.dumps(entry)
    timestamp = entry.get("timestamp") or _now_iso()
    return StreamEvent(agent=agent_name, text=text, timestamp=timestamp)


def _system_event(inner: dict) -> StreamEvent:
    return StreamEvent(
        agent=SYSTEM_AGENT,
        text=json.dumps(inner),
        timestamp=_now_iso(),
    )


async def tail(ticket_dir: Path) -> AsyncIterator[StreamEvent]:
    """Yield StreamEvents as they occur for one ticket.

    Emits backlog first (already-on-disk entries and system signals), then watches
    for new entries using watchfiles. Stops when the consumer cancels iteration."""
    conversations_dir = ticket_dir / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    entry_offsets: dict[str, int] = {name: 0 for name in AGENT_NAMES}
    emitted_done: set[str] = set()
    checkpoint_open_emitted = False
    checkpoint_closed_emitted = False

    for agent in CANONICAL_AGENTS:
        json_path = conversations_dir / f"{agent.file_basename}.json"
        if json_path.exists():
            entries = _load_json_array(json_path)
            for entry in entries:
                yield _entry_to_event(entry, agent.name)
            entry_offsets[agent.name] = len(entries)

        done_path = ticket_dir / f"{agent.file_basename}.done"
        if done_path.exists():
            yield _system_event({"event": "agent_done", "agent": agent.name})
            emitted_done.add(agent.name)

    waiting_path = ticket_dir / "waiting_for_human.md"
    response_path = ticket_dir / "human_response.md"

    if response_path.exists():
        checkpoint_closed_emitted = True
    elif waiting_path.exists():
        body = waiting_path.read_text(encoding="utf-8")
        yield _system_event({"event": "checkpoint_open", "body": body})
        checkpoint_open_emitted = True

    watch_paths = {str(ticket_dir), str(conversations_dir)}

    async for changes in watchfiles.awatch(*watch_paths, debounce=500):
        changed_paths = {Path(path) for _, path in changes}

        for agent in CANONICAL_AGENTS:
            json_path = conversations_dir / f"{agent.file_basename}.json"
            if json_path in changed_paths and json_path.exists():
                entries = _load_json_array(json_path)
                current_offset = entry_offsets.get(agent.name, 0)
                new_entries = entries[current_offset:]
                for entry in new_entries:
                    yield _entry_to_event(entry, agent.name)
                entry_offsets[agent.name] = len(entries)

        for agent in CANONICAL_AGENTS:
            done_path = ticket_dir / f"{agent.file_basename}.done"
            if agent.name not in emitted_done and done_path.exists():
                yield _system_event({"event": "agent_done", "agent": agent.name})
                emitted_done.add(agent.name)

        if not checkpoint_open_emitted and not checkpoint_closed_emitted:
            if waiting_path.exists():
                body = waiting_path.read_text(encoding="utf-8")
                yield _system_event({"event": "checkpoint_open", "body": body})
                checkpoint_open_emitted = True

        if checkpoint_open_emitted and not checkpoint_closed_emitted:
            if response_path.exists():
                yield _system_event({"event": "checkpoint_closed"})
                checkpoint_closed_emitted = True

        all_done = all(name in emitted_done for name in AGENT_NAMES)
        if all_done:
            yield _system_event({"event": "run_finished"})
            break
