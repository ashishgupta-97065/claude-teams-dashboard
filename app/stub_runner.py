"""Standalone stub runner: python -m app.stub_runner <N>

Simulates the pipeline by writing fake conversation entries and done markers,
including the human-checkpoint flow between Designer and Architect.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from app.services.agents import CANONICAL_AGENTS


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _append_entry(json_path: Path, content: str) -> None:
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                data = [data]
        except (json.JSONDecodeError, OSError):
            data = []
    else:
        data = []

    data.append({"role": "agent", "timestamp": _now_iso(), "content": content})
    json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _touch(path: Path) -> None:
    path.touch()


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python -m app.stub_runner <N>", file=sys.stderr)
        return 2

    worksite_raw = os.environ.get("WORKSITE_PATH")
    if not worksite_raw:
        print("WORKSITE_PATH environment variable is required", file=sys.stderr)
        return 2

    try:
        ticket_n = int(sys.argv[1])
    except ValueError:
        print(f"Invalid ticket number: {sys.argv[1]!r}", file=sys.stderr)
        return 2

    ticket_dir = Path(worksite_raw) / "workspace" / f"ticket_{ticket_n}"
    conversations_dir = ticket_dir / "conversations"
    conversations_dir.mkdir(parents=True, exist_ok=True)

    fake_outputs: dict[str, list[str]] = {
        "pm": [
            "Analyzed the requirements for the pipeline dashboard.",
            "Drafted the specification with 29 acceptance criteria.",
            "Confirmed scope with stakeholders — stub runner is sufficient for AC10.",
        ],
        "designer": [
            "Designed the two-page layout: ticket list and live viewer.",
            "Defined the design system: CSS variables, status pills, agent panels.",
        ],
        "architect": [
            "Defined the file structure and module interfaces.",
            "Confirmed watchfiles+SSE approach meets AC13 latency budget.",
            "Documented the canonical agent list to prevent divergence.",
        ],
        "developer": [
            "Implemented all source files for the pipeline dashboard.",
            "Wrote app.js with smart auto-scroll and +N badge logic.",
            "Verified all 29 ACs are covered by the implementation.",
        ],
        "qa": [
            "Ran Playwright smoke tests at 375px viewport.",
            "Verified SSE stream delivers events within 2s.",
            "All 29 acceptance criteria pass.",
        ],
        "tech-lead": [
            "Reviewed the implementation against architecture.md.",
            "Approved — all directed actions from tech_review.md are addressed.",
        ],
    }

    waiting_path = ticket_dir / "waiting_for_human.md"
    response_path = ticket_dir / "human_response.md"

    for agent in CANONICAL_AGENTS:
        json_path = conversations_dir / f"{agent.file_basename}.json"
        entries = fake_outputs.get(agent.name, [f"Agent {agent.display} completed work."])

        for i, content in enumerate(entries):
            _append_entry(json_path, content)
            if i < len(entries) - 1:
                time.sleep(1.0)

        if agent.name == "designer":
            waiting_path.write_text(
                "Please review the design and approve or request changes.\n\n"
                "The designer has proposed a two-page layout with:\n"
                "- Ticket list with status pills and Run buttons\n"
                "- Live viewer with six agent panels and SSE streaming\n"
                "- Human checkpoint panel with APPROVED / CHANGES form",
                encoding="utf-8",
            )

            while not response_path.exists():
                time.sleep(0.5)

            _append_entry(
                json_path,
                f"Acknowledged human response. Proceeding to Architect phase.",
            )

        _touch(ticket_dir / f"{agent.file_basename}.done")
        time.sleep(0.5)

    return 0


if __name__ == "__main__":
    sys.exit(main())
