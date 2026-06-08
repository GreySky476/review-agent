"""项目管理 REST API 端点。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.project import ProjectRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.types.models import ProjectCreate, ProjectUpdate
from review_agent.types.orm import ProjectModel

router = APIRouter(tags=["projects"])

# Webhook 无事件超过此时间视为不活跃
_WEBHOOK_INACTIVE_HOURS = 24


def _format_project(
    project: ProjectModel,
    webhook_last_event_at: datetime | None,
) -> dict[str, Any]:
    """统一格式化项目响应。"""
    webhook_enabled = project.webhook_enabled

    # 推断 webhook 真实状态
    if not webhook_enabled:
        webhook_status = "disconnected"
    elif webhook_last_event_at is None:
        webhook_status = "never_connected"
    elif (datetime.now(UTC) - webhook_last_event_at) > timedelta(hours=_WEBHOOK_INACTIVE_HOURS):
        webhook_status = "inactive"
    else:
        webhook_status = "connected"

    return {
        "id": project.id,
        "name": project.name,
        "platform": project.platform,
        "repo_url": project.repo_url,
        "webhook_enabled": webhook_enabled,
        "webhook_status": webhook_status,
        "webhook_last_event_at": (
            webhook_last_event_at.isoformat() if webhook_last_event_at else None
        ),
        "recent_review_time": (
            project.update_time.isoformat() if project.update_time else None
        ),
        "pr_count": 0,
        "review_count": 0,
    }


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """注册新项目。"""
    repo = ProjectRepo(db)
    project = await repo.create(
        name=body.name,
        platform=body.platform.value,
        repo_url=body.repo_url,
        webhook_enabled=False,
    )
    return _format_project(project, webhook_last_event_at=None)


@router.get("/projects")
async def list_projects(
    platform: str | None = Query(None, pattern="^(github|gitlab|gitee)$"),
    search: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目列表。"""
    repo = ProjectRepo(db)
    webhook_repo = WebhookEventRepo(db)
    filters: dict[str, Any] = {}
    if platform:
        filters["platform"] = platform
    if search:
        _ = search
    items = await repo.list(
        skip=(page - 1) * page_size,
        limit=page_size,
        filters=filters if filters else None,
    )
    total = await repo.count(filters=filters if filters else None)

    # 获取每个项目的最后 webhook 事件时间
    items_out: list[dict[str, Any]] = []
    for p in items:
        last_event = await webhook_repo.last_event_time(p.id)
        items_out.append(_format_project(p, last_event))

    return {
        "items": items_out,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/projects/{project_id}")
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目详情。"""
    repo = ProjectRepo(db)
    webhook_repo = WebhookEventRepo(db)
    project = await repo.get_active(project_id)

    if project is None:
        return {
            "id": project_id,
            "name": "",
            "platform": "",
            "repo_url": "",
            "webhook_enabled": False,
            "webhook_status": "disconnected",
            "webhook_last_event_at": None,
            "recent_review_time": None,
            "pr_count": 0,
            "review_count": 0,
            "webhook_events": [],
        }

    last_event = await webhook_repo.last_event_time(project_id)
    result = _format_project(project, last_event)
    result["webhook_events"] = []
    return result


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    _body: ProjectUpdate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新项目配置。"""
    _ = _body
    repo = ProjectRepo(db)
    await repo.update(project_id, name=_body.name or project_id)
    return {"id": project_id, "updated": True}


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """删除项目（软删除）。"""
    repo = ProjectRepo(db)
    await repo.soft_delete(project_id)
    return {"id": project_id, "deleted": True}
