"""Repository 基类 — 通用 CRUD 操作。

所有 Repository 继承自 BaseRepository，获得通用的：
- 创建/批量创建
- 按 ID 查询 / 条件查询
- 更新
- 软删除 / 硬删除
- 分页查询
"""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.types.exceptions import NotFoundError
from review_agent.types.orm import Base, SoftDeleteMixin

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository[ModelT]:
    """通用 Repository 基类。

    Args:
        ModelT: ORM 模型类。
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @property
    def _model(self) -> type[ModelT]:
        """子类必须定义此属性或重写。"""
        raise NotImplementedError

    # ── 创建 ──────────────────────────────────────────────

    async def create(self, **kwargs: Any) -> ModelT:
        """创建一条记录。

        Args:
            **kwargs: 模型字段键值对。

        Returns:
            已创建的 ORM 实例。
        """
        instance = self._model(**kwargs)
        self._db.add(instance)
        await self._db.flush()
        return instance

    async def create_many(self, items: list[dict[str, Any]]) -> list[ModelT]:
        """批量创建记录。

        Args:
            items: 模型字段字典列表。

        Returns:
            已创建的 ORM 实例列表。
        """
        instances = [self._model(**item) for item in items]
        self._db.add_all(instances)
        await self._db.flush()
        return instances

    # ── 查询 ──────────────────────────────────────────────

    async def get(self, id: str) -> ModelT | None:
        """按 ID 查询（不过滤软删除）。

        Args:
            id: UUID 字符串。

        Returns:
            ORM 实例或 None。
        """
        return await self._db.get(self._model, id)

    async def get_or_raise(self, id: str) -> ModelT:
        """按 ID 查询，不存在时抛出 NotFoundError。

        Args:
            id: UUID 字符串。

        Returns:
            ORM 实例。

        Raises:
            NotFoundError: 未找到时抛出。
        """
        instance = await self.get(id)
        if instance is None:
            msg = f"{self._model.__name__} with id={id} not found"
            raise NotFoundError(msg)
        return instance

    async def get_active(self, id: str) -> ModelT | None:
        """按 ID 查询存活记录（is_deleted=False）。

        Args:
            id: UUID 字符串。

        Returns:
            ORM 实例或 None。
        """
        stmt = select(self._model).where(self._model.id == id)  # type: ignore[attr-defined]
        if issubclass(self._model, SoftDeleteMixin):
            stmt = stmt.where(self._model.is_deleted.is_(False))  # type: ignore[attr-defined]
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(
        self,
        *,
        skip: int = 0,
        limit: int = 20,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        include_deleted: bool = False,
    ) -> list[ModelT]:
        """分页查询列表。

        Args:
            skip: 偏移量。
            limit: 每页数量，最大 100。
            filters: 等值过滤条件字典。
            order_by: 排序字段名（默认使用 create_time 降序）。
            include_deleted: 是否包含软删除记录。

        Returns:
            ORM 实例列表。
        """
        limit = min(limit, 100)
        stmt = select(self._model)

        if not include_deleted and issubclass(self._model, SoftDeleteMixin):
            stmt = stmt.where(self._model.is_deleted.is_(False))  # type: ignore[attr-defined]

        if filters:
            for key, value in filters.items():
                column = getattr(self._model, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)

        if order_by:
            column = getattr(self._model, order_by, None)
            if column is not None:
                stmt = stmt.order_by(column.desc())
        else:
            if hasattr(self._model, "create_time"):
                stmt = stmt.order_by(self._model.create_time.desc())  # type: ignore[attr-defined]

        stmt = stmt.offset(skip).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        """计数查询。

        Args:
            filters: 等值过滤条件字典。

        Returns:
            记录总数。
        """
        stmt = select(self._model)

        if issubclass(self._model, SoftDeleteMixin):
            stmt = stmt.where(self._model.is_deleted.is_(False))  # type: ignore[attr-defined]

        if filters:
            for key, value in filters.items():
                column = getattr(self._model, key, None)
                if column is not None:
                    stmt = stmt.where(column == value)

        result = await self._db.execute(stmt)
        return len(result.scalars().all())

    # ── 更新 ──────────────────────────────────────────────

    async def update(self, id: str, **kwargs: Any) -> ModelT:
        """更新记录，返回更新后的实例。

        Args:
            id: UUID 字符串。
            **kwargs: 要更新的字段。

        Returns:
            更新后的 ORM 实例。

        Raises:
            NotFoundError: 未找到时抛出。
        """
        instance = await self.get_or_raise(id)
        for key, value in kwargs.items():
            if hasattr(instance, key):
                setattr(instance, key, value)
        await self._db.flush()
        return instance

    # ── 删除 ──────────────────────────────────────────────

    async def soft_delete(self, id: str) -> None:
        """软删除（设置 is_deleted=True）。

        Args:
            id: UUID 字符串。

        Raises:
            NotFoundError: 未找到时抛出。
        """
        instance = await self.get_or_raise(id)
        if hasattr(instance, "is_deleted"):
            instance.is_deleted = True
            await self._db.flush()

    async def hard_delete(self, id: str) -> None:
        """硬删除（从数据库移除）。

        Args:
            id: UUID 字符串。
        """
        stmt = delete(self._model).where(self._model.id == id)  # type: ignore[attr-defined]
        await self._db.execute(stmt)
        await self._db.flush()
