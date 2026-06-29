"""评审服务处理。

封装 ReviewRepo 和 CommentRepo 的查询与写入操作，供 api/reviews.py 使用。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.comment import CommentRepo
from review_agent.repo.review import ReviewRepo
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import CommentModel, ReviewModel


async def create_or_get_review(
    db: AsyncSession,
    *,
    project_id: str,
    pr_number: int | None = None,
    head_sha: str | None = None,
    pr_title: str | None = None,
    status: ReviewStatus = ReviewStatus.PENDING,
) -> tuple[ReviewModel, bool]:
    """创建或获取评审记录（原子操作）。

    Args:
        db: Database session.
        project_id: 项目 ID。
        pr_number: PR 编号（可选，commit 评审时为 None）。
        head_sha: HEAD commit SHA。
        pr_title: PR 标题。
        status: 初始状态。

    Returns:
        (review, is_new) 元组，is_new=True 表示新创建。
    """
    repo = ReviewRepo(db)
    return await repo.create_or_get(  # type: ignore[no-any-return]
        project_id=project_id,
        pr_number=pr_number,
        head_sha=head_sha,
        pr_title=pr_title,
        status=status,
        task_id=None,
    )


async def get_review_by_id(db: AsyncSession, review_id: str) -> ReviewModel | None:
    """按 ID 获取评审记录。

    Args:
        db: Database session.
        review_id: 评审 ID。

    Returns:
        ReviewModel 或 None。
    """
    repo = ReviewRepo(db)
    return await repo.get(review_id)


async def list_reviews(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 20,
    filters: dict[str, Any] | None = None,
) -> list[ReviewModel]:
    """分页列出评审记录。

    Args:
        db: Database session.
        skip: 分页偏移。
        limit: 每页条数。
        filters: 过滤条件。

    Returns:
        评审记录列表。
    """
    repo = ReviewRepo(db)
    return await repo.list(skip=skip, limit=limit, filters=filters)  # type: ignore[no-any-return]


async def count_reviews(
    db: AsyncSession,
    *,
    filters: dict[str, Any] | None = None,
) -> int:
    """统计评审记录数量。

    Args:
        db: Database session.
        filters: 过滤条件。

    Returns:
        记录数量。
    """
    repo = ReviewRepo(db)
    return await repo.count(filters=filters)  # type: ignore[no-any-return]


async def list_comments_by_review(
    db: AsyncSession,
    review_id: str,
) -> list[CommentModel]:
    """获取评审的所有评论。

    Args:
        db: Database session.
        review_id: 评审 ID。

    Returns:
        评论列表。
    """
    repo = CommentRepo(db)
    return await repo.list_by_review(review_id)  # type: ignore[no-any-return]


async def create_comment_for_review(
    db: AsyncSession,
    *,
    review_id: str,
    finding_id: str | None = None,
    author: str = "anonymous",
    content: str = "",
    action: str | None = None,
) -> CommentModel:
    """为评审添加评论。

    Args:
        db: Database session.
        review_id: 评审 ID。
        finding_id: Finding ID（可选）。
        author: 作者。
        content: 内容。
        action: 操作类型。

    Returns:
        创建的评论对象。
    """
    repo = CommentRepo(db)
    return await repo.create(
        review_id=review_id,
        finding_id=finding_id,
        author=author,
        content=content,
        action=action,
    )
