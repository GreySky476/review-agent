"""GitHub Git 平台适配器 — 基于 httpx 的全异步实现。"""

from __future__ import annotations

import logging
from typing import Any, cast

import httpx

from review_agent.config.settings import get_settings
from review_agent.service.error_logger import log_error
from review_agent.service.git._github_client import _GitHubClient
from review_agent.service.git.base import GitProvider, PRFile, PRInfo, ReviewComment
from review_agent.types.exceptions import GitProviderError

logger = logging.getLogger(__name__)


class GitHubProvider(GitProvider):  # type: ignore[misc]
    """GitHub API 适配器 — 基于 httpx AsyncClient 的全异步实现。

    替代了原有的 PyGithub 同步封装，避免阻塞事件循环。
    内置 GitHub API 速率限制跟踪，在剩余次数归零时主动抛异常。
    """

    def __init__(self, token: str | None = None) -> None:
        settings = get_settings()
        token_str = token or settings.github_token.get_secret_value() or ""
        self._client = _GitHubClient(token_str)

    async def close(self) -> None:
        """关闭底层 HTTP 客户端。"""
        await self._client.close()

    # ── PR 查询 ────────────────────────────────────────────────

    async def get_pr_info(self, repo_name: str, pr_number: int) -> PRInfo:
        try:
            resp = await self._client.get(f"/repos/{repo_name}/pulls/{pr_number}")
            resp.raise_for_status()
            data = resp.json()
            return PRInfo(
                repo_name=repo_name,
                pr_number=pr_number,
                title=data.get("title", ""),
                description=data.get("body", ""),
                head_sha=data["head"]["sha"],
                base_sha=data["base"]["sha"],
                author=data.get("user", {}).get("login", "") if data.get("user") else "",
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            await log_error(
                error_type="git_api_failed",
                error_message=f"Failed to get PR info for {repo_name}#{pr_number}",
            )
            msg = f"Failed to fetch PR {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc

    async def get_pr_commits(self, repo_name: str, pr_number: int) -> list[dict[str, Any]]:
        """获取 PR 的所有 commit 列表。"""
        try:
            items = await self._client.paginate(f"/repos/{repo_name}/pulls/{pr_number}/commits")
            commits: list[dict[str, Any]] = []
            for c in items:
                commit_data = c.get("commit", {})
                author_data = commit_data.get("author", {})
                commits.append(
                    {
                        "sha": c.get("sha", ""),
                        "message": (commit_data.get("message") or "").split("\n")[0],
                        "author": author_data.get("name"),
                        "date": author_data.get("date"),
                    }
                )
            return commits
        except Exception as exc:
            logger.warning("Failed to fetch commits for %s#%d: %s", repo_name, pr_number, exc)
            return []

    async def list_open_prs(self, repo_name: str) -> list[dict[str, Any]]:
        """列出仓库所有 Open 状态的 PR。"""
        try:
            items = await self._client.paginate(
                f"/repos/{repo_name}/pulls", params={"state": "open"}
            )
            return [
                {
                    "pr_number": pr["number"],
                    "title": pr.get("title", ""),
                    "head_sha": pr["head"]["sha"],
                    "base_sha": pr["base"]["sha"],
                    "author": pr.get("user", {}).get("login", "") if pr.get("user") else "",
                    "state": "open",
                }
                for pr in items
            ]
        except Exception as exc:
            logger.warning("Failed to list open PRs for %s: %s", repo_name, exc)
            return []

    async def get_pr_diff(self, repo_name: str, pr_number: int) -> list[PRFile]:
        try:
            items = await self._client.paginate(f"/repos/{repo_name}/pulls/{pr_number}/files")
            return cast(list[PRFile], self._client.parse_pr_files(items))
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            await log_error(
                error_type="git_api_failed",
                error_message=f"Failed to fetch diff for {repo_name}#{pr_number}: {exc}",
            )
            msg = f"Failed to fetch diff for {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc

    async def get_file_content(self, repo_name: str, file_path: str, ref: str) -> str | None:
        try:
            resp = await self._client.get(
                f"/repos/{repo_name}/contents/{file_path}", params={"ref": ref}
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return cast("str | None", self._client.decode_file_content(resp.json()))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            logger.warning("Failed to fetch file %s@%s:%s", repo_name, ref, file_path)
        except httpx.RequestError:
            logger.warning("Failed to fetch file %s@%s:%s", repo_name, ref, file_path)
        await log_error(
            error_type="git_file_fetch_failed",
            error_message=f"Failed to fetch file {repo_name}@{ref}:{file_path}",
        )
        return None

    async def get_commit_diff(self, repo_name: str, sha: str) -> list[PRFile]:
        """获取单次提交的变更文件列表（含 patch）。"""
        try:
            resp = await self._client.get(f"/repos/{repo_name}/commits/{sha}")
            resp.raise_for_status()
            files_data = resp.json().get("files", [])
            if isinstance(files_data, list):
                return cast(list[PRFile], self._client.parse_pr_files(files_data))
            return []
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            msg = f"Failed to fetch commit diff {repo_name}@{sha}: {exc}"
            await log_error(error_type="git_api_failed", error_message=msg)
            raise GitProviderError(msg) from exc

    async def get_compare_diff(self, repo_name: str, base_sha: str, head_sha: str) -> list[PRFile]:
        """获取两个 SHA 之间的差异文件列表（用于增量比较）。"""
        try:
            resp = await self._client.get(f"/repos/{repo_name}/compare/{base_sha}...{head_sha}")
            resp.raise_for_status()
            files_data = resp.json().get("files", [])
            if isinstance(files_data, list):
                return cast(list[PRFile], self._client.parse_pr_files(files_data))
            return []
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            msg = f"Failed to compare diff {repo_name}@{base_sha}..{head_sha}: {exc}"
            logger.warning(msg)
            await log_error(error_type="git_api_failed", error_message=msg)
            raise GitProviderError(msg) from exc

    # ── 发布评论 ──────────────────────────────────────────────

    async def publish_commit_summary(self, repo_name: str, sha: str, summary: str) -> None:
        try:
            resp = await self._client.post(
                f"/repos/{repo_name}/commits/{sha}/comments", json_data={"body": summary}
            )
            resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            msg = f"Failed to publish commit summary on {repo_name}@{sha}: {exc}"
            await log_error(error_type="publish_failed", error_message=msg)
            raise GitProviderError(msg) from exc

    async def publish_line_comments(
        self, repo_name: str, pr_number: int, comments: list[ReviewComment]
    ) -> None:
        if not comments:
            return
        try:
            pr_resp = await self._client.get(f"/repos/{repo_name}/pulls/{pr_number}")
            pr_resp.raise_for_status()
            head_sha = pr_resp.json()["head"]["sha"]
            for comment in comments:
                resp = await self._client.post(
                    f"/repos/{repo_name}/pulls/{pr_number}/comments",
                    json_data={
                        "body": comment.body,
                        "commit_id": comment.commit_sha or head_sha,
                        "path": comment.file_path,
                        "line": comment.line,
                    },
                )
                resp.raise_for_status()
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            msg = f"Failed to publish line comments on {repo_name}#{pr_number}: {exc}"
            await log_error(error_type="publish_failed", error_message=msg)
            raise GitProviderError(msg) from exc

    async def publish_summary_comment(
        self, repo_name: str, pr_number: int, summary: str
    ) -> int | None:
        try:
            resp = await self._client.post(
                f"/repos/{repo_name}/issues/{pr_number}/comments",
                json_data={"body": summary},
            )
            resp.raise_for_status()
            return cast("int | None", resp.json().get("id"))
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            msg = f"Failed to publish summary on {repo_name}#{pr_number}: {exc}"
            await log_error(error_type="publish_failed", error_message=msg)
            raise GitProviderError(msg) from exc

    async def get_issue_comment(self, repo_name: str, comment_id: int) -> str | None:
        """获取指定 PR Comment 的内容。"""
        try:
            resp = await self._client.get(f"/repos/{repo_name}/issues/comments/{comment_id}")
            resp.raise_for_status()
            return cast("str | None", resp.json().get("body"))
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning(
                "Failed to get issue comment #%d on %s: %s",
                comment_id,
                repo_name,
                exc,
            )
            return None

    async def edit_issue_comment(self, repo_name: str, comment_id: int, body: str) -> bool:
        """编辑指定 PR Comment 的内容（用于追评追加）。"""
        try:
            resp = await self._client.patch(
                f"/repos/{repo_name}/issues/comments/{comment_id}",
                json_data={"body": body},
            )
            resp.raise_for_status()
            return True
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            await log_error(
                error_type="publish_failed",
                error_message=(f"Failed to edit issue comment #{comment_id} on {repo_name}: {exc}"),
            )
            return False

    # ── Webhook ────────────────────────────────────────────────

    async def check_webhook(self, repo_name: str, webhook_url: str) -> dict[str, Any]:
        """检查仓库是否已配置指定 URL 的 Webhook。"""
        not_found: dict[str, Any] = {
            "found": False,
            "hook_id": None,
            "active": None,
            "events": [],
            "last_response": None,
        }
        try:
            items = await self._client.paginate(f"/repos/{repo_name}/hooks")
            for hook in items:
                config = hook.get("config", {})
                config_url = config.get("url", "") if config else ""
                if webhook_url in config_url:
                    return {
                        "found": True,
                        "hook_id": hook.get("id"),
                        "active": hook.get("active"),
                        "events": hook.get("events", []),
                        "last_response": None,
                    }
            return not_found
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("Failed to check webhook for %s: %s", repo_name, exc)
            await log_error(
                error_type="git_api_failed",
                error_message=f"Failed to check webhook for {repo_name}: {exc}",
            )
            return {**not_found, "last_response": str(exc)}

    async def send_webhook_ping(self, repo_name: str, hook_id: int) -> bool:
        """向指定 Webhook 发送测试 ping。"""
        try:
            resp = await self._client.post(f"/repos/{repo_name}/hooks/{hook_id}/tests")
            resp.raise_for_status()
            logger.info("Webhook ping sent to %s hook #%d", repo_name, hook_id)
            return True
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            logger.warning("Failed to ping webhook for %s: %s", repo_name, exc)
            await log_error(
                error_type="git_api_failed",
                error_message=f"Failed to ping webhook for {repo_name}: {exc}",
            )
            return False
