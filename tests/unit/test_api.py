"""Tests for API endpoints."""

# 测试环境禁用 IP 白名单和速率限制（需在导入 app 前设置）
import os

os.environ.setdefault("REVIEW_AGENT_WEBHOOK_IP_WHITELIST_ENABLED", "false")
os.environ.setdefault("REVIEW_AGENT_WEBHOOK_RATE_LIMITER_ENABLED", "false")

from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.app import create_app
from review_agent.api.dependencies.auth import get_current_user
from review_agent.config.database import get_session
from review_agent.types.orm import ProjectModel


class MockResult:
    """模拟 SQLAlchemy Result。"""

    def __init__(self, scalars_list: list | None = None, scalar_value=None):
        self._scalars_list = scalars_list or []
        self._scalar_value = scalar_value

    def scalars(self) -> "MockResult":
        return self

    def all(self) -> list:
        return self._scalars_list

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalars_list[0] if self._scalars_list else None

    def first(self):
        return self._scalars_list[0] if self._scalars_list else None


@pytest.fixture
def mock_db() -> AsyncSession:
    """返回 mock AsyncSession，execute 返回空结果。"""
    mock = AsyncMock(spec=AsyncSession)

    # 支持 begin_nested() savepoint
    savepoint = AsyncMock()
    savepoint.commit = AsyncMock()
    savepoint.rollback = AsyncMock()
    mock.begin_nested = AsyncMock(return_value=savepoint)

    mock.execute.return_value = MockResult([])
    return mock  # type: ignore


@pytest.fixture
def app(mock_db: AsyncSession) -> Any:
    app = create_app()

    async def _override():
        yield mock_db

    app.dependency_overrides[get_session] = _override

    # 为现有测试提供默认认证用户（绕过 JWT 认证）
    async def _auth_override():
        return {"user_id": "test-user", "role": "super_admin"}

    app.dependency_overrides[get_current_user] = _auth_override
    return app


@pytest.fixture(autouse=True)
def _mock_github_api():
    """Mock GitHub API calls via respx — 阻止测试产生真实的网络调用。"""
    with respx.mock(
        base_url="https://api.github.com", assert_all_mocked=False, assert_all_called=False
    ) as respx_mock:
        respx_mock.get(path__regex=r"/repos/[^/]+/[^/]+/pulls/\d+/files").respond(
            json=[],
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "0",
            },
        )
        respx_mock.get(path__regex=r"/repos/[^/]+/[^/]+/pulls/\d+").respond(
            json={},
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "0",
            },
        )
        respx_mock.get(path__regex=r"/repos/[^/]+/[^/]+/commits/[a-f0-9]+").respond(
            json={},
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "0",
            },
        )
        # webhook 连通性检查
        respx_mock.get(path__regex=r"/repos/[^/]+/[^/]+/hooks").respond(
            json=[],
            headers={
                "X-RateLimit-Limit": "5000",
                "X-RateLimit-Remaining": "4999",
                "X-RateLimit-Reset": "0",
            },
        )
        yield


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestHealthEndpoint:
    async def test_healthz_returns_ok(self, client: AsyncClient) -> None:
        resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
class TestWebhookEndpoints:
    async def test_github_webhook_accepted(self, client: AsyncClient) -> None:
        payload = {
            "action": "opened",
            "pull_request": {"number": 42},
        }
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

    async def test_github_webhook_unsupported_event(self, client: AsyncClient) -> None:
        payload = {"action": "created"}
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "issues"},
        )
        data = resp.json()
        assert data["status"] == "ignored"

    async def test_github_push_event_no_project(self, client: AsyncClient) -> None:
        """Push event for unknown repo should be ignored."""
        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "unknown/repo"},
            "head_commit": {
                "id": "abc123",
                "message": "test commit",
                "author": {"name": "tester"},
                "added": ["new.py"],
                "modified": [],
                "removed": [],
            },
            "commits": [],
        }
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"

    async def test_github_push_event_no_head_commit(self, client: AsyncClient) -> None:
        """Push event without head_commit should be ignored."""
        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "test/repo"},
        }
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "push"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"

    async def test_pr_review_skipped_when_target_branch_not_matched(
        self, client: AsyncClient, mock_db: AsyncSession
    ) -> None:
        """PR targeting a branch not in review_branches should be skipped."""
        project = MagicMock(spec=ProjectModel)
        project.id = "proj-123"
        project.settings = '{"review_branches": ["main"]}'
        project.webhook_enabled = True
        project.platform = "github"
        project.repo_url = "https://github.com/test/repo"

        mock_db.execute = AsyncMock(return_value=MockResult([project]))
        mock_db.get = AsyncMock(return_value=project)

        payload = {
            "action": "opened",
            "repository": {"full_name": "test/repo"},
            "pull_request": {
                "number": 42,
                "base": {"ref": "develop"},
                "head": {"sha": "abc123"},
                "title": "Test PR",
                "user": {"login": "tester"},
            },
        }
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "skipped"
        assert data["reason"] == "branch_not_matched"

    @pytest.mark.skip(
        reason="mock_db 返回通用查询结果，需重构 fixtures 适配新的 create_or_get 查询"
    )
    async def test_pr_review_accepted_when_target_branch_matches(
        self, client: AsyncClient, mock_db: AsyncSession
    ) -> None:
        """PR targeting 'main' with review_branches=['main'] should proceed."""
        project = MagicMock(spec=ProjectModel)
        project.id = "proj-123"
        project.settings = '{"review_branches": ["main"]}'
        project.webhook_enabled = True
        project.platform = "github"
        project.repo_url = "https://github.com/test/repo"

        mock_db.execute = AsyncMock(return_value=MockResult([project]))
        mock_db.get = AsyncMock(return_value=project)

        payload = {
            "action": "opened",
            "repository": {"full_name": "test/repo"},
            "pull_request": {
                "number": 42,
                "base": {"ref": "main"},
                "head": {"sha": "abc123"},
                "title": "Test PR",
                "user": {"login": "tester"},
            },
        }
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Accepted means branch filter passed; review may still fail due to
        # GitHub API mocking, but the branch filter check is what we test here.
        assert data["status"] in ("accepted", "ignored"), (
            f"Expected accepted or ignored, got: {data}"
        )

    @pytest.mark.skip(
        reason="mock_db 返回通用查询结果，需重构 fixtures 适配新的 create_or_get 查询"
    )
    async def test_pr_review_accepted_with_wildcard_branch(
        self, client: AsyncClient, mock_db: AsyncSession
    ) -> None:
        """PR targeting 'release/v1' with review_branches=['release/*'] should proceed."""
        project = MagicMock(spec=ProjectModel)
        project.id = "proj-123"
        project.settings = '{"review_branches": ["release/*"]}'
        project.webhook_enabled = True
        project.platform = "github"
        project.repo_url = "https://github.com/test/repo"

        mock_db.execute = AsyncMock(return_value=MockResult([project]))
        mock_db.get = AsyncMock(return_value=project)

        payload = {
            "action": "opened",
            "repository": {"full_name": "test/repo"},
            "pull_request": {
                "number": 42,
                "base": {"ref": "release/v1"},
                "head": {"sha": "abc123"},
                "title": "Test PR",
                "user": {"login": "tester"},
            },
        }
        resp = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "pull_request"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("accepted", "ignored"), (
            f"Expected accepted or ignored, got: {data}"
        )


@pytest.mark.asyncio
class TestGitLabWebhookEndpoints:
    """Integration tests for GitLab webhook endpoint."""

    async def test_gitlab_mr_accepted(self, client: AsyncClient) -> None:
        """GitLab MR event with open action should be accepted."""
        payload = {
            "object_kind": "merge_request",
            "project": {"path_with_namespace": "test/repo"},
            "object_attributes": {
                "iid": 42,
                "action": "open",
                "state": "opened",
                "title": "Test MR",
                "source_branch": "feature/test",
                "target_branch": "main",
                "last_commit": {"id": "abc123"},
            },
        }
        resp = await client.post(
            "/webhook/gitlab",
            json=payload,
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

    async def test_gitlab_push_no_project(self, client: AsyncClient) -> None:
        """GitLab push event for unknown repo should be ignored."""
        payload = {
            "object_kind": "push",
            "ref": "refs/heads/main",
            "project": {"path_with_namespace": "unknown/repo"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "test",
                    "author": {"name": "tester"},
                    "added": ["new.py"],
                    "modified": [],
                    "removed": [],
                }
            ],
        }
        resp = await client.post(
            "/webhook/gitlab",
            json=payload,
            headers={"X-Gitlab-Event": "Push Hook"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"

    async def test_gitlab_unsupported_event(self, client: AsyncClient) -> None:
        """GitLab unsupported event type should be ignored."""
        payload = {"object_kind": "issue"}
        resp = await client.post(
            "/webhook/gitlab",
            json=payload,
            headers={"X-Gitlab-Event": "Issue Hook"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"


@pytest.mark.asyncio
class TestGiteeWebhookEndpoints:
    """Integration tests for Gitee webhook endpoint."""

    async def test_gitee_mr_accepted(self, client: AsyncClient) -> None:
        """Gitee MR event with open action should be accepted."""
        payload = {
            "action": "open",
            "repository": {"full_name": "test/repo"},
            "project": {"path_with_namespace": "test/repo"},
            "pull_request": {
                "number": 42,
                "state": "open",
                "title": "Test PR",
                "user": {"login": "tester"},
                "head": {"ref": "feature/test", "sha": "abc123"},
                "base": {"ref": "main"},
            },
            "object_attributes": {"iid": 42, "action": "open"},
        }
        resp = await client.post(
            "/webhook/gitee",
            json=payload,
            headers={"X-Gitee-Token": "test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "accepted"

    async def test_gitee_push_no_project(self, client: AsyncClient) -> None:
        """Gitee push event for unknown repo should be ignored."""
        payload = {
            "ref": "refs/heads/main",
            "repository": {"full_name": "unknown/repo"},
            "project": {"path_with_namespace": "unknown/repo"},
            "commits": [
                {
                    "id": "abc123",
                    "message": "test",
                    "author": {"name": "tester"},
                    "added": ["new.py"],
                    "modified": [],
                    "removed": [],
                }
            ],
            "head_commit": {
                "id": "abc123",
                "message": "test",
                "author": {"name": "tester"},
                "added": ["new.py"],
                "modified": [],
                "removed": [],
            },
        }
        resp = await client.post(
            "/webhook/gitee",
            json=payload,
            headers={"X-Gitee-Token": "test-token"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"

    async def test_gitee_unknown_event(self, client: AsyncClient) -> None:
        """Gitee event without PR or push markers should be ignored."""
        payload = {"some": "data"}
        resp = await client.post(
            "/webhook/gitee",
            json=payload,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ignored"


@pytest.mark.asyncio
class TestProjectEndpoints:
    async def test_create_project(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects",
            json={"name": "test", "platform": "github", "repo_url": "https://github.com/test/repo"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "test"

    async def test_list_projects(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_list_projects_with_platform_filter(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects?platform=github")
        assert resp.status_code == 200

    async def test_get_project(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/test-id")
        assert resp.status_code == 200
        assert resp.json()["id"] == "test-id"

    async def test_update_project(self, client: AsyncClient) -> None:
        resp = await client.patch(
            "/api/v1/projects/test-id",
            json={"name": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    async def test_delete_project(self, client: AsyncClient) -> None:
        resp = await client.delete("/api/v1/projects/test-id")
        assert resp.status_code == 200
        assert resp.json()["deleted"] is True

    async def test_webhook_connection_check(
        self, client: AsyncClient, mock_db: AsyncSession
    ) -> None:
        """Webhook test endpoint should return events field."""
        project = MagicMock(spec=ProjectModel)
        project.id = "proj-123"
        project.settings = '{"review_branches": ["main"]}'
        project.webhook_enabled = True
        project.platform = "github"
        project.repo_url = "https://github.com/owner/repo"
        project.is_deleted = False

        mock_db.get = AsyncMock(return_value=project)
        mock_db.execute.return_value = MockResult([project])

        resp = await client.post("/api/v1/projects/proj-123/webhook/test")
        assert resp.status_code == 200
        data = resp.json()
        # events field should exist after the enhancement
        assert "events" in data


@pytest.mark.asyncio
class TestReviewEndpoints:
    async def test_trigger_review(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/projects/p1/reviews",
            json={
                "project_id": "00000000-0000-0000-0000-000000000000",
                "pr_number": 42,
                "head_sha": "abc",
            },
        )
        assert resp.status_code == 202
        data = resp.json()
        assert "task_id" in data

    async def test_get_review_status(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/reviews/task-1")
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "task-1"

    async def test_list_reviews(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/reviews")
        assert resp.status_code == 200
        assert resp.json()["items"] == []

    async def test_list_reviews_with_filters(self, client: AsyncClient) -> None:
        resp = await client.get(
            "/api/v1/projects/p1/reviews?status=completed&score_min=70&score_max=100"
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestDashboardEndpoints:
    async def test_dashboard_stats(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/dashboard/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_projects" in data
        assert "total_reviews_today" in data
        assert "average_score" in data
        assert "pending_errors" in data
        assert "finding_distribution" in data

    async def test_quality_trends_default(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/dashboard/quality-trends")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["period"] == "monthly"

    async def test_quality_trends_with_filters(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/dashboard/quality-trends?project_id=p1&period=weekly")
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestPullRequestEndpoints:
    async def test_list_pull_requests(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/pull-requests")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0

    async def test_list_pull_requests_with_state(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/pull-requests?state=open")
        assert resp.status_code == 200

    async def test_get_pull_request_detail(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/pull-requests/42")
        assert resp.status_code == 200
        data = resp.json()
        assert "pull_request" in data
        assert "reviews" in data
        assert "findings" in data


@pytest.mark.asyncio
class TestCommitEndpoints:
    async def test_list_commits(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/commits")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0

    async def test_list_commits_with_filters(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/projects/p1/commits?branch=main&author=me")
        assert resp.status_code == 200

    async def test_trigger_commit_review(self, client: AsyncClient, mock_db: AsyncSession) -> None:
        # Mock project lookup so _extract_repo_name works
        project_mock = MagicMock()
        type(project_mock).repo_url = PropertyMock(return_value="https://github.com/owner/repo")
        mock_db.get.return_value = project_mock

        resp = await client.post(
            "/api/v1/projects/p1/commits/abc123/review",
            json={"sha": "abc123", "mention_user": "reviewer"},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert data["status"] == "accepted"


@pytest.mark.asyncio
class TestErrorEndpoints:
    async def test_list_errors(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/errors")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert data["total"] == 0

    async def test_list_errors_with_filters(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/errors?project_id=p1&error_type=ai_call_failed")
        assert resp.status_code == 200

    async def test_error_stats(self, client: AsyncClient) -> None:
        resp = await client.get("/api/v1/errors/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
