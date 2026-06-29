"""规则管理服务处理。

封装 RuleRepo 的 CRUD 操作，供 api/rules.py 使用。
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.rule import RuleRepo
from review_agent.types.enums import FindingCategory, FindingSeverity
from review_agent.types.orm import RuleModel


async def list_rules(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 20,
    filters: dict[str, Any] | None = None,
) -> list[RuleModel]:
    """分页列出规则。

    Args:
        db: Database session.
        skip: 分页偏移。
        limit: 每页条数。
        filters: 过滤条件。

    Returns:
        规则列表。
    """
    repo = RuleRepo(db)
    return await repo.list(skip=skip, limit=limit, filters=filters)  # type: ignore[no-any-return]


async def count_rules(
    db: AsyncSession,
    *,
    filters: dict[str, Any] | None = None,
) -> int:
    """统计规则数量。

    Args:
        db: Database session.
        filters: 过滤条件。

    Returns:
        规则数量。
    """
    repo = RuleRepo(db)
    return await repo.count(filters=filters)  # type: ignore[no-any-return]


async def create_rule(
    db: AsyncSession,
    *,
    name: str,
    content: str,
    category: FindingCategory = FindingCategory.STYLE,
    severity: FindingSeverity = FindingSeverity.WARNING,
    languages: str = "[]",
    tags: str = "[]",
) -> RuleModel:
    """创建新规则。

    Args:
        db: Database session.
        name: 规则名称。
        content: 规则内容。
        category: 类别。
        severity: 严重级别。
        languages: 适用语言 JSON 字符串。
        tags: 标签 JSON 字符串。

    Returns:
        创建的规则对象。
    """
    repo = RuleRepo(db)
    return await repo.create(
        name=name,
        content=content,
        category=category,
        severity=severity,
        languages=languages,
        tags=tags,
    )


async def get_active_rule(db: AsyncSession, rule_id: str) -> RuleModel | None:
    """获取未删除的规则。

    Args:
        db: Database session.
        rule_id: 规则 ID。

    Returns:
        RuleModel 或 None。
    """
    repo = RuleRepo(db)
    return await repo.get_active(rule_id)


async def update_rule(db: AsyncSession, rule_id: str, **kwargs: object) -> None:
    """更新规则字段。

    Args:
        db: Database session.
        rule_id: 规则 ID。
        **kwargs: 更新字段。
    """
    repo = RuleRepo(db)
    await repo.update(rule_id, **kwargs)


async def delete_rule(db: AsyncSession, rule_id: str) -> None:
    """软删除规则。

    Args:
        db: Database session.
        rule_id: 规则 ID。
    """
    repo = RuleRepo(db)
    await repo.soft_delete(rule_id)


async def list_active_rules(db: AsyncSession) -> list[RuleModel]:
    """列出所有启用的规则。

    Args:
        db: Database session.

    Returns:
        已启用规则列表。
    """
    repo = RuleRepo(db)
    return await repo.list_active()  # type: ignore[no-any-return]
