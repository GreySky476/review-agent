"""Git 平台适配器抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


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
    async def get_file_content(
        self, repo_name: str, file_path: str, ref: str
    ) -> str | None:
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
    ) -> None:
        """在 PR 中发布摘要评论。

        Args:
            repo_name: 仓库全名。
            pr_number: PR 编号。
            summary: Markdown 格式的摘要内容。
        """
        ...
