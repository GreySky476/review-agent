"""平台相关 ORM 模型（Webhook、健康检查、错误日志）。"""
# mypy: ignore-errors

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from review_agent.types.enums import EventAction, HealthStatus, Platform
from review_agent.types.orm_base import Base, TimestampMixin


class WebhookEventModel(Base, TimestampMixin):
    """Webhook 原始事件日志（用于去重和审计）。"""

    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    platform: Mapped[Platform] = mapped_column(String(32), nullable=False)
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    action: Mapped[EventAction] = mapped_column(String(32), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    repo_full_name: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    response_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PlatformHealthModel(Base, TimestampMixin):
    """平台健康状态记录。"""

    __tablename__ = "platform_health"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    platform: Mapped[Platform] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[HealthStatus] = mapped_column(
        String(32), default=HealthStatus.PENDING, nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ReviewErrorLog(Base, TimestampMixin):
    """评审流水线错误日志。"""

    __tablename__ = "review_errors"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True
    )
    review_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reviews.id"), nullable=True
    )
    error_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    error_message: Mapped[str] = mapped_column(Text, nullable=False)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovered: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
