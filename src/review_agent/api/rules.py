"""评审规则管理 API 端点。

RuleModel CRUD：
- GET    /rules              — 规则列表（分页 + 过滤）
- POST   /rules              — 创建规则
- PATCH  /rules/{id}         — 更新规则
- DELETE /rules/{id}         — 删除（软删除）
- POST   /rules/{id}/re-embed       — 单条规则重新嵌入
- POST   /rules/re-embed-all        — 全量规则重新嵌入
- POST   /rules/{id}/test-embedding — 测试规则匹配
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.dependencies.auth import require_role
from review_agent.config.database import get_session
from review_agent.service.embedding import EmbeddingService
from review_agent.service.rule_handler import (
    count_rules as _count_rules,
)
from review_agent.service.rule_handler import (
    create_rule as _create_rule_handler,
)
from review_agent.service.rule_handler import (
    delete_rule as _delete_rule_handler,
)
from review_agent.service.rule_handler import (
    get_active_rule as _get_active_rule,
)
from review_agent.service.rule_handler import (
    list_active_rules as _list_active_rules,
)
from review_agent.service.rule_handler import (
    list_rules as _list_rules_query,
)
from review_agent.service.rule_handler import (
    update_rule as _update_rule_handler,
)
from review_agent.types.enums import UserRole

logger = logging.getLogger(__name__)
router = APIRouter(tags=["rules"])  # TODO: 登录页面未就绪，暂时不启用 JWT 认证


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
    filters: dict[str, Any] = {}
    if language:
        filters["languages"] = language
    if category:
        filters["category"] = category
    if is_active is not None:
        filters["is_active"] = is_active

    items = await _list_rules_query(
        db,
        skip=(page - 1) * page_size,
        limit=page_size,
        filters=filters,
    )
    total = await _count_rules(db, filters=filters)

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
                "embedding_status": r.embedding is not None,
                "create_time": r.create_time.isoformat() if r.create_time else None,
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post(
    "/rules", status_code=201, dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))]
)
async def create_rule(
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """创建评审规则。"""
    rule = await _create_rule_handler(
        db,
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


@router.patch("/rules/{rule_id}", dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))])
async def update_rule(
    rule_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新评审规则。"""
    rule = await _get_active_rule(db, rule_id)
    if rule is None:
        return {"id": rule_id, "status": "not_found"}

    update_fields: dict[str, Any] = {}
    for field in ("name", "content", "category", "severity", "languages", "tags", "is_active"):
        if field in body:
            update_fields[field] = body[field]

    await _update_rule_handler(db, rule_id, **update_fields)
    # 规则内容变更后清除缓存
    EmbeddingService().cache_invalidate(rule_id)
    return {"id": rule_id, "status": "updated"}


@router.delete("/rules/{rule_id}", dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))])
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """删除评审规则（软删除）。"""
    await _delete_rule_handler(db, rule_id)
    EmbeddingService().cache_invalidate(rule_id)
    return {"id": rule_id, "status": "deleted"}


@router.post(
    "/rules/{rule_id}/re-embed", dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))]
)
async def re_embed_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """重新计算单条规则的嵌入向量。

    调用外部嵌入 API 生成向量，持久化到数据库。
    """
    rule = await _get_active_rule(db, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="规则不存在")

    embedder = EmbeddingService()
    embed_text = f"{rule.name}: {rule.content}"
    vector = await embedder.embed(embed_text)
    vector_json = str(vector)

    await _update_rule_handler(db, rule_id, embedding=vector_json)
    embedder.cache_set(rule_id, vector)

    return {
        "id": rule_id,
        "embedding_status": True,
        "vector_dim": len(vector),
    }


@router.post("/rules/re-embed-all", dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))])
async def re_embed_all_rules(
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """重新计算所有活跃规则的嵌入向量。"""
    rules = await _list_active_rules(db)
    embedder = EmbeddingService()
    updated = 0

    for rule in rules:
        try:
            embed_text = f"{rule.name}: {rule.content}"
            vector = await embedder.embed(embed_text)
            vector_json = str(vector)
            await _update_rule_handler(db, rule.id, embedding=vector_json)
            embedder.cache_set(rule.id, vector)
            updated += 1
        except Exception as exc:
            logger.warning("Failed to embed rule %s: %s", rule.id, exc)
            continue

    return {
        "total": len(rules),
        "updated": updated,
    }


@router.post(
    "/rules/{rule_id}/test-embedding", dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))]
)
async def test_rule_embedding(
    rule_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """测试规则匹配：传入代码片段，返回相似度得分。

    Request body:
        ``{"code": "def foo():\\n    pass"}``
    """
    rule = await _get_active_rule(db, rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail="规则不存在")

    code = body.get("code", "")
    if not code.strip():
        raise HTTPException(status_code=400, detail="code 不能为空")

    embedder = EmbeddingService()
    code_vec = await embedder.embed(code[:500])
    rule_vec: list[float] | None = embedder.cache_get(rule_id)

    if rule_vec is None and rule.embedding:
        import contextlib
        import json

        with contextlib.suppress(json.JSONDecodeError, TypeError):
            rule_vec = json.loads(rule.embedding)

    if rule_vec is None:
        return {
            "id": rule_id,
            "similarity": None,
            "message": "该规则尚未计算嵌入向量，请先调用 re-embed",
        }

    similarity = EmbeddingService.cosine_similarity(code_vec, rule_vec)
    return {
        "id": rule_id,
        "similarity": round(similarity, 4),
        "name": rule.name,
    }
