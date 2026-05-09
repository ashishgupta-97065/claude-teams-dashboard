from __future__ import annotations

import json
from pathlib import Path

from app.services.atomic_write import atomic_write_json


class QueueParseError(Exception):
    """Raised when queue.json exists but is malformed."""


def load_queue(queue_path: Path) -> list[int]:
    """Return the list of ticket numbers. Returns [] if the file does not exist.
    Raises QueueParseError if the file exists but is malformed (not valid JSON,
    no `tickets` key, or `tickets` is not a list of ints)."""
    if not queue_path.exists():
        return []

    try:
        text = queue_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise QueueParseError(f"Invalid JSON in {queue_path}: {exc}") from exc

    if not isinstance(data, dict) or "tickets" not in data:
        raise QueueParseError(f"queue.json at {queue_path} is missing the 'tickets' key")

    tickets = data["tickets"]
    if not isinstance(tickets, list):
        raise QueueParseError(f"'tickets' in {queue_path} is not a list")

    for item in tickets:
        if not isinstance(item, int):
            raise QueueParseError(f"'tickets' contains non-integer value: {item!r}")

    return tickets


def save_queue(queue_path: Path, tickets: list[int]) -> list[int]:
    """Validate every element is int > 0 (raises ValueError on bad input).
    Atomic-write {"tickets": [...]} as JSON with indent=2 and a trailing newline.
    Returns the written list."""
    for ticket in tickets:
        if not isinstance(ticket, int) or ticket <= 0:
            raise ValueError(f"Ticket values must be positive integers, got {ticket!r}")

    atomic_write_json(queue_path, {"tickets": tickets})
    return tickets
