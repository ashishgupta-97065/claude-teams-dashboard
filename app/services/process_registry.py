from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class RunningProcess:
    ticket_number: int
    popen: subprocess.Popen
    started_at: datetime


_registry: dict[int, RunningProcess] = {}
_lock = threading.Lock()


def start(ticket_number: int, command: list[str], cwd: Path) -> bool:
    """Spawn the subprocess if not already running for this ticket.
    Returns True if a new process was spawned, False if one was already running.
    Thread-safe."""
    with _lock:
        existing = _registry.get(ticket_number)
        if existing is not None and existing.popen.poll() is None:
            return False

        proc = subprocess.Popen(
            command,
            cwd=str(cwd),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _registry[ticket_number] = RunningProcess(
            ticket_number=ticket_number,
            popen=proc,
            started_at=datetime.utcnow(),
        )
        return True


def is_running(ticket_number: int) -> bool:
    """Return True iff a process for this ticket is registered AND still alive
    (calls Popen.poll() — does not block). Lazily reaps finished entries."""
    with _lock:
        entry = _registry.get(ticket_number)
        if entry is None:
            return False
        if entry.popen.poll() is not None:
            del _registry[ticket_number]
            return False
        return True


def reap_finished() -> list[int]:
    """Remove finished processes from the registry. Returns the ticket numbers reaped.
    Called from is_running() and from a periodic asyncio task started by main.py's
    lifespan handler (every 5 seconds)."""
    reaped: list[int] = []
    with _lock:
        finished = [n for n, rp in _registry.items() if rp.popen.poll() is not None]
        for n in finished:
            del _registry[n]
            reaped.append(n)
    return reaped
