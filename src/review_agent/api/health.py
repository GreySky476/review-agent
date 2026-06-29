"""健康检查端点。"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.service.health import (
    get_platform_health_by_platform,
    get_platform_health_list,
    run_all_checks,
)
from review_agent.types.enums import Platform

router = APIRouter(tags=["health"])


@router.get("/health/platforms")
async def platform_health_list(
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """获取所有平台的连通性状态。"""
    return cast(list[dict[str, Any]], await get_platform_health_list(db))


@router.get("/health/platforms/{platform}")
async def platform_health_detail(
    platform: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取指定平台的连通性状态。"""
    try:
        p = Platform(platform)
    except ValueError:
        return {"platform": platform, "status": "unknown"}
    result = await get_platform_health_by_platform(db, p)
    if result is None:
        return {"platform": platform, "status": "pending", "latency_ms": 0, "error_message": None}
    return cast(dict[str, Any], result)


@router.post("/health/platforms/check", status_code=202)
async def trigger_health_check(
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """手动触发一次平台连通性检测。"""
    await run_all_checks(db)
    await db.commit()
    return {"status": "triggered"}
