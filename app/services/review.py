"""
Review service: aggregates trace data, artifacts, and git commits for a completed ticket.
Pure functions on filesystem inputs — no FastAPI imports except HTTPException for validators.
"""
from __future__ import annotations

import datetime
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException


class GitUnavailable(RuntimeError):
    """Raised when git is not available or returns a non-zero exit code."""


@dataclass(frozen=True)
class AgentRollup:
    name: str           # trace file stem, e.g. "developer-rework-1"
    cost: float         # USD, sum of ResultMessage.data.total_cost_usd
    turns: int          # sum of ResultMessage.data.num_turns
    duration_s: float   # last_ts - first_ts in that file
    model: str | None   # first non-null data.model seen, else None
    first_ts: float     # epoch seconds, for global min/max
    last_ts: float


@dataclass(frozen=True)
class TraceEvent:
    kind: str           # "AssistantMessage" | "UserMessage" | "ToolUseBlock" | "ToolResultBlock" | "RateLimitEvent"
    ts: float
    payload: dict       # original parsed JSON of that line


@dataclass(frozen=True)
class FileDiff:
    path: str
    diff: str           # raw per-file diff text including hunk headers
    additions: int      # count of "+" lines (excluding "+++")
    deletions: int      # count of "-" lines (excluding "---")


@dataclass(frozen=True)
class CommitEntry:
    sha: str            # 7-char short SHA
    message: str
    files: list         # list[FileDiff]


@dataclass(frozen=True)
class ReviewBundle:
    ticket_id: int
    title: str
    date: str           # YYYY-MM-DD, mtime of ticket_dir
    total_cost: float
    total_turns: int
    duration_s: float
    verdict: str        # "PASS" | "FAIL" | "BLOCKED" | "unknown"
    agents: list        # list[AgentRollup]
    artifacts: dict     # keys: specs, design, architecture, tech_review, qa_report
    artifacts_html: dict  # rendered HTML, None when source is None
    commits: list       # list[CommitEntry]


def format_duration(seconds: float) -> str:
    """Single shared duration formatter (AC8).

    Rules (locked by architecture §4.1 / §5.12):
      total = max(0, round(seconds))
      h = total // 3600;  m = (total % 3600) // 60;  s = total % 60
      If h > 0: "{h}h {m}m {s}s"   (always all three)
      Elif m > 0: "{m}m {s}s"
      Else: "{s}s"
    No leading zeros on any component.
    """
    total = max(0, round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    if h > 0:
        return f"{h}h {m}m {s}s"
    elif m > 0:
        return f"{m}m {s}s"
    else:
        return f"{s}s"


def safe_ticket_id(raw: str) -> int:
    """Validate raw string is a pure digit sequence; raise HTTPException(404) otherwise."""
    if not re.match(r"^\d+$", raw):
        raise HTTPException(status_code=404)
    return int(raw)


def safe_agent_name(raw: str) -> str:
    """Validate raw string matches ^[A-Za-z0-9_\\-]+$; raise HTTPException(404) otherwise."""
    if not re.match(r"^[A-Za-z0-9_\-]+$", raw):
        raise HTTPException(status_code=404)
    return raw


def list_trace_files(ticket_dir: Path) -> list:
    """Sorted list of traces/*.jsonl. Sort: stable lexicographic on stem."""
    traces_dir = ticket_dir / "traces"
    if not traces_dir.is_dir():
        return []
    return sorted(traces_dir.glob("*.jsonl"), key=lambda p: p.stem)


def parse_trace_file(path: Path) -> tuple:
    """Single-pass file read. Returns (AgentRollup, list[TraceEvent]).
    Events are sorted by ts. Malformed lines and lines missing ts are skipped.
    """
    cost = 0.0
    turns = 0
    model: str | None = None
    first_ts: float | None = None
    last_ts: float | None = None
    events: list = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        ts_raw = obj.get("ts")
        if ts_raw is None:
            continue
        try:
            ts = float(ts_raw)
        except (TypeError, ValueError):
            continue

        kind = obj.get("kind", "")
        data = obj.get("data") or {}

        if kind == "ResultMessage":
            cost += float(data.get("total_cost_usd") or 0)
            turns += int(data.get("num_turns") or 0)
            if model is None and data.get("model"):
                model = data["model"]

        if first_ts is None or ts < first_ts:
            first_ts = ts
        if last_ts is None or ts > last_ts:
            last_ts = ts

        events.append(TraceEvent(kind=kind, ts=ts, payload=obj))

    if first_ts is None:
        first_ts = 0.0
        last_ts = 0.0

    events.sort(key=lambda e: e.ts)

    duration_s = (last_ts - first_ts) if last_ts is not None else 0.0

    return AgentRollup(
        name=path.stem,
        cost=cost,
        turns=turns,
        duration_s=duration_s,
        model=model,
        first_ts=first_ts,
        last_ts=last_ts if last_ts is not None else 0.0,
    ), events


def aggregate_totals(rollups: list) -> tuple:
    """Returns (total_cost, total_turns, duration_s).
    Duration uses global min(first_ts) and max(last_ts) across all rollups.
    """
    if not rollups:
        return 0.0, 0, 0.0
    total_cost = sum(r.cost for r in rollups)
    total_turns = sum(r.turns for r in rollups)
    global_first = min(r.first_ts for r in rollups)
    global_last = max(r.last_ts for r in rollups)
    return total_cost, total_turns, global_last - global_first


def _count_string_chars(obj: object) -> int:
    """Recursively count total characters of all string values in obj."""
    if isinstance(obj, str):
        return len(obj)
    if isinstance(obj, dict):
        return sum(_count_string_chars(v) for v in obj.values())
    if isinstance(obj, list):
        return sum(_count_string_chars(item) for item in obj)
    return 0


def estimate_tokens(events: list) -> int:
    """ceil(total_chars / 4) over AssistantMessage, UserMessage, ToolUseBlock, ToolResultBlock string content."""
    counted_kinds = {"AssistantMessage", "UserMessage", "ToolUseBlock", "ToolResultBlock"}
    total_chars = sum(
        _count_string_chars(e.payload)
        for e in events
        if e.kind in counted_kinds
    )
    return math.ceil(total_chars / 4)


def parse_verdict(qa_report_text: str | None) -> str:
    """Returns "PASS" | "FAIL" | "BLOCKED" | "unknown".
    Case-insensitive search for first PASS|FAIL|BLOCKED on a line containing "verdict".
    """
    if not qa_report_text:
        return "unknown"
    for line in qa_report_text.splitlines():
        if re.search(r"verdict", line, re.IGNORECASE):
            m = re.search(r"\b(PASS|FAIL|BLOCKED)\b", line, re.IGNORECASE)
            if m:
                return m.group(1).upper()
    return "unknown"


def parse_title(specs_text: str | None, ticket_id: int) -> str:
    """First H1 of specs.md, else f"Ticket #{ticket_id}"."""
    if not specs_text:
        return f"Ticket #{ticket_id}"
    for line in specs_text.splitlines():
        m = re.match(r"^#\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return f"Ticket #{ticket_id}"


def load_artifacts(ticket_dir: Path) -> dict:
    """Keys: specs, design, architecture, tech_review, qa_report. Value: file text or None."""
    mapping = {
        "specs": "specs.md",
        "design": "design.md",
        "architecture": "architecture.md",
        "tech_review": "tech_review.md",
        "qa_report": "qa_report.md",
    }
    result = {}
    for key, filename in mapping.items():
        fp = ticket_dir / filename
        try:
            result[key] = fp.read_text(encoding="utf-8")
        except OSError:
            result[key] = None
    return result


def render_artifacts_html(artifacts: dict) -> dict:
    """Calls services.markdown.render on each non-None value."""
    from app.services.markdown import render as md_render
    return {
        key: md_render(text) if text is not None else None
        for key, text in artifacts.items()
    }


def build_bundle(workspace_root: Path, repo_root: Path, ticket_id: int) -> ReviewBundle:
    """Top-level orchestrator. Raises FileNotFoundError if ticket_dir missing."""
    ticket_dir = workspace_root / f"ticket_{ticket_id}"
    if not ticket_dir.is_dir():
        raise FileNotFoundError(f"Ticket directory not found: {ticket_dir}")

    trace_paths = list_trace_files(ticket_dir)
    rollups = []
    for path in trace_paths:
        rollup, _ = parse_trace_file(path)
        rollups.append(rollup)

    total_cost, total_turns, duration_s = aggregate_totals(rollups)
    artifacts = load_artifacts(ticket_dir)
    artifacts_html = render_artifacts_html(artifacts)
    verdict = parse_verdict(artifacts.get("qa_report"))
    title = parse_title(artifacts.get("specs"), ticket_id)

    mtime = ticket_dir.stat().st_mtime
    date = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")

    from app.services import git_diff as git_diff_mod
    commits: list = []
    try:
        commit_pairs = git_diff_mod.matching_commits(repo_root, ticket_id)
        for sha, message in commit_pairs:
            diff_text = git_diff_mod.diff_for_commit(repo_root, sha)
            files = git_diff_mod.split_per_file(diff_text)
            commits.append(CommitEntry(sha=sha, message=message, files=files))
    except GitUnavailable:
        pass

    return ReviewBundle(
        ticket_id=ticket_id,
        title=title,
        date=date,
        total_cost=total_cost,
        total_turns=total_turns,
        duration_s=duration_s,
        verdict=verdict,
        agents=rollups,
        artifacts=artifacts,
        artifacts_html=artifacts_html,
        commits=commits,
    )
