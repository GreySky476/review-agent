"""Finding 查询与反馈服务处理。

封装 FindingRepo 和 CommentRepo 的查询与写入操作，供 api/findings.py 使用。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.comment import CommentRepo
from review_agent.repo.finding import FindingRepo
from review_agent.types.orm import CommentModel, FindingModel


async def list_findings_by_review(db: AsyncSession, review_id: str) -> list[FindingModel]:
    """获取指定评审的所有 Finding。

    Args:
        db: Database session.
        review_id: 评审 ID。

    Returns:
        Finding 列表。
    """
    repo = FindingRepo(db)
    return await repo.list_by_review(review_id)  # type: ignore[no-any-return]


async def list_comments_by_finding(db: AsyncSession, finding_id: str) -> list[CommentModel]:
    """获取指定 Finding 的所有评论。

    Args:
        db: Database session.
        finding_id: Finding ID。

    Returns:
        评论列表。
    """
    repo = CommentRepo(db)
    return await repo.list_by_finding(finding_id)  # type: ignore[no-any-return]


async def delete_comment(db: AsyncSession, comment_id: str) -> None:
    """硬删除一条评论。

    Args:
        db: Database session.
        comment_id: 评论 ID。
    """
    repo = CommentRepo(db)
    await repo.hard_delete(comment_id)


async def update_comment(db: AsyncSession, comment_id: str, **kwargs: object) -> None:
    """更新一条评论。

    Args:
        db: Database session.
        comment_id: 评论 ID。
        **kwargs: 更新字段。
    """
    repo = CommentRepo(db)
    await repo.update(comment_id, **kwargs)


async def create_comment(
    db: AsyncSession,
    *,
    review_id: str,
    finding_id: str | None = None,
    author: str = "anonymous",
    content: str = "",
    action: str | None = None,
) -> CommentModel:
    """创建一条评论。

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
