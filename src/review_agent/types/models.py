"""Pydantic 数据模型定义。

这些模型用于 API 请求/响应序列化和内部数据传输。
ORM 模型定义在 `types/orm.py`。
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from review_agent.types.enums import (
    EventAction,
    FindingCategory,
    FindingSeverity,
    Platform,
    ReviewStatus,
    UserRole,
)

# ── Project（注册的仓库项目） ──────────────────────────


class Project(BaseModel):
    """在系统内注册的一个代码仓库。"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    platform: Platform
    repo_url: str
    webhook_secret: str | None = None
    webhook_enabled: bool = True
    is_deleted: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


class ProjectCreate(BaseModel):
    """创建项目请求。"""

    name: str
    platform: Platform
    repo_url: str


class ProjectUpdate(BaseModel):
    """更新项目请求（所有字段可选）。"""

    name: str | None = None
    webhook_enabled: bool | None = None
    review_branches: list[str] | None = None


# ── Review（评审记录） ────────────────────────────────


class Review(BaseModel):
    """一次 AI 评审任务的记录。"""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    pr_number: int
    pr_title: str
    head_sha: str
    status: ReviewStatus = ReviewStatus.PENDING
    score: int | None = Field(default=None, ge=0, le=100)
    findings_count: int = 0
    task_id: str | None = None
    report_url: str | None = None
    is_deleted: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


class ReviewCreate(BaseModel):
    """手动触发评审的请求。"""

    project_id: UUID
    pr_number: int
    pr_title: str = ""
    head_sha: str


# ── Finding（评审发现的具体问题） ────────────────────


class Finding(BaseModel):
    """一次评审发现的具体问题。"""

    id: UUID = Field(default_factory=uuid4)
    review_id: UUID
    file_path: str
    line_start: int | None = None
    line_end: int | None = None
    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    suggestion: str
    rule_id: UUID | None = None
    is_valid: bool = True
    is_deleted: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── Rule（规范/规则，存储于知识库） ────────────────


class Rule(BaseModel):
    """企业自定义的代码审查规范条目。"""

    id: UUID = Field(default_factory=uuid4)
    name: str
    content: str
    category: FindingCategory
    severity: FindingSeverity
    languages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    version: int = 1
    is_active: bool = True
    is_deleted: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── User（管理后台用户） ──────────────────────────────


class User(BaseModel):
    """管理后台用户。"""

    id: UUID = Field(default_factory=uuid4)
    username: str
    email: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    is_deleted: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── Event（Webhook 原始事件日志） ────────────────────


class WebhookEvent(BaseModel):
    """Webhook 原始事件记录。"""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    platform: Platform
    event_id: str
    action: EventAction
    pr_number: int
    raw_payload: str
    is_processed: bool = False
    create_time: datetime | None = None


# ── PullRequest ──────────────────────────────────────────


class PullRequest(BaseModel):
    """PR（Pull Request / Merge Request）跟踪记录。"""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    pr_number: int
    title: str = ""
    author: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    state: str = "open"
    merge_sha: str | None = None
    is_merged: bool = False
    merged_at: datetime | None = None
    platform: Platform
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── Commit ────────────────────────────────────────────────


class Commit(BaseModel):
    """提交记录（含纯分支提交）。"""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    sha: str
    author: str | None = None
    message: str | None = None
    branch: str | None = None
    pr_number: int | None = None
    is_reviewed: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


class CommitReviewRequest(BaseModel):
    """通过 @mention 触发评审的请求。"""

    sha: str
    mention_user: str


# ── Comment ────────────────────────────────────────────────


class Comment(BaseModel):
    """对 Finding 的反馈/讨论评论。"""

    id: UUID = Field(default_factory=uuid4)
    review_id: UUID
    finding_id: UUID | None = None
    author: str
    content: str
    action: str | None = None
    create_time: datetime | None = None
    update_time: datetime | None = None


class CommentCreate(BaseModel):
    """创建评论请求。"""

    finding_id: str | None = None
    author: str
    content: str
    action: str | None = None


# ── ReviewErrorLog ──────────────────────────────────────


class ReviewErrorLog(BaseModel):
    """评审流水线错误日志。"""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID | None = None
    review_id: UUID | None = None
    error_type: str
    error_message: str
    error_detail: str | None = None
    recovered: bool = False
    frequency: int = 1
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── QualitySnapshot ────────────────────────────────────────


class QualitySnapshot(BaseModel):
    """代码质量快照（预聚合数据）。"""

    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    snapshot_date: date
    period: str
    avg_score: float = 0.0
    total_reviews: int = 0
    total_findings: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── Dashboard Stats ────────────────────────────────────────


class DashboardStats(BaseModel):
    """仪表盘统计信息。"""

    total_projects: int = 0
    total_reviews_today: int = 0
    average_score: float = 0.0
    pending_errors: int = 0
    finding_distribution: dict[str, int] = Field(default_factory=dict)


class TrendDataPoint(BaseModel):
    """质量趋势数据点。"""

    date: str
    avg_score: float
    total_reviews: int
    critical: int
    warning: int
    info: int


class EnterpriseDashboard(BaseModel):
    """企业级仪表盘执行摘要。"""

    total_projects: int = 0
    total_projects_change: float = 0.0  # 较上周变化百分比
    reviews_this_week: int = 0
    reviews_week_change: float = 0.0
    avg_score: float = 0.0
    avg_score_change: float = 0.0
    error_rate: float = 0.0  # completed_with_errors / total
    error_rate_change: float = 0.0
    review_coverage: float = 0.0  # 有评审的 commit 占比
    reviews_by_status: dict[str, int] = Field(default_factory=dict)
    top_findings: list[dict[str, Any]] = Field(default_factory=list)


class ProjectHealthItem(BaseModel):
    """项目健康矩阵条目。"""

    project_id: str
    project_name: str
    platform: str
    latest_score: int | None = None
    score_change: int | None = None  # 较 7 天前变化
    health: str = "dormant"  # active / warning / critical / dormant
    review_count_7d: int = 0
    error_count_7d: int = 0
    last_review_at: str | None = None


class RecentReviewItem(BaseModel):
    """最近评审活动条目。"""

    review_id: str
    project_name: str
    project_id: str
    pr_title: str
    branch: str | None = None
    status: str
    score: int | None = None
    head_sha: str
    duration_seconds: int | None = None
    created_at: str | None = None


class ErrorStats(BaseModel):
    """错误聚合统计。"""

    error_type: str
    count: int
    last_occurred: datetime | None = None
