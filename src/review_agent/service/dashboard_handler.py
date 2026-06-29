"""仪表盘服务处理 — 封装 PlatformHealthRepo/ProjectRepo/QualitySnapshotRepo 操作。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.platform_health import PlatformHealthRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.quality_snapshot import QualitySnapshotRepo
from review_agent.types.enums import SnapshotPeriod
from review_agent.types.orm import ProjectModel, QualitySnapshot


async def count_projects(db: AsyncSession) -> int:
    """统计项目总数。"""
    return await ProjectRepo(db).count()  # type: ignore[no-any-return]


async def list_projects_all(db: AsyncSession, *, limit: int = 100) -> list[ProjectModel]:
    """列出所有项目（不限分页）。"""
    return await ProjectRepo(db).list(limit=limit)  # type: ignore[no-any-return]


async def list_platform_health(db: AsyncSession) -> list[dict[str, Any]]:
    """列出所有平台连通性状态。"""
    return await PlatformHealthRepo(db).list_all()  # type: ignore[no-any-return]


async def list_quality_snapshots(
    db: AsyncSession,
    *,
    project_id: str | None = None,
    period: SnapshotPeriod = SnapshotPeriod.MONTHLY,
    start_date: Any = None,
    end_date: Any = None,
) -> list[QualitySnapshot]:
    """按项目和周期查询质量快照。"""
    return await QualitySnapshotRepo(db).list_by_project_and_period(  # type: ignore[no-any-return]
        project_id=project_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )
