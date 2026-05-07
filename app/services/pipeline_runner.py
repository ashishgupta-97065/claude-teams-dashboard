from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.config import Settings


def build_command(ticket_number: int, settings: Settings) -> tuple[list[str], Path]:
    """Return (argv, cwd) for a subprocess that triggers 900_pipeline_runner via HTTP
    and blocks until the run reaches a terminal state."""
    worksite = settings.worksite_path.parent.name
    base_url = settings.pipeline_runner_url

    script = f"""
import json, sys, time, urllib.request, urllib.error

base = {base_url!r}
worksite = {worksite!r}
ticket = {ticket_number}
key = f"{{worksite}}/{{ticket}}"

# Trigger the run (idempotent — 200 or 409 both mean it's running)
try:
    urllib.request.urlopen(
        urllib.request.Request(
            f"{{base}}/run/{{worksite}}/{{ticket}}",
            data=b"",
            method="POST",
        ),
        timeout=15,
    )
except urllib.error.HTTPError as e:
    if e.code not in (200, 202, 409):
        print(f"Failed to start run: HTTP {{e.code}}", file=sys.stderr)
        sys.exit(1)
except Exception as e:
    print(f"Failed to reach pipeline runner: {{e}}", file=sys.stderr)
    sys.exit(1)

# Poll /runs until terminal state
while True:
    try:
        resp = urllib.request.urlopen(f"{{base}}/runs", timeout=10).read()
        runs = json.loads(resp)
        run = next((r for r in runs if r["key"] == key), None)
        if run is not None and run.get("status") not in ("running", None):
            break
    except Exception:
        pass
    time.sleep(5)
"""
    argv = [sys.executable, "-c", script]
    return argv, settings.worksite_path
