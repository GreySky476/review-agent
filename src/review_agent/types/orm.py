"""SQLAlchemy ORM 模型定义。

遵循数据规范（§6）：
- 所有表包含 UUID 主键、create_time（不可更新）、update_time（自动刷新）
- 枚举字段存储为字符串
- 关键实体支持软删除（is_deleted）
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from review_agent.types.enums import (
    EventAction,
    FindingCategory,
    FindingSeverity,
    Platform,
    ReviewStatus,
    UserRole,
)


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


# ── Project ──────────────────────────────────────────────


class ProjectModel(Base, TimestampMixin, SoftDeleteMixin):
    """在系统内注册的一个代码仓库。"""

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[Platform] = mapped_column(String(32), nullable=False)
    repo_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(255), default="main", nullable=False)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id"), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)
    webhook_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_activity_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    settings: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON

    # relationships
    reviews: Mapped[list[ReviewModel]] = relationship(
        "ReviewModel", back_populates="project", cascade="all, delete-orphan"
    )


# ── Review ───────────────────────────────────────────────


class ReviewModel(Base, TimestampMixin, SoftDeleteMixin):
    """一次 AI 评审任务的记录。"""

    __tablename__ = "reviews"
    __table_args__ = (
        Index("ix_reviews_project_head_sha", "project_id", "head_sha"),
        Index("ix_reviews_project_pr", "project_id", "pr_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), nullable=False)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pr_title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    head_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[ReviewStatus] = mapped_column(
        String(32), default=ReviewStatus.PENDING, nullable=False
    )
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    findings_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    report_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    trigger_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    files_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commits_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_files: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    # ── 监控指标（Phase 2：汇总统计） ──
    summary_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ai_call_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pipeline_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    file_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # relationships
    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="reviews")
    findings: Mapped[list[FindingModel]] = relationship(
        "FindingModel", back_populates="review", cascade="all, delete-orphan"
    )
    review_functions: Mapped[list[ReviewFunctionModel]] = relationship(
        "ReviewFunctionModel", back_populates="review", cascade="all, delete-orphan"
    )
    ai_calls: Mapped[list[ReviewAICallModel]] = relationship(
        "ReviewAICallModel", back_populates="review", cascade="all, delete-orphan"
    )


# ── Finding ──────────────────────────────────────────────


class FindingModel(Base, TimestampMixin, SoftDeleteMixin):
    """评审发现的具体问题。"""

    __tablename__ = "findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(String(36), ForeignKey("reviews.id"), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    category: Mapped[FindingCategory] = mapped_column(String(32), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    suggestion: Mapped[str] = mapped_column(Text, nullable=False)
    rule_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    detected_by: Mapped[str] = mapped_column(String(32), default="ai", nullable=False)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_fixed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fixed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fixed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # relationships
    review: Mapped[ReviewModel] = relationship("ReviewModel", back_populates="findings")


# ── ReviewFunction ─────────────────────────────────────


class ReviewFunctionModel(Base, TimestampMixin):
    """函数级评审跟踪：记录每个函数在每次评审中的状态。"""

    __tablename__ = "review_functions"
    __table_args__ = (
        UniqueConstraint(
            "review_id", "file_path", "function_name", "start_line", name="uq_review_func"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    function_name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_line: Mapped[int] = mapped_column(Integer, nullable=False)
    end_line: Mapped[int] = mapped_column(Integer, nullable=False)
    sha: Mapped[str] = mapped_column(String(64), nullable=False)
    max_severity: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # NULL=clean, "critical"/"warning"/"info"
    finding_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    review: Mapped[ReviewModel] = relationship("ReviewModel", back_populates="review_functions")


# ── Rule ─────────────────────────────────────────────────


class RuleModel(Base, TimestampMixin, SoftDeleteMixin):
    """企业自定义的代码审查规范条目。"""

    __tablename__ = "rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[FindingCategory] = mapped_column(String(32), nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(String(32), nullable=False)
    languages: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    tags: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    embedding: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    project_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("projects.id"),
        nullable=True,
    )


# ── User ─────────────────────────────────────────────────


class UserModel(Base, TimestampMixin, SoftDeleteMixin):
    """管理后台用户。"""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    role: Mapped[UserRole] = mapped_column(String(32), default=UserRole.VIEWER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    team_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("teams.id"), nullable=True)


# ── WebhookEvent ─────────────────────────────────────────


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


# ── PullRequest ────────────────────────────────────────────


class PullRequestModel(Base, TimestampMixin):
    """PR（Pull Request / Merge Request）跟踪记录。"""

    __tablename__ = "pull_requests"
    __table_args__ = (UniqueConstraint("project_id", "pr_number", name="uq_pr_project_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    state: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    merge_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_merged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    platform: Mapped[Platform] = mapped_column(String(32), nullable=False)
    last_reviewed_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_review_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("reviews.id"), nullable=True
    )
    pr_comment_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)


# ── Commit ─────────────────────────────────────────────────


class CommitModel(Base, TimestampMixin):
    """提交记录（含纯分支提交）。"""

    __tablename__ = "commits"
    __table_args__ = (UniqueConstraint("project_id", "sha", name="uq_commit_project_sha"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    additions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    deletions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    files_changed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )


# ── ReviewAICall ──────────────────────────────────────────


class ReviewAICallModel(Base):
    """AI 调用明细 — 每次 LLM 请求的 token 消耗和耗时。"""

    __tablename__ = "review_ai_calls"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id"), nullable=False, index=True
    )
    batch_idx: Mapped[int] = mapped_column(Integer, nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    # relationships
    review: Mapped[ReviewModel] = relationship("ReviewModel", back_populates="ai_calls")


# ── Comment ────────────────────────────────────────────────


class CommentModel(Base, TimestampMixin):
    """对 Finding 的反馈/讨论评论。"""

    __tablename__ = "comments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    review_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("reviews.id"), nullable=False, index=True
    )
    finding_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("findings.id"), nullable=True
    )
    author: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)


# ── ReviewErrorLog ─────────────────────────────────────────


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


# ── QualitySnapshot ────────────────────────────────────────


class QualitySnapshot(Base, TimestampMixin):
    """代码质量快照（预聚合数据，加速仪表盘展示）。"""

    __tablename__ = "quality_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False)  # daily / weekly / monthly
    avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    info_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# ── PlatformHealth ────────────────────────────────────────────
class PlatformHealthModel(Base, TimestampMixin):
    __tablename__ = "platform_health"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    platform: Mapped[Platform] = mapped_column(String(32), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


# ── Team ────────────────────────────────────────────────────────


class TeamModel(Base, TimestampMixin, SoftDeleteMixin):
    """团队/组织分组。"""

    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=True
    )

    # relationships
    members: Mapped[list[TeamMemberModel]] = relationship(
        "TeamMemberModel", back_populates="team", cascade="all, delete-orphan"
    )


class TeamMemberModel(Base, TimestampMixin):
    """团队成员关系。"""

    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    team_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("teams.id"), nullable=False, index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)

    # relationships
    team: Mapped[TeamModel] = relationship("TeamModel", back_populates="members")


# ── AuditLog ────────────────────────────────────────────────────


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


# ── UserSession ────────────────────────────────────────────────


class UserSessionModel(Base, TimestampMixin):
    """用户登录会话（JWT 管理）。"""

    __tablename__ = "user_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


# ── Notification ────────────────────────────────────────────────


class NotificationRuleModel(Base, TimestampMixin, SoftDeleteMixin):
    """通知规则配置。"""

    __tablename__ = "notification_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=True
    )
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[str] = mapped_column(Text, default="{}", nullable=False)  # JSON
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class NotificationLogModel(Base, TimestampMixin):
    """通知发送记录。"""

    __tablename__ = "notification_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rule_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("notification_rules.id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    channel: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
