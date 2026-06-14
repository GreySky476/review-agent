"""Git 平台适配器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PRInfo:
    """Pull Request 基本信息。"""

    repo_name: str
    pr_number: int
    title: str
    description: str
    head_sha: str
    base_sha: str
    author: str


@dataclass
class PRFile:
    """PR 中的变更文件。"""

    filename: str
    status: str  # added, modified, removed, renamed
    additions: int
    deletions: int
    patch: str | None = None


@dataclass
class ReviewComment:
    """行级评审评论。"""

    file_path: str
    line: int
    body: str
    commit_sha: str | None = None


class GitProvider(ABC):
    """Git 平台 API 抽象。

    所有平台（GitHub、GitLab、Gitee）需实现此接口。
    """

    @abstractmethod
    async def get_pr_info(self, repo_name: str, pr_number: int) -> PRInfo:
        """获取 PR 基本信息。

        Args:
            repo_name: 仓库全名（如 "owner/repo"）。
            pr_number: PR 编号。

        Returns:
            PR 基本信息。
        """
        ...

    @abstractmethod
    async def get_pr_diff(self, repo_name: str, pr_number: int) -> list[PRFile]:
        """获取 PR 的 Diff 内容。

        Args:
            repo_name: 仓库全名。
            pr_number: PR 编号。

        Returns:
            变更文件列表。
        """
        ...

    @abstractmethod
    async def get_file_content(self, repo_name: str, file_path: str, ref: str) -> str | None:
        """获取仓库中指定文件的完整内容。

        Args:
            repo_name: 仓库全名。
            file_path: 文件路径。
            ref: 分支名或 commit SHA。

        Returns:
            文件内容，不存在时返回 None。
        """
        ...

    @abstractmethod
    async def get_commit_diff(self, repo_name: str, sha: str) -> list[PRFile]:
        """获取单次提交的变更文件列表（含 patch）。

        Args:
            repo_name: 仓库全名（如 "owner/repo"）。
            sha: 提交 SHA。

        Returns:
            变更文件列表。
        """
        ...

    @abstractmethod
    async def get_compare_diff(self, repo_name: str, base_sha: str, head_sha: str) -> list[PRFile]:
        """获取两个 SHA 之间的差异文件列表（用于增量比较）。

        Args:
            repo_name: 仓库全名。
            base_sha: 起始 SHA（上次已评的 commit）。
            head_sha: 目标 SHA（当前 head commit）。

        Returns:
            变更文件列表。
        """
        ...

    @abstractmethod
    async def publish_commit_summary(self, repo_name: str, sha: str, summary: str) -> None:
        """在提交上发布摘要评论。

        Args:
            repo_name: 仓库全名。
            sha: 提交 SHA。
            summary: Markdown 格式的摘要内容。
        """
        ...

    @abstractmethod
    async def publish_line_comments(
        self, repo_name: str, pr_number: int, comments: list[ReviewComment]
    ) -> None:
        """在 PR 中发布行级评论。

        Args:
            repo_name: 仓库全名。
            pr_number: PR 编号。
            comments: 评论列表。
        """
        ...

    @abstractmethod
    async def publish_summary_comment(
        self, repo_name: str, pr_number: int, summary: str
    ) -> int | None:
        """在 PR 中发布摘要评论。

        Args:
            repo_name: 仓库全名。
            pr_number: PR 编号。
            summary: Markdown 格式的摘要内容。
        """
        ...

    @abstractmethod
    async def list_open_prs(self, repo_name: str) -> list[dict[str, Any]]:
        """列出仓库所有 Open 状态的 PR。

        Args:
            repo_name: 仓库全名（如 "owner/repo"）。

        Returns:
            list[dict]: [{pr_number, title, head_sha, base_sha, author, state}, ...]
        """
        ...
