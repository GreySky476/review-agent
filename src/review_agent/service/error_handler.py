"""错误日志服务处理。

封装 ReviewErrorRepo 的查询操作，供 api/errors.py 使用。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.review_error import ReviewErrorRepo
from review_agent.types.orm import ReviewErrorLog


async def list_errors(
    db: AsyncSession,
    *,
    project_id: str | None = None,
    error_type: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[ReviewErrorLog]:
    """按筛选条件查询错误日志列表。

    Args:
        db: Database session.
        project_id: 可选，按项目过滤。
        error_type: 可选，按错误类型过滤。
        start_date: 可选，起始时间。
        end_date: 可选，结束时间。
        skip: 分页偏移。
        limit: 每页条数。

    Returns:
        错误日志列表。
    """
    repo = ReviewErrorRepo(db)
    return await repo.list_with_filters(  # type: ignore[no-any-return]
        project_id=project_id,
        error_type=error_type,
        start_date=start_date,
        end_date=end_date,
        skip=skip,
        limit=limit,
    )


async def count_errors_by_type(
    db: AsyncSession,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> list[dict[str, object]]:
    """按错误类型统计数量。

    Args:
        db: Database session.
        start_date: 可选，起始时间。
        end_date: 可选，结束时间。

    Returns:
        列表，每项包含 error_type, count, last_occurred。
    """
    repo = ReviewErrorRepo(db)
    return await repo.count_by_type(start_date=start_date, end_date=end_date)  # type: ignore[no-any-return]
