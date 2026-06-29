"""GitHub API 底层 HTTP 客户端 + 速率限制跟踪（内部模块）。"""

from __future__ import annotations

import base64
import logging
from datetime import UTC, datetime
from typing import Any, cast

import httpx

from review_agent.service.git.base import PRFile
from review_agent.types.exceptions import GitProviderError

logger = logging.getLogger(__name__)

_GITHUB_API_BASE = "https://api.github.com"


class GitHubRateLimitError(GitProviderError):  # type: ignore[misc]
    """GitHub API 速率限制已耗尽。"""

    def __init__(self, reset_time: float | None = None) -> None:
        self.reset_time = reset_time
        reset_str = (
            datetime.fromtimestamp(reset_time, tz=UTC).isoformat() if reset_time else "unknown"
        )
        super().__init__(f"GitHub API rate limit exceeded. Resets at {reset_str}")


class _GitHubClient:
    """GitHub REST API 异步客户端 — 内置速率限制跟踪和分页支持。

    GitHubProvider 的内部基础设施，不对外暴露。
    """

    def __init__(self, token: str) -> None:
        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "review-agent",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        else:
            logger.info("GitHub token not configured — using unauthenticated access (rate limited)")
        self._http = httpx.AsyncClient(
            base_url=_GITHUB_API_BASE,
            headers=headers,
            timeout=httpx.Timeout(15.0),
        )
        self._rate_limit_remaining: int | None = None
        self._rate_limit_limit: int | None = None
        self._rate_limit_reset: int | None = None

    async def close(self) -> None:
        """关闭底层 HTTP 连接。"""
        await self._http.aclose()

    # ── Rate limit ─────────────────────────────────────────────

    def _track_rate_limit(self, resp: httpx.Response) -> None:
        """从响应头更新速率限制状态。"""
        limit = resp.headers.get("x-ratelimit-limit")
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if limit is not None:
            self._rate_limit_limit = int(limit)
        if remaining is not None:
            self._rate_limit_remaining = int(remaining)
        if reset is not None:
            self._rate_limit_reset = int(reset)

        if (
            self._rate_limit_remaining is not None
            and self._rate_limit_limit is not None
            and self._rate_limit_limit > 0
        ):
            pct = self._rate_limit_remaining / self._rate_limit_limit
            if pct < 0.1:
                reset_ts = self._rate_limit_reset or 0
                reset_str = datetime.fromtimestamp(reset_ts, tz=UTC).isoformat()
                logger.warning(
                    "GitHub API rate limit low: %d/%d (%.0f%%) remaining, resets at %s",
                    self._rate_limit_remaining,
                    self._rate_limit_limit,
                    pct * 100,
                    reset_str,
                )

    def _ensure_rate_limit(self) -> None:
        """若已知速率限制耗尽则立即抛出。"""
        if self._rate_limit_remaining is not None and self._rate_limit_remaining <= 0:
            raise GitHubRateLimitError(self._rate_limit_reset)

    # ── HTTP wrappers ──────────────────────────────────────────

    async def get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        self._ensure_rate_limit()
        resp = await self._http.get(path, params=params)
        self._track_rate_limit(resp)
        return resp

    async def post(self, path: str, json_data: dict[str, Any] | None = None) -> httpx.Response:
        self._ensure_rate_limit()
        resp = await self._http.post(path, json=json_data)
        self._track_rate_limit(resp)
        return resp

    async def patch(self, path: str, json_data: dict[str, Any] | None = None) -> httpx.Response:
        self._ensure_rate_limit()
        resp = await self._http.patch(path, json=json_data)
        self._track_rate_limit(resp)
        return resp

    # ── Pagination ─────────────────────────────────────────────

    @staticmethod
    def _next_link(resp: httpx.Response) -> str | None:
        link = resp.headers.get("link", "")
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip(" <>")
                if url.startswith(_GITHUB_API_BASE):
                    url = url[len(_GITHUB_API_BASE) :]
                return cast(str, url)
        return None

    async def paginate(
        self, path: str, params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """分页获取 GitHub API 列表资源。"""
        results: list[dict[str, Any]] = []
        current_path: str | None = path
        current_params = params
        while current_path is not None:
            resp = await self.get(current_path, params=current_params)
            if resp.status_code == 404:
                return results
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list):
                results.extend(data)
            else:
                return results
            current_path = self._next_link(resp)
            current_params = None
        return results

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def parse_pr_files(items: list[dict[str, Any]]) -> list[PRFile]:
        """将 GitHub API 文件列表转为 PRFile 列表。"""
        return [
            PRFile(
                filename=f["filename"],
                status=f["status"],
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
            )
            for f in items
        ]

    @staticmethod
    def decode_file_content(data: dict[str, Any]) -> str | None:
        """解码 GitHub Contents API 返回的文件内容。"""
        if isinstance(data, list):
            return None  # directory listing
        if data.get("encoding") == "base64" and data.get("content"):
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        return None
