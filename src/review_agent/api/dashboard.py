"""仪表盘统计 API 端点。"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.project import ProjectRepo
from review_agent.repo.quality_snapshot import QualitySnapshotRepo
from review_agent.types.models import DashboardStats
from review_agent.types.orm import ReviewErrorLog, ReviewModel

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_session),
) -> DashboardStats:
    """获取仪表盘统计信息。"""
    # Total projects (active)
    project_repo = ProjectRepo(db)
    total_projects = await project_repo.count()

    # Today's reviews
    today_start = sa.func.current_date()
    today_count_result = await db.execute(
        select(func.count(ReviewModel.id)).where(
            sa.cast(ReviewModel.create_time, sa.Date) == today_start,
            ReviewModel.is_deleted.is_(False),
        )
    )
    total_reviews_today = today_count_result.scalar() or 0

    # Average score
    avg_result = await db.execute(
        select(func.avg(ReviewModel.score)).where(
            ReviewModel.score.isnot(None),
            ReviewModel.is_deleted.is_(False),
        )
    )
    avg_score = avg_result.scalar() or 0.0

    # Pending errors (unrecovered)
    pending_result = await db.execute(
        select(func.count(ReviewErrorLog.id)).where(ReviewErrorLog.recovered.is_(False))
    )
    pending_errors = pending_result.scalar() or 0

    # Finding distribution by category
    find_dist_result = await db.execute(
        select(ReviewModel.findings_count)
        .where(
            ReviewModel.is_deleted.is_(False),
        )
    )
    all_findings_counts = find_dist_result.scalars().all()
    total_findings = sum(all_findings_counts)

    return DashboardStats(
        total_projects=total_projects,
        total_reviews_today=total_reviews_today,
        average_score=round(float(avg_score), 1),
        pending_errors=pending_errors,
        finding_distribution={"total": total_findings},
    )


@router.get("/dashboard/quality-trends")
async def quality_trends(
    project_id: str | None = Query(None),
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取质量趋势数据（折线图）。"""
    repo = QualitySnapshotRepo(db)

    start: Any = start_date
    end: Any = end_date

    snapshots = await repo.list_by_project_and_period(
        project_id=project_id,
        period=period,
        start_date=start,
        end_date=end,
    )

    return {
        "items": [
            {
                "date": s.snapshot_date.isoformat() if s.snapshot_date else "",
                "avg_score": s.avg_score,
                "total_reviews": s.total_reviews,
                "total_findings": s.total_findings,
                "critical": s.critical_count,
                "warning": s.warning_count,
                "info": s.info_count,
            }
            for s in snapshots
        ],
        "period": period,
    }
