"""
Subprocess wrappers for git log / git diff, and a unified-diff splitter.
Raises review.GitUnavailable on subprocess failure or git not on PATH.
"""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from app.services.review import FileDiff, GitUnavailable

EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


def _run_git(args: list, repo_root: Path) -> str:
    """Run a git command in repo_root; raise GitUnavailable on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        raise GitUnavailable("git not found on PATH")
    except subprocess.TimeoutExpired:
        raise GitUnavailable("git command timed out")

    if result.returncode != 0:
        raise GitUnavailable(result.stderr.strip() or "git returned non-zero")

    return result.stdout


def matching_commits(repo_root: Path, ticket_id: int) -> list:
    """Run git log and return commits matching the ticket id pattern.

    Pattern: case-insensitive #N\\b or ticket[_ ]N\\b
    Returns [(short_sha, message), ...] newest-first (git log default order).
    """
    output = _run_git(["log", "--oneline", "--no-decorate"], repo_root)
    pattern = re.compile(rf"(?i)(#{ticket_id}\b|ticket[_ ]{ticket_id}\b)")
    results = []
    for line in output.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        sha, message = parts[0], parts[1]
        if pattern.search(message):
            results.append((sha, message))
    return results


def diff_for_commit(repo_root: Path, sha: str) -> str:
    """Get the diff for a commit.

    Tries git diff <sha>^ <sha>. On non-zero exit (root commit),
    falls back to git diff EMPTY_TREE_SHA <sha>.
    """
    try:
        return _run_git(["diff", f"{sha}^", sha], repo_root)
    except GitUnavailable:
        return _run_git(["diff", EMPTY_TREE_SHA, sha], repo_root)


def split_per_file(diff_text: str) -> list:
    """Parse a unified diff into per-file FileDiff blocks.

    Splits on lines starting with 'diff --git '.
    Path is from '+++ b/<path>' line; if that's /dev/null, use '--- a/<path>'.
    additions/deletions: count +/- lines excluding +++/---.
    """
    if not diff_text.strip():
        return []

    blocks: list[str] = []
    current: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("diff --git "):
            if current:
                blocks.append("\n".join(current))
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current))

    results: list = []
    for block in blocks:
        path = _extract_path(block)
        additions, deletions = _count_changes(block)
        results.append(FileDiff(
            path=path,
            diff=block,
            additions=additions,
            deletions=deletions,
        ))
    return results


def _extract_path(block: str) -> str:
    """Extract the file path from a single per-file diff block."""
    plus_line: str | None = None
    minus_line: str | None = None
    for line in block.splitlines():
        if line.startswith("+++ ") and plus_line is None:
            plus_line = line
        elif line.startswith("--- ") and minus_line is None:
            minus_line = line

    # Use +++ line unless it points to /dev/null (deleted file)
    if plus_line and "+++ /dev/null" not in plus_line:
        path = plus_line[4:]  # strip "+++ "
        if path.startswith("b/"):
            path = path[2:]
        return path

    # Fall back to --- line
    if minus_line and "--- /dev/null" not in minus_line:
        path = minus_line[4:]  # strip "--- "
        if path.startswith("a/"):
            path = path[2:]
        return path

    return "/dev/null"


def _count_changes(block: str) -> tuple:
    """Count additions and deletions in a diff block, excluding +++ and --- header lines."""
    additions = 0
    deletions = 0
    for line in block.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            additions += 1
        elif line.startswith("-"):
            deletions += 1
    return additions, deletions
