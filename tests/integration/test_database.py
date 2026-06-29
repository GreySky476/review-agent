"""Integration tests for database repository layer.

Tests cover: project CRUD, review CRUD with findings, using mocked DB sessions.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.types.enums import Platform, ReviewStatus
from review_agent.types.orm import ProjectModel, ReviewModel


@pytest.mark.asyncio
@pytest.mark.integration
class TestProjectCrud:
    """ProjectRepo CRUD 集成测试。"""

    async def test_create_project(self, mock_db: AsyncSession) -> None:
        """创建项目应返回 ProjectModel 实例。"""
        from review_agent.repo.project import ProjectRepo

        repo = ProjectRepo(mock_db)
        project = await repo.create(
            id="proj-001",
            name="test-project",
            platform=Platform.GITHUB,
            repo_url="https://github.com/test/repo",
        )

        assert project.id == "proj-001"
        assert project.name == "test-project"
        assert project.platform == Platform.GITHUB
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    async def test_get_project_by_id(self, mock_db: AsyncSession) -> None:
        """按 ID 查询项目应返回正确的 ProjectModel。"""
        from review_agent.repo.project import ProjectRepo

        project_mock = MagicMock(spec=ProjectModel)
        project_mock.id = "proj-002"
        project_mock.name = "found-project"
        project_mock.is_deleted = False

        mock_db.get = AsyncMock(return_value=project_mock)

        repo = ProjectRepo(mock_db)
        result = await repo.get("proj-002")

        assert result is not None
        assert result.id == "proj-002"
        assert result.name == "found-project"
        mock_db.get.assert_awaited_once_with(ProjectModel, "proj-002")

    async def test_update_project_settings(self, mock_db: AsyncSession) -> None:
        """更新项目 settings 应正确合并 JSON 配置。"""
        from review_agent.repo.project import ProjectRepo

        project_mock = MagicMock(spec=ProjectModel)
        project_mock.id = "proj-003"
        project_mock.settings = '{"existing_key": "value"}'
        project_mock.is_deleted = False

        mock_db.get = AsyncMock(return_value=project_mock)

        repo = ProjectRepo(mock_db)
        result = await repo.update_settings(
            "proj-003",
            review_branches=["main", "develop"],
        )

        assert result.get("existing_key") == "value"
        assert result.get("review_branches") == ["main", "develop"]
        mock_db.flush.assert_awaited_once()

    async def test_get_review_branches_default(self, mock_db: AsyncSession) -> None:
        """未配置 review_branches 时应返回默认的 ["*"]。"""
        from review_agent.repo.project import ProjectRepo

        project_mock = MagicMock(spec=ProjectModel)
        project_mock.id = "proj-004"
        project_mock.settings = "{}"
        project_mock.is_deleted = False

        mock_db.get = AsyncMock(return_value=project_mock)

        repo = ProjectRepo(mock_db)
        branches = await repo.get_review_branches("proj-004")

        assert branches == ["*"]

    async def test_get_by_platform_repo_found(self, mock_db: AsyncSession) -> None:
        """按平台和仓库 URL 查询项目应返回匹配的 ProjectModel。"""
        from review_agent.repo.project import ProjectRepo
        from tests.conftest import MockResult

        project_mock = MagicMock(spec=ProjectModel)
        project_mock.id = "proj-005"
        project_mock.platform = Platform.GITHUB
        project_mock.repo_url = "https://github.com/owner/repo"
        project_mock.is_deleted = False

        mock_db.execute = AsyncMock(return_value=MockResult([project_mock]))

        repo = ProjectRepo(mock_db)
        result = await repo.get_by_platform_repo(Platform.GITHUB, "https://github.com/owner/repo")

        assert result is not None
        assert result.id == "proj-005"

    async def test_delete_project(self, mock_db: AsyncSession) -> None:
        """软删除项目应将 is_deleted 设为 True。"""
        from review_agent.repo.project import ProjectRepo

        project_mock = MagicMock(spec=ProjectModel)
        project_mock.id = "proj-006"
        project_mock.is_deleted = False

        mock_db.get = AsyncMock(return_value=project_mock)

        repo = ProjectRepo(mock_db)
        await repo.soft_delete("proj-006")

        assert project_mock.is_deleted is True
        mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.integration
class TestReviewCrud:
    """ReviewRepo CRUD 集成测试。"""

    async def test_create_review(self, mock_db: AsyncSession) -> None:
        """创建评审记录应返回 ReviewModel 实例。"""
        from review_agent.repo.review import ReviewRepo

        repo = ReviewRepo(mock_db)
        review = await repo.create(
            id="review-001",
            project_id="proj-001",
            pr_number=42,
            head_sha="abc123def456",
            status=ReviewStatus.PENDING,
            score=0,
        )

        assert review.id == "review-001"
        assert review.project_id == "proj-001"
        assert review.pr_number == 42
        assert review.status == ReviewStatus.PENDING
        mock_db.add.assert_called_once()
        mock_db.flush.assert_awaited_once()

    async def test_get_by_project_pr(self, mock_db: AsyncSession) -> None:
        """按项目和 PR 号查询应返回最新评审。"""
        from review_agent.repo.review import ReviewRepo
        from tests.conftest import MockResult

        review_mock = MagicMock(spec=ReviewModel)
        review_mock.id = "review-002"
        review_mock.project_id = "proj-001"
        review_mock.pr_number = 42
        review_mock.head_sha = "abc123"
        review_mock.status = ReviewStatus.COMPLETED
        review_mock.is_deleted = False

        # MockSelectResult: MockResult with scalar_one_or_none returning review_mock
        mock_result = MockResult(scalar_value=review_mock)
        # Override scalar_one_or_none explicitly
        mock_result.scalar_one_or_none = MagicMock(return_value=review_mock)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ReviewRepo(mock_db)
        result = await repo.get_by_project_pr("proj-001", 42)

        assert result is not None
        assert result.id == "review-002"
        assert result.status == ReviewStatus.COMPLETED

    async def test_create_or_get_new_review(self, mock_db: AsyncSession) -> None:
        """create_or_get 应为新评审返回 (review, True)。"""
        from review_agent.repo.review import ReviewRepo

        repo = ReviewRepo(mock_db)
        repo.get_running_by_sha = AsyncMock(return_value=None)  # type: ignore[assignment]
        review, is_new = await repo.create_or_get(
            project_id="proj-001",
            pr_number=42,
            head_sha="abc123",
            status=ReviewStatus.PENDING,
        )

        assert is_new is True
        assert review.project_id == "proj-001"
        assert review.pr_number == 42
        assert review.head_sha == "abc123"
        mock_db.add.assert_called_once()

    async def test_list_by_pr_empty(self, mock_db: AsyncSession) -> None:
        """无评审记录时应返回空列表。"""
        from review_agent.repo.review import ReviewRepo
        from tests.conftest import MockResult

        # For list_by_pr, execute → scalars() → all() → []
        mock_result = MockResult(scalars_list=[])
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ReviewRepo(mock_db)
        result = await repo.list_by_pr("proj-001", 42)

        assert result == []

    async def test_update_review_status(self, mock_db: AsyncSession) -> None:
        """更新评审状态应正确执行。"""
        from review_agent.repo.review import ReviewRepo

        review_mock = MagicMock(spec=ReviewModel)
        review_mock.id = "review-003"
        review_mock.status = ReviewStatus.PENDING
        review_mock.score = 0
        review_mock.is_deleted = False

        mock_db.get = AsyncMock(return_value=review_mock)

        repo = ReviewRepo(mock_db)
        result = await repo.update(
            "review-003",
            status=ReviewStatus.COMPLETED,
            score=85,
        )

        assert result is not None
        assert review_mock.status == ReviewStatus.COMPLETED  # type: ignore
        assert review_mock.score == 85  # type: ignore
        mock_db.flush.assert_awaited()

    async def test_get_by_head_sha(self, mock_db: AsyncSession) -> None:
        """按 head_sha 查询应返回匹配的评审。"""
        from review_agent.repo.review import ReviewRepo
        from tests.conftest import MockResult

        review_mock = MagicMock(spec=ReviewModel)
        review_mock.id = "review-004"
        review_mock.head_sha = "abc123"
        review_mock.is_deleted = False

        mock_result = MockResult(scalar_value=review_mock)
        mock_result.scalar_one_or_none = MagicMock(return_value=review_mock)
        mock_db.execute = AsyncMock(return_value=mock_result)

        repo = ReviewRepo(mock_db)
        result = await repo.get_by_head_sha("proj-001", "abc123")

        assert result is not None
        assert result.id == "review-004"
        assert result.head_sha == "abc123"
