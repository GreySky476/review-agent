"""项目、Webhook事件、仪表盘相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from review_agent.types.enums import EventAction, Platform, ProjectHealth

# ── Project（注册的仓库项目） ──────────────────────────


class Project(BaseModel):
    """在系统内注册的一个代码仓库。"""

    model_config = ConfigDict(from_attributes=True)
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


# ── Event（Webhook 原始事件日志） ────────────────────


class WebhookEvent(BaseModel):
    """Webhook 原始事件记录。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    platform: Platform
    event_id: str
    action: EventAction
    pr_number: int
    raw_payload: str
    is_processed: bool = False
    create_time: datetime | None = None


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

    model_config = ConfigDict(from_attributes=True)
    project_id: str
    project_name: str
    platform: str
    latest_score: int | None = None
    score_change: int | None = None  # 较 7 天前变化
    health: ProjectHealth = ProjectHealth.DORMANT  # active / warning / critical / dormant
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
