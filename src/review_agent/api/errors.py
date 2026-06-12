"""异常监控 API 端点。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.review_error import ReviewErrorRepo
from review_agent.types.models import ErrorStats
from review_agent.types.orm import ReviewErrorLog

router = APIRouter(tags=["errors"])


def _parse_date(value: str | None) -> datetime | None:
    """将 ISO 日期字符串转为 datetime，失败时返回 None。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@router.get("/errors")
async def list_errors(
    project_id: str | None = Query(None),
    error_type: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取异常日志列表。"""
    repo = ReviewErrorRepo(db)

    items = await repo.list_with_filters(
        project_id=project_id,
        error_type=error_type,
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    # Count total
    count_stmt = select(func.count(ReviewErrorLog.id))
    if project_id:
        count_stmt = count_stmt.where(ReviewErrorLog.project_id == project_id)
    if error_type:
        count_stmt = count_stmt.where(ReviewErrorLog.error_type == error_type)
    result = await db.execute(count_stmt)
    total = result.scalar() or 0

    return {
        "items": [
            {
                "id": e.id,
                "project_id": e.project_id,
                "review_id": e.review_id,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "error_detail": e.error_detail,
                "frequency": e.frequency,
                "recovered": e.recovered,
                "create_time": e.create_time.isoformat() if e.create_time else None,
            }
            for e in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/errors/stats")
async def error_statistics(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
) -> list[ErrorStats]:
    """获取异常聚合统计。"""
    repo = ReviewErrorRepo(db)
    rows = await repo.count_by_type(
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
    )
    return [
        ErrorStats(
            error_type=row["error_type"],
            count=row["count"],
            last_occurred=row["last_occurred"],
        )
        for row in rows
    ]


@router.get("/errors/trend")
async def error_trend(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """按天统计错误数量趋势（用于折线图）。"""
    start = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(
            func.date(ReviewErrorLog.create_time).label("date"),
            func.count(ReviewErrorLog.id).label("count"),
        )
        .where(ReviewErrorLog.create_time >= start)
        .group_by(func.date(ReviewErrorLog.create_time))
        .order_by(func.date(ReviewErrorLog.create_time))
    )
    result = await db.execute(stmt)
    return [{"date": str(row.date), "count": row.count} for row in result.all()]
