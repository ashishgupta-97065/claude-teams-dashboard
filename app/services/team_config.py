from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.services.atomic_write import atomic_write_json

ALLOWED_HUMAN_MODES: tuple[str, ...] = (
    "active_discussion",
    "task_confirmation_only",
    "no_human",
)


class ConfigNotFoundError(Exception):
    """Raised when team.config.json does not exist."""


class ConfigParseError(Exception):
    """Raised when team.config.json is not valid JSON or not a top-level object."""


def load_config(config_path: Path) -> dict[str, Any]:
    """Read and parse team.config.json. Raises ConfigNotFoundError if missing,
    ConfigParseError if not valid JSON or not a top-level object."""
    if not config_path.exists():
        raise ConfigNotFoundError(f"Config file not found: {config_path}")

    try:
        text = config_path.read_text(encoding="utf-8")
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigParseError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigParseError(f"Config file {config_path} is not a JSON object")

    return data


def save_config_partial(
    config_path: Path,
    *,
    loop_cap: int,
    human_mode: str,
    agents: list[str],
) -> dict[str, Any]:
    """Read existing config, replace ONLY the three editable keys, atomic-write
    back. Returns the merged dict. Preserves order and values of all other
    top-level keys. Validates loop_cap >= 1 and human_mode in ALLOWED_HUMAN_MODES
    (Pydantic in the route is the primary gate; this is defense-in-depth)."""
    if loop_cap < 1:
        raise ValueError(f"loop_cap must be >= 1, got {loop_cap}")
    if human_mode not in ALLOWED_HUMAN_MODES:
        raise ValueError(f"human_mode {human_mode!r} is not in {ALLOWED_HUMAN_MODES}")

    existing = load_config(config_path)  # raises ConfigNotFoundError / ConfigParseError

    # Merge: overwrite only the three editable keys, preserve everything else
    existing["loop_cap"] = loop_cap
    existing["human_mode"] = human_mode
    existing["agents"] = agents

    atomic_write_json(config_path, existing)
    return existing
