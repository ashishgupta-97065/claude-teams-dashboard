"""Filesystem service for workspace artifact reads.

Provides two public functions consumed by app/routes/workspace.py:
  - list_tree(ticket_id) -> (entries, truncated)
  - read_file(ticket_id, relative_path) -> FilePayload

WORKSPACE_ROOT is a module-level variable set at app startup by create_app()
so that tests can monkeypatch it with a tmp_path worksite.
"""
from __future__ import annotations

import os
import stat as _stat
from dataclasses import dataclass
from pathlib import Path

MAX_FILE_BYTES = 1_048_576  # 1 MB
MAX_TREE_ENTRIES = 5000

# Overridden by create_app() and by test monkeypatching
WORKSPACE_ROOT: Path = Path("workspace")


@dataclass(frozen=True)
class TreeEntry:
    path: str       # POSIX, relative to ticket workspace root
    size: int       # 0 for directories
    modified: float # unix epoch seconds
    is_dir: bool


@dataclass(frozen=True)
class FilePayload:
    content: bytes       # length <= MAX_FILE_BYTES
    truncated: bool
    original_size: int   # full file size on disk
    content_type: str


def ticket_root(ticket_id: int) -> Path:
    """Return WORKSPACE_ROOT / f'ticket_{ticket_id}'. Does NOT verify existence."""
    return WORKSPACE_ROOT / f"ticket_{ticket_id}"


def list_tree(ticket_id: int) -> tuple[list[TreeEntry], bool]:
    """Walk the ticket workspace recursively.

    Returns (entries, truncated). Raises FileNotFoundError if workspace missing.
    Symlinks are not followed. Hidden files and .done markers are included.
    Walk is bounded by MAX_TREE_ENTRIES.
    """
    root = ticket_root(ticket_id)
    if not root.is_dir():
        raise FileNotFoundError(f"Workspace directory not found: {root}")

    # Collect up to MAX_TREE_ENTRIES + 1 entries so we can detect truncation
    entries: list[TreeEntry] = []
    _collect(root, root, entries, MAX_TREE_ENTRIES + 1)

    if len(entries) > MAX_TREE_ENTRIES:
        return entries[:MAX_TREE_ENTRIES], True
    return entries, False


def _collect(directory: Path, root: Path, entries: list[TreeEntry], limit: int) -> None:
    """Recursively collect TreeEntry objects, stopping once limit is reached."""
    try:
        children = sorted(directory.iterdir())
    except (PermissionError, OSError):
        return

    for child in children:
        if len(entries) >= limit:
            return

        try:
            st = child.stat(follow_symlinks=False)
        except OSError:
            continue

        is_dir = _stat.S_ISDIR(st.st_mode)
        rel = child.relative_to(root)
        path_str = rel.as_posix()
        size = 0 if is_dir else st.st_size
        modified = st.st_mtime

        entries.append(TreeEntry(path=path_str, size=size, modified=modified, is_dir=is_dir))

        if len(entries) >= limit:
            return

        if is_dir:
            _collect(child, root, entries, limit)


def read_file(ticket_id: int, relative_path: str) -> FilePayload:
    """Resolve and read a file from the ticket workspace, capped at MAX_FILE_BYTES.

    Raises:
      ValueError        on empty/invalid path            -> route maps to 400
      PermissionError   on traversal escape              -> route maps to 403
      FileNotFoundError on missing workspace or file     -> route maps to 404
      IsADirectoryError on directory target              -> route maps to 400
    """
    if not relative_path or not relative_path.strip():
        raise ValueError("relative_path must not be empty")

    # Defence in depth: reject absolute paths and any .. segments before resolve()
    rp = Path(relative_path)
    if rp.is_absolute() or relative_path.startswith("/"):
        raise PermissionError("path escapes workspace root")

    # Split on both forward and back slashes to catch Windows-style traversal
    parts = relative_path.replace("\\", "/").split("/")
    if ".." in parts:
        raise PermissionError("path escapes workspace root")

    root = ticket_root(ticket_id)
    if not root.is_dir():
        raise FileNotFoundError(f"Workspace directory not found: {root}")

    try:
        resolved_root = root.resolve(strict=True)
    except OSError:
        raise FileNotFoundError(f"Workspace directory not found: {root}")

    candidate = root / relative_path
    try:
        resolved_candidate = candidate.resolve(strict=True)
    except OSError:
        raise FileNotFoundError(f"File not found: {relative_path}")

    if not resolved_candidate.is_relative_to(resolved_root):
        raise PermissionError("path escapes workspace root")

    if resolved_candidate.is_dir():
        raise IsADirectoryError(f"path is a directory: {relative_path}")

    st = resolved_candidate.stat()
    original_size = st.st_size
    truncated = original_size > MAX_FILE_BYTES

    with open(resolved_candidate, "rb") as fh:
        content = fh.read(MAX_FILE_BYTES)

    content_type = _content_type_for(resolved_candidate)

    return FilePayload(
        content=content,
        truncated=truncated,
        original_size=original_size,
        content_type=content_type,
    )


def _content_type_for(path: Path) -> str:
    """Map file extension to Content-Type per spec §3.2."""
    ext = path.suffix.lower()
    if ext == ".md":
        return "text/markdown; charset=utf-8"
    if ext == ".py":
        return "text/x-python; charset=utf-8"
    if ext == ".json":
        return "application/json; charset=utf-8"
    return "text/plain; charset=utf-8"
