"""评审、发现、PR/Commit、评论等核心 Pydantic 模型。"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from review_agent.types.enums import (
    FindingCategory,
    FindingSeverity,
    Platform,
    PRState,
    ReviewStatus,
    SnapshotPeriod,
)

# ── Review（评审记录） ────────────────────────────────


class Review(BaseModel):
    """一次 AI 评审任务的记录。"""

    model_config = ConfigDict(from_attributes=True)
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

    model_config = ConfigDict(from_attributes=True)
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

    model_config = ConfigDict(from_attributes=True)
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
    embedding_status: bool = False
    project_id: str | None = None


# ── PullRequest ──────────────────────────────────────────


class PullRequest(BaseModel):
    """PR（Pull Request / Merge Request）跟踪记录。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    pr_number: int
    title: str = ""
    author: str | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    state: PRState = PRState.OPEN
    merge_sha: str | None = None
    is_merged: bool = False
    merged_at: datetime | None = None
    platform: Platform
    create_time: datetime | None = None
    update_time: datetime | None = None


# ── Commit ────────────────────────────────────────────────


class Commit(BaseModel):
    """提交记录（含纯分支提交）。"""

    model_config = ConfigDict(from_attributes=True)
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

    model_config = ConfigDict(from_attributes=True)
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

    model_config = ConfigDict(from_attributes=True)
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

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    snapshot_date: date
    period: SnapshotPeriod
    avg_score: float = 0.0
    total_reviews: int = 0
    total_findings: int = 0
    critical_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    create_time: datetime | None = None
    update_time: datetime | None = None
