from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter

from app.services.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)

ALLOWED_MODELS: tuple[str, ...] = (
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-20251001",
)


class AgentNotFoundError(Exception):
    """Raised when an ag_<name>.md file does not exist."""


class FrontmatterParseError(Exception):
    """Raised when a file cannot be parsed as frontmatter."""


class InvalidModelError(Exception):
    """Raised when a model value is not in ALLOWED_MODELS."""


@dataclass(frozen=True)
class AgentRecord:
    name: str               # "ag_pm" — filename without .md
    model: str
    tools: list[str]
    permission_mode: str | None
    path: Path
    system_prompt: str      # the body after the closing ---


def _parse_agent_file(path: Path) -> AgentRecord:
    """Parse an ag_*.md file into an AgentRecord. Raises FrontmatterParseError on failure."""
    try:
        post = frontmatter.load(str(path))
    except Exception as exc:
        raise FrontmatterParseError(f"Failed to parse {path}: {exc}") from exc

    metadata = post.metadata
    name = path.stem  # filename without .md
    model = metadata.get("model", "")
    tools_raw = metadata.get("tools", [])
    if isinstance(tools_raw, list):
        tools = [str(t) for t in tools_raw]
    else:
        tools = []
    permission_mode = metadata.get("permissionMode", None)
    if permission_mode is not None:
        permission_mode = str(permission_mode)
    system_prompt = post.content

    return AgentRecord(
        name=name,
        model=model,
        tools=tools,
        permission_mode=permission_mode,
        path=path.resolve(),
        system_prompt=system_prompt,
    )


def list_agents(agents_dir: Path) -> list[AgentRecord]:
    """Glob ag_*.md, parse each, return sorted by name. Skips files that fail
    to parse with a logged warning (does not raise)."""
    records: list[AgentRecord] = []
    for path in sorted(agents_dir.glob("ag_*.md")):
        try:
            rec = _parse_agent_file(path)
            records.append(rec)
        except FrontmatterParseError as exc:
            logger.warning("Skipping malformed agent file %s: %s", path, exc)
        except Exception as exc:
            logger.warning("Unexpected error parsing agent file %s: %s", path, exc)
    return sorted(records, key=lambda r: r.name)


def load_agent(agents_dir: Path, name: str) -> AgentRecord:
    """Load one agent by name. Raises AgentNotFoundError if the file is absent.
    Raises FrontmatterParseError if the file exists but cannot be parsed."""
    path = agents_dir / f"{name}.md"
    if not path.exists():
        raise AgentNotFoundError(f"Agent file not found: {path}")
    return _parse_agent_file(path)


def patch_agent_model(agents_dir: Path, name: str, new_model: str) -> AgentRecord:
    """Validate new_model is in ALLOWED_MODELS (else InvalidModelError).
    Read the file as text. Find the frontmatter block (between leading and next ---).
    Replace ONLY the line that starts with `model:` (allowing leading whitespace)
    with `model: <new_model>` preserving original indentation. Atomic-write the
    full file. Re-parse and return the updated AgentRecord. Body bytes after the
    closing --- are not touched."""
    if new_model not in ALLOWED_MODELS:
        raise InvalidModelError(f"Model {new_model!r} is not in ALLOWED_MODELS: {ALLOWED_MODELS}")

    path = agents_dir / f"{name}.md"
    if not path.exists():
        raise AgentNotFoundError(f"Agent file not found: {path}")

    original_text = path.read_text(encoding="utf-8")

    # Find the frontmatter block: starts at the leading "---\n" and ends at the next "---"
    # The frontmatter is between the first "---" and the second "---"
    # We only modify lines in the frontmatter block.
    lines = original_text.split("\n")

    # Find the frontmatter delimiters
    if not lines or lines[0].rstrip() != "---":
        raise FrontmatterParseError(f"File {path} does not start with '---'")

    # Find closing ---
    closing_idx = None
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            closing_idx = i
            break

    if closing_idx is None:
        raise FrontmatterParseError(f"File {path} has no closing '---' for frontmatter")

    # Replace ONLY the model: line in frontmatter, preserving indentation
    model_pattern = re.compile(r'^(\s*)model:\s*.+$')
    new_lines = lines[:]
    replaced = False
    for i in range(1, closing_idx):
        m = model_pattern.match(lines[i])
        if m:
            indent = m.group(1)
            new_lines[i] = f"{indent}model: {new_model}"
            replaced = True
            break

    if not replaced:
        raise FrontmatterParseError(f"No 'model:' line found in frontmatter of {path}")

    new_text = "\n".join(new_lines)
    atomic_write_text(path, new_text)

    return _parse_agent_file(path)


def to_api_dict(rec: AgentRecord) -> dict:
    """JSON-serializable dict matching the GET /api/agents element shape.
    Note key name: API uses `permissionMode` (camelCase, matches frontmatter)."""
    return {
        "name": rec.name,
        "model": rec.model,
        "tools": rec.tools,
        "permissionMode": rec.permission_mode,
        "path": str(rec.path),
        "system_prompt": rec.system_prompt,
    }
