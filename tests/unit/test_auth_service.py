"""Tests for auth service: password hashing, token creation/verification."""

import os

import pytest

# Ensure JWT secret is set before importing auth modules
os.environ["REVIEW_AGENT_JWT_SECRET"] = "a-test-secret-key-that-is-at-least-32-chars-long"  # noqa: S105

from review_agent.service.auth import (  # noqa: E402
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    """密码哈希和验证测试。"""

    def test_hash_returns_different_values(self) -> None:
        """每次哈希应产生不同的盐值。"""
        h1 = hash_password("password123")
        h2 = hash_password("password123")
        assert h1 != h2

    def test_verify_correct_password(self) -> None:
        """验证正确密码应返回 True。"""
        h = hash_password("my-secret")
        assert verify_password("my-secret", h) is True

    def test_verify_wrong_password(self) -> None:
        """验证错误密码应返回 False。"""
        h = hash_password("my-secret")
        assert verify_password("wrong-password", h) is False

    def test_hash_is_bcrypt_format(self) -> None:
        """哈希值应为 bcrypt 格式。"""
        h = hash_password("test")
        assert h.startswith("$2b$")


class TestJwtTokens:
    """JWT 令牌创建和验证测试。"""

    def test_create_and_decode_access_token(self) -> None:
        """创建的 access token 应能成功解码。"""
        token = create_access_token("user-123", "super_admin")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "super_admin"
        assert payload["type"] == "access"
        assert "exp" in payload
        assert "iat" in payload

    def test_create_and_decode_refresh_token(self) -> None:
        """创建的 refresh token 应能成功解码。"""
        token = create_refresh_token("user-456")
        payload = decode_token(token)
        assert payload["sub"] == "user-456"
        assert payload["type"] == "refresh"
        assert "exp" in payload

    def test_decode_expired_token(self) -> None:
        """过期 token 应抛出 ExpiredSignatureError。"""
        from datetime import UTC, datetime, timedelta

        import jwt

        from review_agent.config.settings import get_settings

        settings = get_settings()
        now = datetime.now(UTC)
        payload = {
            "sub": "user-1",
            "type": "access",
            "role": "viewer",
            "iat": now - timedelta(hours=1),
            "exp": now - timedelta(seconds=1),
        }
        expired_token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_token(expired_token)

    def test_decode_invalid_token(self) -> None:
        """无效 token 应抛出 InvalidTokenError。"""
        import jwt

        with pytest.raises(jwt.InvalidTokenError):
            decode_token("invalid-token-string")

    def test_decode_token_wrong_secret(self) -> None:
        """用错误密钥创建的 token 应验证失败。"""
        import jwt

        payload = {"sub": "user-1", "type": "access", "role": "viewer"}
        wrong_token = jwt.encode(
            payload, "wrong-secret-key-that-should-not-match", algorithm="HS256"
        )
        with pytest.raises(jwt.InvalidTokenError):
            decode_token(wrong_token)
