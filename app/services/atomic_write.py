from __future__ import annotations

import json
import os
from pathlib import Path


def atomic_write_text(path: Path, text: str) -> None:
    """Write text to a sibling temp file in the same directory, fsync, os.replace onto path."""
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        # fsync the file to ensure data is flushed
        with open(tmp, "r+b") as f:
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, obj: object, *, indent: int = 2) -> None:
    """json.dumps(obj, indent=indent, sort_keys=False, ensure_ascii=False) + trailing newline,
    then atomic_write_text."""
    text = json.dumps(obj, indent=indent, sort_keys=False, ensure_ascii=False) + "\n"
    atomic_write_text(path, text)
