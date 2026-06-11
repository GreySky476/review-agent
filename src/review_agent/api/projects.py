"""项目管理 REST API 端点。"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.config.settings import get_settings
from review_agent.repo.project import ProjectRepo, normalize_repo_url
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.types.exceptions import ValidationError
from review_agent.types.models import ProjectCreate, ProjectUpdate
from review_agent.types.orm import ProjectModel

router = APIRouter(tags=["projects"])

_WEBHOOK_INACTIVE_HOURS = 24

# UUID 正则：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _validate_project_name(name: str) -> None:
    """校验项目名称，拒绝纯 UUID 格式的名称。"""
    if _UUID_PATTERN.match(name.strip()):
        msg = f"项目名称不能是 UUID 格式: {name}"
        raise ValidationError(msg)


async def _get_review_branches(project: ProjectModel) -> list[str]:
    """从 project.settings JSON 中读取 review_branches。"""
    if not project.settings:
        return ["*"]
    try:
        settings = json.loads(project.settings)
        branches = settings.get("review_branches")
        if isinstance(branches, list) and branches:
            return [str(b) for b in branches]
    except (json.JSONDecodeError, TypeError):
        pass
    return ["*"]


async def _format_project(
    project: ProjectModel,
    webhook_last_event_at: datetime | None,
    db: AsyncSession | None = None,
) -> dict[str, Any]:
    """统一格式化项目响应。"""
    webhook_enabled = project.webhook_enabled
    if not webhook_enabled:
        webhook_status = "disconnected"
    elif webhook_last_event_at is None:
        webhook_status = "connected"  # webhook_enabled=True → GitHub API 已验证
    elif (datetime.now(UTC) - webhook_last_event_at) > timedelta(hours=_WEBHOOK_INACTIVE_HOURS):
        webhook_status = "inactive"
    else:
        webhook_status = "connected"

    pr_count = 0
    review_count = 0
    latest_score: int | None = None
    recent_review_dt: datetime | None = None
    if db is not None:
        pr_repo = PullRequestRepo(db)
        review_repo = ReviewRepo(db)
        pr_count = await pr_repo.count(filters={"project_id": project.id})
        review_count = await review_repo.count(filters={"project_id": project.id})
        latest_review = await review_repo.get_latest(project.id)
        if latest_review:
            latest_score = latest_review.score
            recent_review_dt = latest_review.create_time

    # 活跃状态
    status: str = "dormant" if review_count == 0 else "inactive"
    active_days: int | None = None
    if recent_review_dt is not None:
        days_since = (datetime.now(UTC) - recent_review_dt).days
        active_days = max(0, days_since)
        status = "active" if days_since <= 7 else "inactive"

    # 从 settings 读取分支过滤配置
    review_branches = await _get_review_branches(project)

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
            recent_review_dt.isoformat() if recent_review_dt
            else (project.update_time.isoformat() if project.update_time else None)
        ),
        "pr_count": pr_count,
        "review_count": review_count,
        "latest_score": latest_score,
        "status": status,
        "active_days": active_days,
        "review_branches": review_branches,
    }


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """注册新项目。"""
    _validate_project_name(body.name)
    repo = ProjectRepo(db)
    project = await repo.create(
        name=body.name,
        platform=body.platform.value,
        repo_url=normalize_repo_url(body.repo_url),
        webhook_enabled=False,
    )
    return await _format_project(project, webhook_last_event_at=None, db=db)


@router.get("/projects")
async def list_projects(
    platform: str | None = Query(None, pattern="^(github|gitlab|gitee)$"),
    search: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目列表。"""
    webhook_repo = WebhookEventRepo(db)
    stmt = select(ProjectModel).where(ProjectModel.is_deleted.is_(False))
    if platform:
        stmt = stmt.where(ProjectModel.platform == platform)
    if search:
        stmt = stmt.where(
            ProjectModel.name.ilike(f"%{search}%") |
            ProjectModel.repo_url.ilike(f"%{search}%")
        )

    total_result = await db.execute(stmt)
    all_matching = total_result.scalars().all()
    total = len(all_matching)

    stmt = stmt.order_by(ProjectModel.create_time.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size)
    rows = await db.execute(stmt)
    items = rows.scalars().all()

    items_out: list[dict[str, Any]] = []
    for p in items:
        last_event = await webhook_repo.last_event_time(p.id)
        items_out.append(await _format_project(p, last_event, db))

    return {"items": items_out, "total": total, "page": page, "page_size": page_size}


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
            "id": project_id, "name": "", "platform": "", "repo_url": "",
            "webhook_enabled": False, "webhook_status": "disconnected",
            "webhook_last_event_at": None, "recent_review_time": None,
            "pr_count": 0, "review_count": 0,
            "latest_score": None, "status": "dormant", "active_days": None,
            "webhook_events": [],
        }

    last_event = await webhook_repo.last_event_time(project_id)
    result = await _format_project(project, last_event, db)
    result["webhook_events"] = []
    return result


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: str,
    body: ProjectUpdate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新项目配置。"""
    repo = ProjectRepo(db)
    if body.name is not None:
        _validate_project_name(body.name)
        await repo.update(project_id, name=body.name)
    if body.review_branches is not None:
        await repo.update_settings(project_id, review_branches=body.review_branches)
    # 返回完整项目信息，前端可立即使用
    project = await repo.get_active(project_id)
    if project:
        webhook_repo = WebhookEventRepo(db)
        last_event = await webhook_repo.last_event_time(project_id)
        return await _format_project(project, last_event, db)
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


def _extract_repo_name_from_url(repo_url: str) -> str | None:
    """从 repo_url 提取 owner/repo 格式的仓库名。"""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:]).removesuffix(".git")
    return None


@router.post("/projects/{project_id}/webhook/test")
async def test_webhook_connection(
    project_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """测试项目 Webhook 连接状态（主动向 GitHub 查询并发送 Ping）。"""
    repo = ProjectRepo(db)
    project = await repo.get_active(project_id)
    if not project:
        return {"found": False, "error": "project_not_found"}

    repo_name = _extract_repo_name_from_url(project.repo_url)
    if not repo_name:
        return {"found": False, "error": "invalid_repo_url"}

    webhook_url = f"{get_settings().public_url}/webhook/{project.platform}"
    git = GitHubProvider()
    result = await git.check_webhook(repo_name, webhook_url)

    if result["found"]:
        if not project.webhook_enabled:
            project.webhook_enabled = True
            await db.flush()
        result["status"] = "connected"
        if result.get("hook_id"):
            result["ping_sent"] = await git.send_webhook_ping(repo_name, result["hook_id"])
    else:
        if project.webhook_enabled:
            project.webhook_enabled = False
            await db.flush()
        result["status"] = "disconnected"

    return result
