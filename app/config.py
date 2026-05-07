from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    worksite_path: Path
    github_repo: str
    github_token: str | None
    pipeline_runner_url: str = "http://localhost:8090"
    port: int = 8080
    bind_host: str = "127.0.0.1"


def load_settings() -> Settings:
    """Read env vars; raise RuntimeError if WORKSITE_PATH or GITHUB_REPO missing or
    if WORKSITE_PATH does not exist as a directory. Called once from main.py."""
    worksite_raw = os.environ.get("WORKSITE_PATH")
    if not worksite_raw:
        raise RuntimeError("WORKSITE_PATH environment variable is required but not set")

    worksite_path = Path(worksite_raw)
    if not worksite_path.is_dir():
        raise RuntimeError(
            f"WORKSITE_PATH={worksite_raw!r} does not exist or is not a directory"
        )

    github_repo = os.environ.get("GITHUB_REPO")
    if not github_repo:
        raise RuntimeError("GITHUB_REPO environment variable is required but not set")

    github_token = os.environ.get("GITHUB_TOKEN") or None

    bind_host = os.environ.get("DASHBOARD_BIND_HOST", "127.0.0.1")
    port_raw = os.environ.get("DASHBOARD_PORT", "8080")
    try:
        port = int(port_raw)
    except ValueError:
        raise RuntimeError(f"DASHBOARD_PORT={port_raw!r} is not a valid integer")

    pipeline_runner_url = os.environ.get("PIPELINE_RUNNER_URL", "http://localhost:8090")

    return Settings(
        worksite_path=worksite_path,
        github_repo=github_repo,
        github_token=github_token,
        pipeline_runner_url=pipeline_runner_url,
        port=port,
        bind_host=bind_host,
    )
