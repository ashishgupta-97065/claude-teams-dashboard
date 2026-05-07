from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AgentSpec:
    name: str
    display: str
    file_basename: str


CANONICAL_AGENTS: list[AgentSpec] = [
    AgentSpec(name="pm", display="PM", file_basename="pm"),
    AgentSpec(name="designer", display="Designer", file_basename="designer"),
    AgentSpec(name="architect", display="Architect", file_basename="architect"),
    AgentSpec(name="developer", display="Developer", file_basename="developer"),
    AgentSpec(name="qa", display="QA", file_basename="qa"),
    AgentSpec(name="tech-lead", display="Tech Lead", file_basename="tech-lead"),
]

# Orchestrator is not file-based — tracked via process_registry + SSE proxy from pipeline runner
ORCHESTRATOR_AGENT = AgentSpec(name="orchestrator", display="Orchestrator", file_basename="")

AGENT_NAMES: list[str] = [a.name for a in CANONICAL_AGENTS]

SYSTEM_AGENT: str = "_system"

_AGENT_BY_BASENAME: dict[str, str] = {a.file_basename: a.name for a in CANONICAL_AGENTS}


def agent_from_filename(path: Path) -> str | None:
    """Return the SSE `agent` field for a conversations file path, or None if the
    filename does not match a canonical agent. Mapping: strip `.json`, lowercase."""
    stem = path.stem.lower()
    return _AGENT_BY_BASENAME.get(stem)
