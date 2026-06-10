"""Tests for Pydantic models."""

from uuid import UUID

from review_agent.types.enums import FindingCategory, FindingSeverity, Platform, ReviewStatus
from review_agent.types.models import (
    Finding,
    Project,
    ProjectCreate,
    Review,
    ReviewCreate,
    Rule,
    User,
    WebhookEvent,
)


class TestProjectModels:
    def test_project_defaults(self) -> None:
        """Project 应使用默认值。"""
        p = Project(name="test-repo", platform="github", repo_url="https://github.com/test/repo")
        assert isinstance(p.id, UUID)
        assert p.webhook_enabled is True
        assert p.is_deleted is False

    def test_project_create_valid(self) -> None:
        """ProjectCreate 应正确解析。"""
        pc = ProjectCreate(name="test", platform=Platform.GITLAB, repo_url="https://gitlab.com/test")
        assert pc.platform == Platform.GITLAB

    def test_project_update_optional(self) -> None:
        """ProjectUpdate 所有字段应为可选。"""
        from review_agent.types.models import ProjectUpdate
        pu = ProjectUpdate()
        assert pu.name is None
        assert pu.webhook_enabled is None
        pu = ProjectUpdate(name="new-name")
        assert pu.name == "new-name"


class TestReviewModels:
    def test_review_defaults(self) -> None:
        """Review 应使用默认状态。"""
        r = Review(project_id=UUID(int=1), pr_number=42, pr_title="Fix bug", head_sha="abc123")
        assert r.status == ReviewStatus.PENDING
        assert r.findings_count == 0
        assert r.is_deleted is False

    def test_review_create(self) -> None:
        """ReviewCreate 应正确解析。"""
        rc = ReviewCreate(project_id=UUID(int=2), pr_number=100, head_sha="def456")
        assert rc.pr_number == 100

    def test_review_score_range(self) -> None:
        """分数应在 0-100 范围。"""
        r = Review(project_id=UUID(int=1), pr_number=1, pr_title="fix", head_sha="x", score=85)
        assert r.score == 85


class TestFindingModel:
    def test_finding_defaults(self) -> None:
        """Finding 应使用默认值。"""
        f = Finding(
            review_id=UUID(int=1),
            file_path="src/main.py",
            category=FindingCategory.SECURITY,
            severity=FindingSeverity.CRITICAL,
            title="SQL Injection",
            description="User input used in raw query",
            suggestion="Use parameterized queries",
        )
        assert f.is_valid is True
        assert f.is_deleted is False
        assert f.rule_id is None

    def test_finding_with_optional_fields(self) -> None:
        """Finding 可选字段应正确设置。"""
        f = Finding(
            review_id=UUID(int=2),
            file_path="app.py",
            line_start=10,
            line_end=20,
            category=FindingCategory.PERFORMANCE,
            severity=FindingSeverity.WARNING,
            title="N+1 Query",
            description="Loop query inside for",
            suggestion="Use select_related",
            rule_id=UUID(int=99),
        )
        assert f.line_start == 10
        assert f.line_end == 20
        assert f.rule_id == UUID(int=99)


class TestRuleModel:
    def test_rule_defaults(self) -> None:
        """Rule 应使用默认值。"""
        r = Rule(
            name="No Eval",
            content="禁止使用 eval 执行用户输入",
            category=FindingCategory.SECURITY,
            severity=FindingSeverity.CRITICAL,
        )
        assert r.version == 1
        assert r.is_active is True
        assert r.languages == []

    def test_rule_with_tags(self) -> None:
        """Rule 可设置语言和标签。"""
        r = Rule(
            name="Test",
            content="content",
            category=FindingCategory.STYLE,
            severity=FindingSeverity.INFO,
            languages=["python", "javascript"],
            tags=["naming", "convention"],
        )
        assert "python" in r.languages
        assert "naming" in r.tags


class TestUserModel:
    def test_user_defaults(self) -> None:
        """User 应使用默认角色。"""
        from review_agent.types.enums import UserRole
        u = User(username="alice", email="alice@example.com")
        assert u.role == UserRole.VIEWER
        assert u.is_active is True


class TestWebhookEventModel:
    def test_webhook_event_defaults(self) -> None:
        """WebhookEvent 应使用默认值。"""
        from review_agent.types.enums import EventAction
        e = WebhookEvent(
            project_id=UUID(int=1),
            platform=Platform.GITHUB,
            event_id="evt-001",
            action=EventAction.OPENED,
            pr_number=42,
            raw_payload='{"action": "opened"}',
        )
        assert e.is_processed is False


class TestPullRequestModel:
    def test_pull_request_defaults(self) -> None:
        """PullRequest 应使用默认值。"""
        from review_agent.types.models import PullRequest
        pr = PullRequest(
            project_id=UUID(int=1),
            pr_number=42,
            platform=Platform.GITHUB,
        )
        assert pr.state == "open"
        assert pr.is_merged is False
        assert pr.title == ""

    def test_pull_request_merged_state(self) -> None:
        """PullRequest 合并状态。"""
        from review_agent.types.models import PullRequest
        pr = PullRequest(
            project_id=UUID(int=1),
            pr_number=42,
            platform=Platform.GITHUB,
            state="merged",
            is_merged=True,
            merge_sha="abc123",
        )
        assert pr.is_merged is True
        assert pr.merge_sha == "abc123"


class TestCommitModel:
    def test_commit_defaults(self) -> None:
        """Commit 应使用默认值。"""
        from review_agent.types.models import Commit
        c = Commit(
            project_id=UUID(int=1),
            sha="abc123",
        )
        assert c.is_reviewed is False
        assert c.author is None

    def test_commit_review_request(self) -> None:
        """CommitReviewRequest 应正确解析。"""
        from review_agent.types.models import CommitReviewRequest
        req = CommitReviewRequest(sha="abc123", mention_user="reviewer-bot")
        assert req.sha == "abc123"
        assert req.mention_user == "reviewer-bot"


class TestCommentModel:
    def test_comment_defaults(self) -> None:
        """Comment 应正确解析。"""
        from review_agent.types.models import Comment
        c = Comment(
            review_id=UUID(int=1),
            author="user1",
            content="Great finding!",
        )
        assert c.action is None
        assert c.finding_id is None

    def test_comment_create(self) -> None:
        """CommentCreate 应正确解析。"""
        from review_agent.types.models import CommentCreate
        cc = CommentCreate(author="user1", content="Looks good")
        assert cc.action is None

    def test_comment_with_action(self) -> None:
        """Comment 支持 action 字段。"""
        from review_agent.types.models import CommentCreate
        cc = CommentCreate(author="user1", content="Accepted", action="accepted")
        assert cc.action == "accepted"


class TestReviewErrorLogModel:
    def test_error_log_defaults(self) -> None:
        """ReviewErrorLog 应使用默认值。"""
        from review_agent.types.models import ReviewErrorLog
        e = ReviewErrorLog(
            error_type="ai_call_failed",
            error_message="Timeout connecting to API",
        )
        assert e.recovered is False
        assert e.frequency == 1
        assert e.error_detail is None


class TestQualitySnapshotModel:
    def test_quality_snapshot_defaults(self) -> None:
        """QualitySnapshot 应使用默认值。"""
        from datetime import date

        from review_agent.types.models import QualitySnapshot
        qs = QualitySnapshot(
            project_id=UUID(int=1),
            snapshot_date=date(2026, 6, 1),
            period="monthly",
        )
        assert qs.avg_score == 0.0
        assert qs.total_reviews == 0


class TestDashboardStatsModel:
    def test_dashboard_stats_defaults(self) -> None:
        """DashboardStats 应使用默认值。"""
        from review_agent.types.models import DashboardStats
        ds = DashboardStats()
        assert ds.total_projects == 0
        assert ds.total_reviews_today == 0
        assert ds.finding_distribution == {}

    def test_dashboard_stats_with_data(self) -> None:
        """DashboardStats 应接受数据。"""
        from review_agent.types.models import DashboardStats
        ds = DashboardStats(
            total_projects=5,
            total_reviews_today=10,
            average_score=85.0,
            finding_distribution={"security": 3, "bug": 2},
        )
        assert ds.total_projects == 5
        assert ds.finding_distribution["security"] == 3
