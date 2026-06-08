"""项目管理 REST API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.project import ProjectRepo
from review_agent.types.models import ProjectCreate, ProjectUpdate

router = APIRouter(tags=["projects"])


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
    )
    return {
        "id": project.id,
        "name": project.name,
        "platform": project.platform,
        "repo_url": project.repo_url,
        "webhook_enabled": project.webhook_enabled,
        "recent_review_time": None,
        "pr_count": 0,
        "review_count": 0,
    }


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
    return {
        "items": [
            {
                "id": p.id,
                "name": p.name,
                "platform": p.platform,
                "repo_url": p.repo_url,
                "webhook_enabled": p.webhook_enabled,
                "recent_review_time": (
                    p.update_time.isoformat() if p.update_time else None
                ),
                "pr_count": 0,
                "review_count": 0,
            }
            for p in items
        ],
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
    project = await repo.get_active(project_id)
    if project is None:
        return {
            "id": project_id,
            "name": "",
            "platform": "",
            "repo_url": "",
            "webhook_enabled": True,
            "recent_review_time": None,
            "pr_count": 0,
            "review_count": 0,
            "webhook_events": [],
        }
    return {
        "id": project.id,
        "name": project.name,
        "platform": project.platform,
        "repo_url": project.repo_url,
        "webhook_enabled": project.webhook_enabled,
        "recent_review_time": (
            project.update_time.isoformat() if project.update_time else None
        ),
        "pr_count": 0,
        "review_count": 0,
        "webhook_events": [],
    }


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
