"""认证服务：密码哈希、JWT 令牌创建/验证、用户注册/登录。"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.settings import get_settings
from review_agent.repo.user import UserRepo
from review_agent.repo.user_session import UserSessionRepo
from review_agent.types.exceptions import ValidationError
from review_agent.types.orm import UserModel, UserSessionModel

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """使用 bcrypt 哈希密码。

    Args:
        password: 明文密码。

    Returns:
        bcrypt 哈希字符串。
    """
    return cast(str, _pwd_context.hash(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码是否匹配哈希值。

    Args:
        plain_password: 明文密码。
        hashed_password: bcrypt 哈希值。

    Returns:
        密码匹配返回 True，否则返回 False。
    """
    return cast(bool, _pwd_context.verify(plain_password, hashed_password))


def _token_hash(token: str) -> str:
    """计算令牌的 SHA-256 哈希值（用于会话表存储）。

    Args:
        token: JWT 令牌字符串。

    Returns:
        十六进制哈希字符串。
    """
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """创建 JWT Access Token。

    Args:
        user_id: 用户 ID。
        role: 用户角色。
        expires_delta: 自定义过期时间，默认使用配置中的值。

    Returns:
        JWT 令牌字符串。
    """
    settings = get_settings()
    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: str) -> str:
    """创建 JWT Refresh Token。

    Args:
        user_id: 用户 ID。

    Returns:
        JWT 令牌字符串。
    """
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """验证并解码 JWT 令牌。

    Args:
        token: JWT 令牌字符串。

    Returns:
        解码后的令牌载荷字典。

    Raises:
        jwt.ExpiredSignatureError: 令牌已过期。
        jwt.InvalidTokenError: 令牌无效。
    """
    settings = get_settings()
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub", "type"]},
    )


async def authenticate_user(
    db: AsyncSession,
    username: str,
    password: str,
) -> UserModel | None:
    """验证用户凭据。

    Args:
        db: 数据库会话。
        username: 用户名。
        password: 明文密码。

    Returns:
        验证成功返回 UserModel，失败返回 None。
    """
    repo = UserRepo(db)
    user = await repo.get_by_username(username)
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def register_user(
    db: AsyncSession,
    username: str,
    email: str,
    password: str,
    display_name: str = "",
) -> UserModel:
    """注册新用户。

    检查用户名和邮箱唯一性，哈希密码后创建用户。

    Args:
        db: 数据库会话。
        username: 用户名。
        email: 邮箱地址。
        password: 明文密码。
        display_name: 显示名称。

    Returns:
        已创建的用户 ORM 实例。

    Raises:
        ValidationError: 用户名或邮箱已被占用。
    """
    repo = UserRepo(db)
    existing = await repo.get_by_username(username)
    if existing is not None:
        msg = f"用户名已被占用: {username}"
        raise ValidationError(msg)
    existing = await repo.get_by_email(email)
    if existing is not None:
        msg = f"邮箱已被占用: {email}"
        raise ValidationError(msg)
    password_hash = hash_password(password)
    return await repo.create_user(
        username=username,
        email=email,
        password_hash=password_hash,
        display_name=display_name,
    )


# ── API 层包装函数 ─────────────────────────────────────────


async def get_user_by_id(db: AsyncSession, user_id: str) -> UserModel | None:
    """根据用户 ID 获取用户（供 API 层调用）。

    Args:
        db: 数据库会话。
        user_id: 用户 ID。

    Returns:
        用户 ORM 实例，未找到时返回 None。
    """
    repo = UserRepo(db)
    return await repo.get(user_id)


async def update_last_login(db: AsyncSession, user_id: str) -> UserModel:
    """更新用户最后登录时间（供 API 层调用）。

    Args:
        db: 数据库会话。
        user_id: 用户 ID。

    Returns:
        更新后的用户 ORM 实例。
    """
    repo = UserRepo(db)
    return await repo.update_last_login(user_id)


async def create_refresh_session(
    db: AsyncSession,
    user_id: str,
    token_hash: str,
) -> UserSessionModel:
    """创建刷新令牌会话记录（供 API 层调用）。

    Args:
        db: 数据库会话。
        user_id: 用户 ID。
        token_hash: 令牌的 SHA-256 哈希。

    Returns:
        创建的会话 ORM 实例。
    """
    repo = UserSessionRepo(db)
    return await repo.create_session(user_id=user_id, token_hash=token_hash)


async def list_active_sessions(db: AsyncSession, user_id: str) -> list[UserSessionModel]:
    """获取用户所有活跃会话（供 API 层调用）。

    Args:
        db: 数据库会话。
        user_id: 用户 ID。

    Returns:
        活跃会话 ORM 实例列表。
    """
    repo = UserSessionRepo(db)
    return cast(list[Any], await repo.list_active_for_user(user_id))


async def revoke_user_sessions(db: AsyncSession, user_id: str) -> None:
    """吊销用户所有活跃会话（供 API 层调用）。

    Args:
        db: 数据库会话。
        user_id: 用户 ID。
    """
    repo = UserSessionRepo(db)
    await repo.revoke_all_for_user(user_id)
