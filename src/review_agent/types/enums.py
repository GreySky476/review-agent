"""项目枚举常量定义。

数据库存储字符串值，代码中使用枚举类型保证类型安全。
"""

from __future__ import annotations

from enum import StrEnum


class Platform(StrEnum):
    """Git 托管平台类型。"""

    GITHUB = "github"
    GITLAB = "gitlab"
    GITEE = "gitee"
    GITHUB_ENTERPRISE = "github_enterprise"
    GITLAB_SELF_HOSTED = "gitlab_self_hosted"
    GITEA_SELF_HOSTED = "gitea_self_hosted"


class FindingSeverity(StrEnum):
    """Finding 严重性级别。"""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class FindingCategory(StrEnum):
    """Finding 类别。"""

    SECURITY = "security"
    BUG = "bug"
    PERFORMANCE = "performance"
    STYLE = "style"
    DEPENDENCY = "dependency"
    STRUCTURE = "structure"


class ReviewStatus(StrEnum):
    """评审任务状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"


class ChunkPath(StrEnum):
    """代码分块后的处理路径。"""

    DETAILED_REVIEW = "detailed_review"
    STRUCTURAL_REVIEW = "structural_review"


class EventAction(StrEnum):
    """Webhook 支持的 PR 事件动作。"""

    OPENED = "opened"
    SYNCHRONIZE = "synchronize"
    REOPENED = "reopened"


class UserRole(StrEnum):
    """管理后台用户角色。"""

    SUPER_ADMIN = "super_admin"
    PROJECT_ADMIN = "project_admin"
    VIEWER = "viewer"


class TriggerType(StrEnum):
    """评审触发方式。"""

    MANUAL = "manual"
    WEBHOOK = "webhook"
    SCHEDULED = "scheduled"


class DetectorType(StrEnum):
    """Finding 检测方式。"""

    AI = "ai"
    RULE = "rule"
    HUMAN = "human"
    LINTER = "linter"


class PRState(StrEnum):
    """Pull Request 状态。"""

    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class SnapshotPeriod(StrEnum):
    """质量快照统计周期。"""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class HealthStatus(StrEnum):
    """平台连通性健康状态。"""

    CONNECTED = "connected"
    ERROR = "error"
    PENDING = "pending"
    DISCONNECTED = "disconnected"


class ProjectHealth(StrEnum):
    """项目活跃度状态。"""

    ACTIVE = "active"
    DORMANT = "dormant"
    INACTIVE = "inactive"


class TeamRole(StrEnum):
    """团队成员角色。"""

    ADMIN = "admin"
    MEMBER = "member"


class NotificationEventType(StrEnum):
    """通知触发事件类型。"""

    REVIEW_COMPLETED = "review_completed"
    REVIEW_FAILED = "review_failed"
    NEW_FINDING = "new_finding"
    PR_OPENED = "pr_opened"


class NotificationChannel(StrEnum):
    """通知发送渠道。"""

    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"


class NotificationStatus(StrEnum):
    """通知发送状态。"""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
