"""Tests for webhook helper functions and branch filtering logic."""

from __future__ import annotations

import fnmatch
from unittest.mock import AsyncMock, MagicMock

import pytest

from review_agent.repo.project import ProjectRepo
from review_agent.types.orm import ProjectModel


def make_project_mock(settings: str = "{}") -> MagicMock:
    """创建一个模拟的 ProjectModel 实例。"""
    project = MagicMock(spec=ProjectModel)
    project.id = "proj-123"
    project.settings = settings
    project.webhook_enabled = True
    project.platform = "github"
    project.repo_url = "https://github.com/test/repo"
    return project


@pytest.fixture
def db():
    db = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    db.flush = AsyncMock()
    return db


class TestBranchMatchingLogic:
    """测试 fnmatch 分支匹配逻辑（webhook_helpers.py 的核心逻辑）。"""

    def test_exact_branch_match(self) -> None:
        """精确分支名匹配。"""
        allowed = ["main", "develop"]
        assert any(fnmatch.fnmatch("main", p) for p in allowed)
        assert any(fnmatch.fnmatch("develop", p) for p in allowed)

    def test_exact_branch_no_match(self) -> None:
        """精确分支名不匹配。"""
        allowed = ["main", "develop"]
        assert not any(fnmatch.fnmatch("feature/login", p) for p in allowed)

    def test_wildcard_match(self) -> None:
        """通配符 * 匹配任意后缀。"""
        allowed = ["release/*"]
        assert any(fnmatch.fnmatch("release/v1.0", p) for p in allowed)
        assert any(fnmatch.fnmatch("release/2.0.1", p) for p in allowed)
        assert not any(fnmatch.fnmatch("main", p) for p in allowed)

    def test_wildcard_all(self) -> None:
        """* 匹配所有分支。"""
        allowed = ["*"]
        assert any(fnmatch.fnmatch("main", p) for p in allowed)
        assert any(fnmatch.fnmatch("feature/foo", p) for p in allowed)
        assert any(fnmatch.fnmatch("release/v1", p) for p in allowed)

    def test_multiple_patterns(self) -> None:
        """多个模式组合。"""
        allowed = ["main", "develop", "release/*"]
        assert any(fnmatch.fnmatch("main", p) for p in allowed)
        assert any(fnmatch.fnmatch("develop", p) for p in allowed)
        assert any(fnmatch.fnmatch("release/v2.0", p) for p in allowed)
        assert not any(fnmatch.fnmatch("feature/login", p) for p in allowed)
        assert not any(fnmatch.fnmatch("hotfix/1", p) for p in allowed)


class TestProjectRepoBranchSettings:
    """测试 ProjectRepo 的分支配置读写。"""

    @pytest.mark.asyncio
    async def test_get_review_branches_default(self, db) -> None:
        """settings 为空时返回默认 ["*"]。"""
        project = make_project_mock(settings="{}")
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        branches = await repo.get_review_branches("proj-123")
        assert branches == ["*"]

    @pytest.mark.asyncio
    async def test_get_review_branches_custom(self, db) -> None:
        """settings 中有 review_branches 时正确返回。"""
        project = make_project_mock(settings='{"review_branches": ["main", "develop"]}')
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        branches = await repo.get_review_branches("proj-123")
        assert branches == ["main", "develop"]

    @pytest.mark.asyncio
    async def test_get_review_branches_with_wildcard(self, db) -> None:
        """settings 中带通配符的分支模式。"""
        project = make_project_mock(settings='{"review_branches": ["main", "release/*"]}')
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        branches = await repo.get_review_branches("proj-123")
        assert len(branches) == 2
        assert any(fnmatch.fnmatch("release/v1.0", p) for p in branches)
        assert any(fnmatch.fnmatch("main", p) for p in branches)

    @pytest.mark.asyncio
    async def test_get_review_branches_empty_list(self, db) -> None:
        """settings 中 review_branches 为空列表时返回默认 ["*"]。"""
        project = make_project_mock(settings='{"review_branches": []}')
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        branches = await repo.get_review_branches("proj-123")
        assert branches == ["*"]

    @pytest.mark.asyncio
    async def test_get_review_branches_invalid_json(self, db) -> None:
        """settings 为无效 JSON 时返回默认 ["*"]。"""
        project = make_project_mock(settings="not-json")
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        branches = await repo.get_review_branches("proj-123")
        assert branches == ["*"]

    @pytest.mark.asyncio
    async def test_get_review_branches_project_not_found(self, db) -> None:
        """项目不存在时返回默认 ["*"]。"""
        db.get = AsyncMock(return_value=None)
        repo = ProjectRepo(db)
        branches = await repo.get_review_branches("non-existent")
        assert branches == ["*"]

    @pytest.mark.asyncio
    async def test_update_settings_adds_review_branches(self, db) -> None:
        """update_settings 能正确写入 review_branches。"""
        project = make_project_mock(settings="{}")
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        result = await repo.update_settings("proj-123", review_branches=["main", "develop"])
        assert result.get("review_branches") == ["main", "develop"]
        # 验证 settings 被更新为 JSON 字符串
        import json
        saved = json.loads(project.settings)
        assert saved.get("review_branches") == ["main", "develop"]

    @pytest.mark.asyncio
    async def test_update_settings_merges_existing(self, db) -> None:
        """update_settings 合并已有配置，不覆盖其他 key。"""
        project = make_project_mock(settings='{"existing_key": "value"}')
        db.get = AsyncMock(return_value=project)
        repo = ProjectRepo(db)
        result = await repo.update_settings("proj-123", review_branches=["release/*"])
        assert result.get("existing_key") == "value"
        assert result.get("review_branches") == ["release/*"]
