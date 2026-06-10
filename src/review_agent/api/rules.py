"""评审规则管理 API 端点。

RuleModel CRUD：
- GET    /rules         — 规则列表（分页 + 过滤）
- POST   /rules         — 创建规则
- PATCH  /rules/{id}    — 更新规则
- DELETE /rules/{id}    — 删除（软删除）
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.rule import RuleRepo

router = APIRouter(tags=["rules"])


@router.get("/rules")
async def list_rules(
    language: str | None = Query(None),
    category: str | None = Query(None),
    is_active: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取评审规则列表。"""
    repo = RuleRepo(db)
    filters: dict[str, Any] = {}
    if language:
        filters["languages"] = language
    if category:
        filters["category"] = category
    if is_active is not None:
        filters["is_active"] = is_active

    items = await repo.list(
        skip=(page - 1) * page_size,
        limit=page_size,
        filters=filters,
    )
    total = await repo.count(filters=filters)

    return {
        "items": [
            {
                "id": r.id,
                "name": r.name,
                "content": r.content,
                "category": r.category,
                "severity": r.severity,
                "languages": r.languages,
                "tags": r.tags,
                "version": r.version,
                "is_active": r.is_active,
                "create_time": r.create_time.isoformat() if r.create_time else None,
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/rules", status_code=201)
async def create_rule(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """创建评审规则。"""
    repo = RuleRepo(db)
    rule = await repo.create(
        name=body.get("name", ""),
        content=body.get("content", ""),
        category=body.get("category", "style"),
        severity=body.get("severity", "warning"),
        languages=body.get("languages", "[]"),
        tags=body.get("tags", "[]"),
    )
    return {
        "id": rule.id,
        "status": "created",
    }


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新评审规则。"""
    repo = RuleRepo(db)
    rule = await repo.get_active(rule_id)
    if rule is None:
        return {"id": rule_id, "status": "not_found"}

    update_fields: dict[str, Any] = {}
    for field in ("name", "content", "category", "severity", "languages", "tags", "is_active"):
        if field in body:
            update_fields[field] = body[field]

    await repo.update(rule_id, **update_fields)
    return {"id": rule_id, "status": "updated"}


@router.delete("/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """删除评审规则（软删除）。"""
    repo = RuleRepo(db)
    await repo.soft_delete(rule_id)
    return {"id": rule_id, "status": "deleted"}
