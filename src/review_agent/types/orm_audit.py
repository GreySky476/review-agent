"""审计日志和通知相关 ORM 模型。"""
# mypy: ignore-errors

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from review_agent.types.enums import NotificationChannel, NotificationEventType, NotificationStatus
from review_agent.types.orm_base import Base, SoftDeleteMixin, TimestampMixin


class AuditLogModel(Base, TimestampMixin):
    """操作审计日志。"""

    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True, index=True
    )
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)


class NotificationRuleModel(Base, TimestampMixin, SoftDeleteMixin):
    """通知规则配置。"""

    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    event_type: Mapped[NotificationEventType] = mapped_column(String(64), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(String(32), nullable=False)
    config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationLogModel(Base, TimestampMixin):
    """通知发送记录。"""

    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("notification_rules.id"), nullable=True
    )
    event_type: Mapped[NotificationEventType] = mapped_column(String(64), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[NotificationChannel] = mapped_column(String(32), nullable=False)
    status: Mapped[NotificationStatus] = mapped_column(
        String(32), default=NotificationStatus.PENDING, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
