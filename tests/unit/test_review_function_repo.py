"""Tests for ReviewFunctionRepo."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from review_agent.repo.review_function import ReviewFunctionRepo


class TestReviewFunctionRepo:
    @pytest.fixture
    def repo(self) -> ReviewFunctionRepo:
        db = AsyncMock()
        return ReviewFunctionRepo(db)

    @staticmethod
    def _mock_scalars_result(records: list) -> MagicMock:
        """创建模拟的 scalars().all() 链。"""
        mock_all = MagicMock(return_value=records)
        mock_scalars = MagicMock()
        mock_scalars.all = mock_all
        mock_result = MagicMock()
        mock_result.scalars.return_value = mock_scalars
        return mock_result

    async def test_list_by_review(self, repo: ReviewFunctionRepo) -> None:
        """list_by_review 返回空列表。"""
        mock_result = self._mock_scalars_result([])
        repo._db.execute.return_value = mock_result

        result = await repo.list_by_review("review-123")
        assert result == []

    async def test_list_by_review_and_file(self, repo: ReviewFunctionRepo) -> None:
        """list_by_review_and_file 返回空列表。"""
        mock_result = self._mock_scalars_result([])
        repo._db.execute.return_value = mock_result

        result = await repo.list_by_review_and_file("review-123", "src/a.py")
        assert result == []

    async def test_bulk_create(self, repo: ReviewFunctionRepo) -> None:
        """bulk_create 委托给 create_many 并返回实例列表。"""
        items = [
            {
                "review_id": "r1",
                "file_path": "src/a.py",
                "function_name": "foo",
                "start_line": 1,
                "end_line": 5,
                "sha": "abc123",
            },
        ]
        result = await repo.bulk_create(items)
        assert isinstance(result, list)
