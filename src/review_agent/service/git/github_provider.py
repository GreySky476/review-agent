"""GitHub Git 平台适配器。"""

from __future__ import annotations

import logging

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
        self._client = Github(token or settings.github_token)

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

    async def get_file_content(
        self, repo_name: str, file_path: str, ref: str
    ) -> str | None:
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

    async def publish_summary_comment(
        self, repo_name: str, pr_number: int, summary: str
    ) -> None:
        repo, pr = self._get_repo_and_pr(repo_name, pr_number)
        try:
            pr.create_issue_comment(summary)
        except Exception as exc:
            msg = f"Failed to publish summary on {repo_name}#{pr_number}: {exc}"
            raise GitProviderError(msg) from exc
