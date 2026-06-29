"""Webhook 事件日志查询 API。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.types.orm import WebhookEventModel

router = APIRouter(tags=["webhook-events"])  # TODO: 登录页面未就绪，暂时不启用 JWT 认证


@router.get("/projects/{project_id}/webhook-events")
async def list_webhook_events(
    project_id: str,
    action: str | None = Query(None, pattern="^(opened|synchronize|reopened|closed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的 Webhook 事件日志。"""
    # Count
    count_stmt = select(WebhookEventModel.id).where(WebhookEventModel.project_id == project_id)
    if action:
        count_stmt = count_stmt.where(WebhookEventModel.action == action)
    total_result = await db.execute(count_stmt)
    total = len(total_result.scalars().all())

    # List
    stmt = (
        select(WebhookEventModel)
        .where(WebhookEventModel.project_id == project_id)
        .order_by(WebhookEventModel.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    if action:
        stmt = stmt.where(WebhookEventModel.action == action)

    rows = await db.execute(stmt)
    events = rows.scalars().all()

    return {
        "items": [
            {
                "id": e.id,
                "event_id": e.event_id,
                "platform": e.platform,
                "action": e.action,
                "pr_number": e.pr_number,
                "is_processed": e.is_processed,
                "create_time": e.create_time.isoformat() if e.create_time else None,
            }
            for e in events
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }
