"""GitHub Git 平台适配器。"""

from __future__ import annotations

import logging
from typing import Any

import github.Auth
from github import Github
from github.PullRequest import PullRequest

from review_agent.config.settings import get_settings
from review_agent.service.git.base import GitProvider, PRFile, PRInfo, ReviewComment
from review_agent.types.exceptions import GitProviderError

logger = logging.getLogger(__name__)


class GitHubProvider(GitProvider):  # type: ignore[misc]
    """GitHub API 适配器。

    使用 PyGithub 库封装 GitHub REST API 调用。
    """

    def __init__(self, token: str | None = None) -> None:
        settings = get_settings()
        token_str = token or settings.github_token
        auth = github.Auth.Token(token_str) if token_str else None
        self._client = Github(auth=auth, timeout=15)

    def _get_repo_and_pr(self, repo_name: str, pr_number: int) -> tuple[object, PullRequest]:
        """获取仓库和 PR 对象。"""
        try:
            repo = self._client.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            return repo, pr
        except Exception as exc:
            msg = f"Failed to fetch PR {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc

    async def get_pr_info(self, repo_name: str, pr_number: int) -> PRInfo:
        repo, pr = self._get_repo_and_pr(repo_name, pr_number)
        return PRInfo(
            repo_name=repo_name,
            pr_number=pr_number,
            title=pr.title or "",
            description=pr.body or "",
            head_sha=pr.head.sha,
            base_sha=pr.base.sha,
            author=pr.user.login if pr.user else "",
        )

    async def get_pr_diff(self, repo_name: str, pr_number: int) -> list[PRFile]:
        repo, pr = self._get_repo_and_pr(repo_name, pr_number)
        try:
            files = []
            for f in pr.get_files():
                files.append(
                    PRFile(
                        filename=f.filename,
                        status=f.status,
                        additions=f.additions,
                        deletions=f.deletions,
                        patch=f.patch,
                    )
                )
            return files
        except Exception as exc:
            msg = f"Failed to fetch diff for {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc

    async def get_file_content(self, repo_name: str, file_path: str, ref: str) -> str | None:
        try:
            repo = self._client.get_repo(repo_name)
            content = repo.get_contents(file_path, ref=ref)
            # get_contents can return ContentFile or list[ContentFile]
            if isinstance(content, list):
                return None
            if content.decoded_content:
                return content.decoded_content.decode("utf-8", errors="replace")
            return None
        except Exception:
            logger.warning("Failed to fetch file %s@%s:%s", repo_name, ref, file_path)
            return None

    async def get_commit_diff(self, repo_name: str, sha: str) -> list[PRFile]:
        """获取单次提交的变更文件列表（含 patch）。"""
        try:
            repo = self._client.get_repo(repo_name)
            commit = repo.get_commit(sha)
            files = []
            for f in commit.files:
                files.append(
                    PRFile(
                        filename=f.filename,
                        status=f.status,
                        additions=f.additions,
                        deletions=f.deletions,
                        patch=getattr(f, "patch", None),
                    )
                )
            return files
        except Exception as exc:
            msg = f"Failed to fetch commit diff {repo_name}@{sha}: {exc}"
            raise GitProviderError(msg) from exc

    async def publish_commit_summary(self, repo_name: str, sha: str, summary: str) -> None:
        """在提交上发布摘要评论。"""
        try:
            repo = self._client.get_repo(repo_name)
            commit = repo.get_commit(sha)
            commit.create_comment(body=summary)
        except Exception as exc:
            msg = f"Failed to publish commit summary on {repo_name}@{sha}: {exc}"
            raise GitProviderError(msg) from exc

    async def publish_line_comments(
        self, repo_name: str, pr_number: int, comments: list[ReviewComment]
    ) -> None:
        if not comments:
            return
        repo, pr = self._get_repo_and_pr(repo_name, pr_number)
        try:
            # Group by file and create review comments
            for comment in comments:
                pr.create_review_comment(
                    body=comment.body,
                    commit=pr.head.sha,
                    path=comment.file_path,
                    line=comment.line,
                )
        except Exception as exc:
            msg = f"Failed to publish line comments on {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc

    async def publish_summary_comment(self, repo_name: str, pr_number: int, summary: str) -> None:
        repo, pr = self._get_repo_and_pr(repo_name, pr_number)
        try:
            pr.create_issue_comment(summary)
        except Exception as exc:
            msg = f"Failed to publish summary on {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc

    async def check_webhook(self, repo_name: str, webhook_url: str) -> dict[str, Any]:
        """检查仓库是否已配置指定 URL 的 Webhook。

        返回: found/hook_id/active/last_response
        """
        try:
            repo = self._client.get_repo(repo_name)
            hooks = repo.get_hooks()
            for hook in hooks:
                config_url = hook.config.get("url", "") if hook.config else ""
                if webhook_url in config_url:
                    return {
                        "found": True,
                        "hook_id": hook.id,
                        "active": hook.active,
                        "last_response": None,
                    }
            return {"found": False, "hook_id": None, "active": None, "last_response": None}
        except Exception as exc:
            logger.warning("Failed to check webhook for %s: %s", repo_name, exc)
            return {"found": False, "hook_id": None, "active": None, "last_response": str(exc)}

    async def send_webhook_ping(self, repo_name: str, hook_id: int) -> bool:
        """向指定 Webhook 发送测试 ping。

        Returns: True if ping was sent successfully.
        """
        try:
            repo = self._client.get_repo(repo_name)
            hook = repo.get_hook(hook_id)
            hook.test()
            logger.info("Webhook ping sent to %s hook #%d", repo_name, hook_id)
            return True
        except Exception as exc:
            logger.warning("Failed to ping webhook for %s: %s", repo_name, exc)
            return False
