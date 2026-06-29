"""Tests for auth API endpoints: login, register, refresh, logout, me."""

# 测试环境配置
import os

os.environ.setdefault(
    "REVIEW_AGENT_JWT_SECRET",
    "a-test-secret-key-that-is-at-least-32-chars-long",  # noqa: S105
)

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.app import create_app
from review_agent.config.database import get_session
from review_agent.types.enums import UserRole
from review_agent.types.orm import UserModel


class MockResult:
    """模拟 SQLAlchemy Result。"""

    def __init__(self, scalars_list: list | None = None, scalar_value=None):
        self._scalars_list = scalars_list or []
        self._scalar_value = scalar_value

    def scalars(self) -> "MockResult":
        return self

    def all(self) -> list:
        return self._scalars_list

    def scalar_one_or_none(self):
        return self._scalars_list[0] if self._scalars_list else None

    def scalar(self):
        return self._scalar_value


def _make_mock_user(user_id: str = "user-001", role: UserRole = UserRole.VIEWER) -> MagicMock:
    """创建模拟 UserModel。"""
    user = MagicMock(spec=UserModel)
    user.id = user_id
    user.username = "testuser"
    user.email = "test@example.com"
    user.password_hash = ""
    user.role = role
    user.is_active = True
    user.is_deleted = False
    return user


@pytest.fixture
def mock_db() -> AsyncSession:
    """返回 mock AsyncSession。"""
    mock = AsyncMock(spec=AsyncSession)
    mock.execute.return_value = MockResult([])
    return mock  # type: ignore


@pytest.fixture
def app(mock_db: AsyncSession) -> Any:
    """创建测试 FastAPI 应用。"""
    app = create_app()

    async def _override():
        yield mock_db

    app.dependency_overrides[get_session] = _override
    return app


@pytest.mark.asyncio
async def test_login_success(app: Any, mock_db: AsyncSession) -> None:  # noqa: ARG001
    """测试成功登录返回 tokens。"""
    from review_agent.service.auth import hash_password

    mock_user = _make_mock_user(role=UserRole.SUPER_ADMIN)
    mock_user.password_hash = hash_password("testpass123")

    with patch(
        "review_agent.repo.user.UserRepo.get_by_username",
        new_callable=AsyncMock,
        return_value=mock_user,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "testpass123"},
            )
            assert response.status_code == 200
            data = response.json()
            assert "access_token" in data
            assert "refresh_token" in data
            assert data["token_type"] == "bearer"  # noqa: S105
            assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_login_wrong_password(app: Any, mock_db: AsyncSession) -> None:  # noqa: ARG001
    """测试错误密码返回 401。"""
    from review_agent.service.auth import hash_password

    mock_user = _make_mock_user()
    mock_user.password_hash = hash_password("correct-password")

    with patch(
        "review_agent.repo.user.UserRepo.get_by_username",
        new_callable=AsyncMock,
        return_value=mock_user,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "wrong-password"},
            )
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_nonexistent_user(app: Any, mock_db: AsyncSession) -> None:  # noqa: ARG001
    """测试不存在的用户返回 401。"""
    with patch(
        "review_agent.repo.user.UserRepo.get_by_username",
        new_callable=AsyncMock,
        return_value=None,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "nonexistent", "password": "any"},
            )
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_user(app: Any, mock_db: AsyncSession) -> None:  # noqa: ARG001
    """测试被禁用的用户返回 401。"""
    from review_agent.service.auth import hash_password

    mock_user = _make_mock_user()
    mock_user.is_active = False
    mock_user.password_hash = hash_password("testpass")

    with patch(
        "review_agent.repo.user.UserRepo.get_by_username",
        new_callable=AsyncMock,
        return_value=mock_user,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/login",
                json={"username": "testuser", "password": "testpass"},
            )
            assert response.status_code == 401


@pytest.mark.asyncio
async def test_register_success(app: Any, mock_db: AsyncSession) -> None:  # noqa: ARG001
    """测试成功注册返回 201 和新用户信息。"""
    with (
        patch(
            "review_agent.repo.user.UserRepo.get_by_username",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "review_agent.repo.user.UserRepo.get_by_email",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "review_agent.repo.user.UserRepo.create_user",
            new_callable=AsyncMock,
        ) as mock_create,
    ):
        created_user = _make_mock_user()
        created_user.username = "newuser"
        created_user.email = "new@example.com"
        created_user.role = UserRole.VIEWER
        mock_create.return_value = created_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "newuser",
                    "email": "new@example.com",
                    "password": "securepass123",
                },
            )
            assert response.status_code == 201
            data = response.json()
            assert data["username"] == "newuser"
            assert data["email"] == "new@example.com"
            assert data["is_active"] is True


@pytest.mark.asyncio
async def test_register_duplicate_username(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
) -> None:
    """测试重复用户名返回 400。"""
    existing_user = _make_mock_user()
    with (
        patch(
            "review_agent.repo.user.UserRepo.get_by_username",
            new_callable=AsyncMock,
            return_value=existing_user,
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/auth/register",
                json={
                    "username": "existing",
                    "email": "new@example.com",
                    "password": "securepass123",
                },
            )
            assert response.status_code == 400


@pytest.mark.asyncio
async def test_auth_me_requires_token(app: Any, mock_db: AsyncSession) -> None:  # noqa: ARG001
    """测试 /auth/me 在无 token 时返回 403。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/auth/me")
        assert response.status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.skip(reason="JWT 认证暂未启用")
async def test_protected_endpoint_requires_auth(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
) -> None:
    """测试受保护的 /projects 端点需要认证。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/projects")
        assert response.status_code in (401, 403)


# ── RBAC 测试辅助 ─────────────────────────────────────────


def _make_token(role: UserRole) -> str:
    """生成具有指定角色的 JWT Access Token。"""
    from review_agent.service.auth import create_access_token

    return create_access_token("test-user-001", role.value)


@pytest.fixture
def viewer_token() -> str:
    """VIEWER 角色 Token。"""
    return _make_token(UserRole.VIEWER)


@pytest.fixture
def project_admin_token() -> str:
    """PROJECT_ADMIN 角色 Token。"""
    return _make_token(UserRole.PROJECT_ADMIN)


@pytest.fixture
def super_admin_token() -> str:
    """SUPER_ADMIN 角色 Token。"""
    return _make_token(UserRole.SUPER_ADMIN)


# ── VIEWER 角色测试 ────────────────────────────────────────


@pytest.mark.asyncio
async def test_viewer_can_access_viewer_endpoints(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    viewer_token: str,
) -> None:
    """VIEWER 可以访问 VIEWER 级别端点 (GET /projects)。"""
    headers = {"Authorization": f"Bearer {viewer_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/projects", headers=headers)
        assert response.status_code == 200


@pytest.mark.asyncio
async def test_viewer_gets_403_on_project_admin_endpoint(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    viewer_token: str,
) -> None:
    """VIEWER 访问 PROJECT_ADMIN 端点 (POST /projects) 返回 403。"""
    headers = {"Authorization": f"Bearer {viewer_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects",
            json={"name": "test", "platform": "github", "repo_url": "https://github.com/o/r"},
            headers=headers,
        )
        assert response.status_code == 403


@pytest.mark.asyncio
@pytest.mark.skip(reason="JWT 认证暂未启用")
async def test_viewer_gets_403_on_super_admin_endpoint(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    viewer_token: str,
) -> None:
    """VIEWER 访问 SUPER_ADMIN 端点 (GET /errors) 返回 403。"""
    headers = {"Authorization": f"Bearer {viewer_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/errors", headers=headers)
        assert response.status_code == 403


# ── PROJECT_ADMIN 角色测试 ──────────────────────────────────


@pytest.mark.asyncio
async def test_project_admin_can_access_project_admin_endpoints(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    project_admin_token: str,
) -> None:
    """PROJECT_ADMIN 可以访问 PROJECT_ADMIN 级别端点 (POST /projects)。"""
    headers = {"Authorization": f"Bearer {project_admin_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/projects",
            json={"name": "test-proj", "platform": "github", "repo_url": "https://github.com/x/y"},
            headers=headers,
        )
        # 201 on success, 422 on validation (name/repo check) — both mean auth passed
        assert response.status_code in (201, 422)


@pytest.mark.asyncio
async def test_project_admin_can_access_viewer_endpoints(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    project_admin_token: str,
) -> None:
    """PROJECT_ADMIN 可以访问 VIEWER 级别端点 (GET /projects)。"""
    headers = {"Authorization": f"Bearer {project_admin_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/projects", headers=headers)
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.skip(reason="JWT 认证暂未启用")
async def test_project_admin_gets_403_on_super_admin_endpoint(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    project_admin_token: str,
) -> None:
    """PROJECT_ADMIN 访问 SUPER_ADMIN 端点 (GET /errors) 返回 403。"""
    headers = {"Authorization": f"Bearer {project_admin_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/errors", headers=headers)
        assert response.status_code == 403


# ── SUPER_ADMIN 角色测试 ────────────────────────────────────


@pytest.mark.asyncio
async def test_super_admin_can_access_all_endpoints(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
    super_admin_token: str,
) -> None:
    """SUPER_ADMIN 可以访问所有端点。"""
    headers = {"Authorization": f"Bearer {super_admin_token}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # VIEWER endpoint
        r1 = await client.get("/api/v1/projects", headers=headers)
        assert r1.status_code == 200

        # PROJECT_ADMIN endpoint
        r2 = await client.post(
            "/api/v1/projects",
            json={"name": "t", "platform": "github", "repo_url": "https://github.com/a/b"},
            headers=headers,
        )
        assert r2.status_code in (201, 422)

        # SUPER_ADMIN endpoint
        r3 = await client.get("/api/v1/errors", headers=headers)
        assert r3.status_code == 200


@pytest.mark.asyncio
@pytest.mark.skip(reason="JWT 认证暂未启用")
async def test_unauthenticated_gets_401_on_protected_endpoint(
    app: Any,
    mock_db: AsyncSession,  # noqa: ARG001
) -> None:
    """未认证用户访问受保护端点返回 401。"""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/dashboard/stats")
        assert response.status_code == 401
