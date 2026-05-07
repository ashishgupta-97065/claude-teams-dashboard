from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

import httpx


@dataclass
class Issue:
    number: int
    title: str
    github_state: str
    status: str = "open"


@dataclass
class CacheMeta:
    fetched_at: datetime
    stale: bool
    error: str | None


_CACHE_TTL_SECONDS = 10


class GitHubClient:
    def __init__(self, repo: str, token: str | None, http: httpx.AsyncClient) -> None:
        self._repo = repo
        self._token = token
        self._http = http
        self._cached_issues: list[Issue] = []
        self._cached_at: float = 0.0
        self._etag: str | None = None
        self._last_meta: CacheMeta = CacheMeta(
            fetched_at=datetime.utcnow(), stale=False, error=None
        )

    def _build_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/vnd.github+json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        if self._etag:
            headers["If-None-Match"] = self._etag
        return headers

    def _parse_issues(self, data: list[dict]) -> list[Issue]:
        issues: list[Issue] = []
        for item in data:
            if "pull_request" in item:
                continue
            issues.append(
                Issue(
                    number=item["number"],
                    title=item.get("title", ""),
                    github_state=item.get("state", "open"),
                )
            )
        return issues

    async def list_issues(self) -> tuple[list[Issue], CacheMeta]:
        """Fetch issues for `repo` (open + closed, page 1 only). Uses ETag conditional
        GET; on 304 returns cached. On error returns (last_cached_or_empty,
        CacheMeta(stale=True, error=...))."""
        now = time.monotonic()
        if now - self._cached_at < _CACHE_TTL_SECONDS and self._cached_issues:
            meta = CacheMeta(
                fetched_at=self._last_meta.fetched_at,
                stale=False,
                error=None,
            )
            return list(self._cached_issues), meta

        url = f"https://api.github.com/repos/{self._repo}/issues"
        params = {"state": "all", "per_page": "100"}
        try:
            response = await self._http.get(
                url, headers=self._build_headers(), params=params, timeout=10.0
            )
            if response.status_code == 304:
                self._cached_at = now
                meta = CacheMeta(
                    fetched_at=datetime.utcnow(), stale=False, error=None
                )
                self._last_meta = meta
                return list(self._cached_issues), meta

            if response.status_code == 200:
                etag = response.headers.get("ETag")
                if etag:
                    self._etag = etag
                issues = self._parse_issues(response.json())
                self._cached_issues = issues
                self._cached_at = now
                meta = CacheMeta(
                    fetched_at=datetime.utcnow(), stale=False, error=None
                )
                self._last_meta = meta
                return list(issues), meta

            error_msg = f"GitHub API returned {response.status_code}"
            meta = CacheMeta(
                fetched_at=self._last_meta.fetched_at, stale=True, error=error_msg
            )
            self._last_meta = meta
            return list(self._cached_issues), meta

        except Exception as exc:
            error_msg = str(exc)
            meta = CacheMeta(
                fetched_at=self._last_meta.fetched_at, stale=True, error=error_msg
            )
            self._last_meta = meta
            return list(self._cached_issues), meta
