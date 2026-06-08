"""Tests for BaseRepository using mocked session."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from review_agent.repo.base import BaseRepository
from review_agent.types.exceptions import NotFoundError
from review_agent.types.orm import ProjectModel


class ConcreteRepo(BaseRepository[ProjectModel]):
    """Concrete repo for testing base class."""

    @property
    def _model(self) -> type[ProjectModel]:  # type: ignore[misc]
        return ProjectModel  # type: ignore[no-any-return]


@pytest.fixture
def repo() -> ConcreteRepo:
    db = AsyncMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    return ConcreteRepo(db)


class TestBaseRepository:
    """BaseRepository 核心功能测试。"""

    @pytest.mark.asyncio
    async def test_create_calls_add_and_flush(self, repo: ConcreteRepo) -> None:
        """create 应调用 db.add 和 db.flush。"""
        import uuid

        await repo.create(
            id=str(uuid.uuid4()),
            name="test",
            platform="github",
            repo_url="https://github.com/test",
        )
        repo._db.add.assert_called_once()
        repo._db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_returns_none_when_missing(self, repo: ConcreteRepo) -> None:
        """get 不存在的 ID 应返回 None。"""
        repo._db.get.return_value = None
        result = await repo.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_or_raise_raises_not_found(self, repo: ConcreteRepo) -> None:
        """get_or_raise 不存在的 ID 应抛出 NotFoundError。"""
        repo._db.get.return_value = None
        with pytest.raises(NotFoundError):
            await repo.get_or_raise("nonexistent-id")

    @pytest.mark.asyncio
    async def test_hard_delete_calls_execute_and_flush(self, repo: ConcreteRepo) -> None:
        """hard_delete 应调用 db.execute 和 db.flush。"""
        await repo.hard_delete("some-id")
        repo._db.execute.assert_awaited_once()
        repo._db.flush.assert_awaited_once()
