"""项目、评审、PR/Commit 等核心业务 ORM 模型。"""
# mypy: ignore-errors

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from review_agent.types.enums import (
    DetectorType,
    FindingCategory,
    FindingSeverity,
    Platform,
    PRState,
    ReviewStatus,
    SnapshotPeriod,
    TriggerType,
)
from review_agent.types.orm_base import Base, SoftDeleteMixin, TimestampMixin

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
        UniqueConstraint("project_id", "pr_number", "head_sha", name="uq_review_project_pr_sha"),
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
    trigger_type: Mapped[TriggerType] = mapped_column(
        String(32), default=TriggerType.MANUAL, nullable=False
    )
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    files_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commits_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_files: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # relationships
    project: Mapped[ProjectModel] = relationship("ProjectModel", back_populates="reviews")
    findings: Mapped[list[FindingModel]] = relationship(
        "FindingModel", back_populates="review", cascade="all, delete-orphan"
    )
    review_functions: Mapped[list[ReviewFunctionModel]] = relationship(
        "ReviewFunctionModel", back_populates="review", cascade="all, delete-orphan"
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
    detected_by: Mapped[DetectorType] = mapped_column(
        String(32), default=DetectorType.AI, nullable=False
    )
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
    max_severity: Mapped[FindingSeverity | None] = mapped_column(
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
    state: Mapped[PRState] = mapped_column(String(32), default=PRState.OPEN, nullable=False)
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


# ── QualitySnapshot ────────────────────────────────────────


class QualitySnapshot(Base, TimestampMixin):
    """代码质量快照（预聚合数据，加速仪表盘展示）。"""

    __tablename__ = "quality_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[SnapshotPeriod] = mapped_column(
        String(16), nullable=False
    )  # daily / weekly / monthly
    avg_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_reviews: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_findings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    critical_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    info_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
