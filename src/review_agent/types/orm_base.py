"""SQLAlchemy 声明式基类和通用 Mixin。

这些类是项目所有 ORM 模型的基础设施。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """声明式基类。"""


class TimestampMixin:
    """时间戳 Mixin，提供 create_time 和 update_time。

    create_time 仅在 INSERT 时写入，禁止更新。
    update_time 在每次 UPDATE 时自动刷新。
    """

    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


class SoftDeleteMixin:
    """软删除 Mixin。"""

    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
