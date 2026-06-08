"""Tests for ORM models."""

from review_agent.types.orm import (
    Base,
    FindingModel,
    ProjectModel,
    ReviewModel,
    RuleModel,
    UserModel,
    WebhookEventModel,
)


class TestORMModels:
    def test_all_tables_registered(self) -> None:
        """所有 ORM 模型应在 Base.metadata 中注册。"""
        table_names = {t.name for t in Base.metadata.tables.values()}
        expected = {"projects", "reviews", "findings", "rules", "users", "webhook_events"}
        assert expected.issubset(table_names)

    def test_project_model_columns(self) -> None:
        """ProjectModel 应包含必需字段。"""
        assert hasattr(ProjectModel, "name")
        assert hasattr(ProjectModel, "platform")
        assert hasattr(ProjectModel, "repo_url")
        assert hasattr(ProjectModel, "is_deleted")

    def test_project_has_timestamps(self) -> None:
        """ProjectModel 应有时间戳字段。"""
        assert hasattr(ProjectModel, "create_time")
        assert hasattr(ProjectModel, "update_time")

    def test_review_model_columns(self) -> None:
        """ReviewModel 应包含必需字段。"""
        assert hasattr(ReviewModel, "project_id")
        assert hasattr(ReviewModel, "pr_number")
        assert hasattr(ReviewModel, "head_sha")
        assert hasattr(ReviewModel, "status")

    def test_review_has_relationships(self) -> None:
        """ReviewModel 应有 project 和 findings 关联。"""
        assert hasattr(ReviewModel, "project")
        assert hasattr(ReviewModel, "findings")

    def test_finding_model_columns(self) -> None:
        """FindingModel 应包含必需字段。"""
        assert hasattr(FindingModel, "review_id")
        assert hasattr(FindingModel, "file_path")
        assert hasattr(FindingModel, "category")
        assert hasattr(FindingModel, "severity")
        assert hasattr(FindingModel, "title")
        assert hasattr(FindingModel, "description")
        assert hasattr(FindingModel, "suggestion")

    def test_rule_model_columns(self) -> None:
        """RuleModel 应包含必需字段。"""
        assert hasattr(RuleModel, "name")
        assert hasattr(RuleModel, "content")
        assert hasattr(RuleModel, "is_active")
        assert hasattr(RuleModel, "version")

    def test_user_model_columns(self) -> None:
        """UserModel 应包含必需字段。"""
        assert hasattr(UserModel, "username")
        assert hasattr(UserModel, "email")
        assert hasattr(UserModel, "role")
        assert hasattr(UserModel, "is_active")

    def test_webhook_event_columns(self) -> None:
        """WebhookEventModel 应包含必需字段。"""
        assert hasattr(WebhookEventModel, "event_id")
        assert hasattr(WebhookEventModel, "pr_number")
        assert hasattr(WebhookEventModel, "raw_payload")
        assert hasattr(WebhookEventModel, "is_processed")

    def test_soft_delete_mixin_applied(self) -> None:
        """ProjectModel/ReviewModel/FindingModel 应有软删除。"""
        assert hasattr(ProjectModel, "is_deleted")
        assert hasattr(ReviewModel, "is_deleted")
        assert hasattr(FindingModel, "is_deleted")
        assert hasattr(RuleModel, "is_deleted")
        assert hasattr(UserModel, "is_deleted")

    def test_webhook_events_no_soft_delete(self) -> None:
        """WebhookEventModel 不应有软删除（审计日志需保留全部）。"""
        assert not hasattr(WebhookEventModel, "is_deleted")
