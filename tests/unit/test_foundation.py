"""Tests for foundation module: exceptions and enums."""

from review_agent.types.enums import (
    ChunkPath,
    EventAction,
    FindingCategory,
    FindingSeverity,
    Platform,
    ReviewStatus,
    UserRole,
)
from review_agent.types.exceptions import (
    AIProviderError,
    ConfigError,
    DatabaseError,
    GitProviderError,
    NotFoundError,
    ReviewAgentError,
    ValidationError,
    WebhookValidationError,
)


class TestExceptions:
    """异常类型层次测试。"""

    def test_all_exceptions_inherit_from_base(self) -> None:
        """所有自定义异常应继承 ReviewAgentError。"""
        exceptions = [
            ConfigError,
            DatabaseError,
            AIProviderError,
            GitProviderError,
            WebhookValidationError,
            NotFoundError,
            ValidationError,
        ]
        for exc in exceptions:
            assert issubclass(exc, ReviewAgentError)

    def test_exception_can_be_raised_with_message(self) -> None:
        """异常可以携带消息。"""
        msg = "test error message"
        try:
            raise ConfigError(msg)
        except ConfigError as e:
            assert str(e) == msg

    def test_exception_captures_cause(self) -> None:
        """异常应能捕获原始异常作为原因。"""
        try:
            raise ValueError("original") from None
        except ValueError:
            try:
                raise DatabaseError("wrapped") from ValueError("original")
            except DatabaseError as e:
                assert e.__cause__ is not None


class TestEnums:
    """枚举常量测试。"""

    def test_platform_values(self) -> None:
        assert Platform.GITHUB == "github"
        assert Platform.GITLAB == "gitlab"
        assert Platform.GITEE == "gitee"

    def test_finding_severity_order(self) -> None:
        assert FindingSeverity.CRITICAL == "critical"
        assert FindingSeverity.WARNING == "warning"
        assert FindingSeverity.INFO == "info"

    def test_finding_category_values(self) -> None:
        assert FindingCategory.SECURITY == "security"
        assert FindingCategory.BUG == "bug"
        assert FindingCategory.PERFORMANCE == "performance"
        assert FindingCategory.STYLE == "style"
        assert FindingCategory.DEPENDENCY == "dependency"
        assert FindingCategory.STRUCTURE == "structure"

    def test_review_status_cycle(self) -> None:
        assert ReviewStatus.PENDING == "pending"
        assert ReviewStatus.RUNNING == "running"
        assert ReviewStatus.COMPLETED == "completed"
        assert ReviewStatus.FAILED == "failed"

    def test_chunk_path_values(self) -> None:
        assert ChunkPath.DETAILED_REVIEW == "detailed_review"
        assert ChunkPath.STRUCTURAL_REVIEW == "structural_review"

    def test_event_action_values(self) -> None:
        assert EventAction.OPENED == "opened"
        assert EventAction.SYNCHRONIZE == "synchronize"
        assert EventAction.REOPENED == "reopened"

    def test_user_role_values(self) -> None:
        assert UserRole.SUPER_ADMIN == "super_admin"
        assert UserRole.PROJECT_ADMIN == "project_admin"
        assert UserRole.VIEWER == "viewer"

    def test_all_enums_are_unique(self) -> None:
        """每个枚举类的值应唯一。"""

        for enum_cls in [Platform, FindingSeverity, FindingCategory, ReviewStatus, ChunkPath, EventAction, UserRole]:
            values = [e.value for e in enum_cls]
            assert len(values) == len(set(values)), f"{enum_cls.__name__} has duplicate values"
