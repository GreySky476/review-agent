"""认证 REST API 端点：登录、注册、刷新、登出、获取当前用户。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.dependencies.auth import get_current_user
from review_agent.config.database import get_session
from review_agent.config.settings import get_settings
from review_agent.service.auth import (
    _token_hash,
    authenticate_user,
    create_access_token,
    create_refresh_session,
    create_refresh_token,
    decode_token,
    get_user_by_id,
    list_active_sessions,
    register_user,
    revoke_user_sessions,
    update_last_login,
)
from review_agent.types.exceptions import ValidationError
from review_agent.types.models import (
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


def _build_user_response(user: Any) -> UserResponse:
    """将 ORM 用户模型转换为 Pydantic 响应模型。

    Args:
        user: ORM UserModel 实例。

    Returns:
        UserResponse Pydantic 模型。
    """
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role.value if hasattr(user.role, "value") else str(user.role),
        is_active=user.is_active,
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(
    body: UserLogin,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """用户登录。

    验证用户名和密码，返回 access token 和 refresh token。

    Args:
        body: 登录请求体（用户名、密码）。
        db: 数据库会话。

    Returns:
        TokenResponse 包含 access_token、refresh_token 和过期信息。

    Raises:
        HTTPException 401: 用户名或密码错误，或账号已禁用。
    """
    user = await authenticate_user(db, body.username, body.password)
    if user is None:
        # 尝试通过用户名查询，判断具体失败原因（避免信息泄露，统一返回 401）
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号已被禁用",
        )

    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    access_token = create_access_token(user.id, role_value)
    refresh_token = create_refresh_token(user.id)
    settings = get_settings()

    # 创建刷新令牌会话记录
    await create_refresh_session(
        db,
        user_id=user.id,
        token_hash=_token_hash(refresh_token),
    )

    # 更新最后登录时间
    await update_last_login(db, user.id)

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/auth/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(
    body: UserCreate,
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    """注册新用户。

    Args:
        body: 注册请求体。
        db: 数据库会话。

    Returns:
        UserResponse 包含新用户信息。

    Raises:
        HTTPException 400: 用户名或邮箱已被占用。
    """
    try:
        user = await register_user(
            db,
            username=body.username,
            email=body.email,
            password=body.password,
            display_name=body.display_name,
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    return _build_user_response(user)


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh(
    body: TokenRefresh,
    db: AsyncSession = Depends(get_session),
) -> TokenResponse:
    """使用 Refresh Token 刷新 Access Token。

    验证 refresh token，吊销旧会话，签发新令牌对。

    Args:
        body: 刷新请求体。
        db: 数据库会话。

    Returns:
        新的 TokenResponse。

    Raises:
        HTTPException 401: refresh token 无效、过期或已被吊销。
    """
    try:
        payload = decode_token(body.refresh_token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或已过期的 Refresh Token",
        ) from None

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌类型不正确，请使用 Refresh Token",
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="令牌缺少用户标识",
        )

    # 验证会话存在且未被吊销
    token_hash = _token_hash(body.refresh_token)
    active_sessions = await list_active_sessions(db, user_id)
    matching_session = None
    for s in active_sessions:
        if s.token_hash == token_hash:
            matching_session = s
            break

    if matching_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token 已被吊销或过期",
        )

    # 吊销旧刷新令牌会话（token rotation）
    await revoke_user_sessions(db, user_id)

    # 获取用户角色
    user = await get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    role_value = user.role.value if hasattr(user.role, "value") else str(user.role)
    new_access_token = create_access_token(user_id, role_value)
    new_refresh_token = create_refresh_token(user_id)
    settings = get_settings()

    # 创建新的刷新令牌会话
    await create_refresh_session(
        db,
        user_id=user_id,
        token_hash=_token_hash(new_refresh_token),
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",  # noqa: S106
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/auth/logout")
async def logout(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """登出当前用户。

    吊销当前用户的所有活跃会话。

    Args:
        current_user: 当前认证用户信息。
        db: 数据库会话。

    Returns:
        登出成功确认。
    """
    user_id = current_user["user_id"]
    await revoke_user_sessions(db, user_id)
    return {"message": "已成功登出"}


@router.get("/auth/me", response_model=UserResponse)
async def get_me(
    current_user: dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
) -> UserResponse:
    """获取当前登录用户信息。

    Args:
        current_user: 当前认证用户信息。
        db: 数据库会话。

    Returns:
        UserResponse 当前用户详细信息。
    """
    user = await get_user_by_id(db, current_user["user_id"])
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在",
        )
    return _build_user_response(user)
