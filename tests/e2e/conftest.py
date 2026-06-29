"""E2E test fixtures — root conftest.py provides MockResult, mock_db."""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.app import create_app
from review_agent.api.dependencies.auth import get_current_user
from review_agent.config.database import get_session


@pytest.fixture
def app(mock_db: AsyncSession) -> Any:
    """创建 FastAPI 应用实例，注入 mock DB 和认证覆盖。"""
    app_instance = create_app()

    async def _override():
        yield mock_db

    app_instance.dependency_overrides[get_session] = _override

    async def _auth_override():
        return {"user_id": "test-user", "role": "super_admin"}

    app_instance.dependency_overrides[get_current_user] = _auth_override
    return app_instance


@pytest.fixture(autouse=True)
def _mock_github_api():
    """Mock GitHub API 调用 — 阻止 E2E 测试产生真实的网络调用。"""
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
    """创建 HTTP 测试客户端。"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
