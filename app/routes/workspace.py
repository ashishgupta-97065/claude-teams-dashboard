"""Read-only workspace filesystem endpoints.

GET /api/workspace/{ticket}/files  — recursive tree listing
GET /api/workspace/{ticket}/file   — raw file content (path=... query param)

Path-traversal hardened via workspace_fs.read_file() which raises PermissionError
for any path that escapes the ticket workspace root.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Response

from app.services import workspace_fs

router = APIRouter(prefix="/api/workspace", tags=["workspace"])


@router.get("/{ticket}/files")
def list_files(ticket: int) -> dict:
    """Return recursive tree listing of the ticket workspace.

    200 — {root, entries, truncated}
    404 — workspace directory does not exist
    """
    try:
        entries, truncated = workspace_fs.list_tree(ticket)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="workspace not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "root": f"workspace/ticket_{ticket}",
        "entries": [
            {
                "path": e.path,
                "size": e.size,
                "modified": e.modified,
                "is_dir": e.is_dir,
            }
            for e in entries
        ],
        "truncated": truncated,
    }


@router.get("/{ticket}/file")
def get_file(ticket: int, path: str = Query(..., min_length=1)) -> Response:
    """Stream a single workspace file (capped at 1 MB).

    200 — raw file bytes with Content-Type and optional X-Truncated / X-Original-Size headers
    400 — empty path or path is a directory
    403 — path traversal escape attempt
    404 — file or workspace does not exist
    """
    try:
        payload = workspace_fs.read_file(ticket, path)
    except ValueError:
        raise HTTPException(status_code=400, detail="path query parameter required")
    except PermissionError:
        raise HTTPException(status_code=403, detail="path escapes workspace root")
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="file not found")
    except IsADirectoryError:
        raise HTTPException(status_code=400, detail="path is a directory")

    headers: dict[str, str] = {
        "Content-Length": str(len(payload.content)),
    }
    if payload.truncated:
        headers["X-Truncated"] = "true"
        headers["X-Original-Size"] = str(payload.original_size)

    return Response(
        content=payload.content,
        media_type=payload.content_type,
        headers=headers,
    )
