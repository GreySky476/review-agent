"""Tests for entity repositories using mocked session."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from review_agent.repo.finding import FindingRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.review import ReviewRepo
from review_agent.repo.rule import RuleRepo
from review_agent.repo.user import UserRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.types.enums import FindingCategory, Platform


def make_result_mock(scalars_return: list | None = None) -> MagicMock:
    """创建一个模拟的 SQLAlchemy Result 对象。"""
    if scalars_return is None:
        scalars_return = [MagicMock()]
    scalar_result = MagicMock()
    scalar_result.all.return_value = scalars_return
    scalar_result.first.return_value = scalars_return[0] if scalars_return else None
    scalar_result.one_or_none.return_value = scalars_return[0] if scalars_return else None
    result = MagicMock()
    result.scalars.return_value = scalar_result
    result.scalar_one_or_none.return_value = scalars_return[0] if scalars_return else None
    return result


@pytest.fixture
def db():
    db = AsyncMock()
    db.get = AsyncMock(return_value=None)
    db.execute = AsyncMock(return_value=make_result_mock())
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    return db


@pytest.fixture
def db_with_result(db):
    """DB mock that returns results from execute. Override by setting result.return_value."""
    return db


class TestProjectRepo:
    def test_extends_base(self, db):
        repo = ProjectRepo(db)
        assert repo._model is not None

    @pytest.mark.asyncio
    async def test_get_by_platform_repo(self, db):
        repo = ProjectRepo(db)
        await repo.get_by_platform_repo(Platform.GITHUB, "https://github.com/test")
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_webhook_secret(self, db):
        repo = ProjectRepo(db)
        await repo.get_by_webhook_secret("secret-123")
        db.execute.assert_awaited_once()


class TestReviewRepo:
    def test_extends_base(self, db):
        repo = ReviewRepo(db)
        assert repo._model is not None

    @pytest.mark.asyncio
    async def test_get_by_project_pr(self, db):
        repo = ReviewRepo(db)
        result = await repo.get_by_project_pr("proj-1", 42)
        db.execute.assert_awaited_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_get_by_head_sha(self, db):
        repo = ReviewRepo(db)
        await repo.get_by_head_sha("abc123")
        db.execute.assert_awaited_once()


class TestFindingRepo:
    def test_extends_base(self, db):
        repo = FindingRepo(db)
        assert repo._model is not None

    @pytest.mark.asyncio
    async def test_list_by_review(self, db):
        db.execute = AsyncMock(return_value=make_result_mock([MagicMock()]))
        repo = FindingRepo(db)
        result = await repo.list_by_review("review-1")
        db.execute.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_count_by_category(self, db):
        f1, f2 = MagicMock(), MagicMock()
        f1.category = FindingCategory.SECURITY
        f2.category = FindingCategory.BUG
        db.execute = AsyncMock(return_value=make_result_mock([f1, f2]))
        repo = FindingRepo(db)
        result = await repo.count_by_category("review-1")
        assert result[FindingCategory.SECURITY] == 1
        assert result[FindingCategory.BUG] == 1

    @pytest.mark.asyncio
    async def test_count_by_severity(self, db):
        f1, f2 = MagicMock(), MagicMock()
        from review_agent.types.enums import FindingSeverity
        f1.severity = FindingSeverity.CRITICAL
        f2.severity = FindingSeverity.WARNING
        db.execute = AsyncMock(return_value=make_result_mock([f1, f2]))
        repo = FindingRepo(db)
        result = await repo.count_by_severity("review-1")
        assert len(result) == 2


class TestRuleRepo:
    def test_extends_base(self, db):
        repo = RuleRepo(db)
        assert repo._model is not None

    @pytest.mark.asyncio
    async def test_list_active(self, db):
        db.execute = AsyncMock(return_value=make_result_mock([MagicMock()]))
        repo = RuleRepo(db)
        result = await repo.list_active()
        db.execute.assert_awaited_once()
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_list_by_category(self, db):
        db.execute = AsyncMock(return_value=make_result_mock([MagicMock()]))
        repo = RuleRepo(db)
        result = await repo.list_by_category(FindingCategory.SECURITY)
        db.execute.assert_awaited_once()
        assert len(result) == 1


class TestUserRepo:
    def test_extends_base(self, db):
        repo = UserRepo(db)
        assert repo._model is not None

    @pytest.mark.asyncio
    async def test_get_by_username(self, db):
        repo = UserRepo(db)
        await repo.get_by_username("alice")
        db.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_by_email(self, db):
        repo = UserRepo(db)
        await repo.get_by_email("alice@example.com")
        db.execute.assert_awaited_once()


class TestWebhookEventRepo:
    def test_extends_base(self, db):
        repo = WebhookEventRepo(db)
        assert repo._model is not None

    @pytest.mark.asyncio
    async def test_exists_in_window_returns_false(self, db):
        """不存在事件时返回 False。"""
        db.execute = AsyncMock(return_value=make_result_mock([]))
        repo = WebhookEventRepo(db)
        result = await repo.exists_in_window("evt-001")
        assert result is False

    @pytest.mark.asyncio
    async def test_exists_in_window_returns_true(self, db):
        """已存在事件时返回 True。"""
        db.execute = AsyncMock(return_value=make_result_mock([MagicMock()]))
        repo = WebhookEventRepo(db)
        result = await repo.exists_in_window("evt-001")
        assert result is True

    @pytest.mark.asyncio
    async def test_create_from_payload(self, db):
        repo = WebhookEventRepo(db)
        await repo.create_from_payload(
            project_id="proj-1",
            platform="github",
            event_id="evt-002",
            action="opened",
            pr_number=42,
            raw_payload="{}",
        )
        db.add.assert_called_once()
        db.flush.assert_awaited_once()
