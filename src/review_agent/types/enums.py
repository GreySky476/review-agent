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
