"""User Session Repository。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import delete, select, update

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import UserSessionModel


class UserSessionRepo(BaseRepository):  # type: ignore[misc]
    """用户登录会话仓库。

    管理 JWT 刷新令牌对应的会话记录，支持创建、吊销、查询和过期清理。
    """

    @property
    def _model(self) -> type[UserSessionModel]:
        return UserSessionModel  # type: ignore[no-any-return]

    async def create_session(
        self,
        user_id: str,
        token_hash: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        expires_at: datetime | None = None,
    ) -> UserSessionModel:
        """创建一条登录会话记录。

        Args:
            user_id: 用户 ID。
            token_hash: 刷新令牌的 SHA-256 哈希值。
            ip_address: 客户端 IP 地址。
            user_agent: 客户端 User-Agent。
            expires_at: 会话过期时间。

        Returns:
            已创建的会话实例。
        """
        if expires_at is None:
            expires_at = datetime.now(UTC) + timedelta(days=7)
        return await self.create(
            user_id=user_id,
            token_hash=token_hash,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )

    async def revoke_all_for_user(self, user_id: str) -> None:
        """吊销指定用户的所有活跃会话。

        Args:
            user_id: 用户 ID。
        """
        stmt = (
            update(UserSessionModel)
            .where(
                UserSessionModel.user_id == user_id,
                UserSessionModel.is_revoked.is_(False),
            )
            .values(is_revoked=True)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def list_active_for_user(self, user_id: str) -> list[UserSessionModel]:
        """查询指定用户的所有活跃会话。

        Args:
            user_id: 用户 ID。

        Returns:
            未吊销且未过期的会话列表。
        """
        stmt = select(UserSessionModel).where(
            UserSessionModel.user_id == user_id,
            UserSessionModel.is_revoked.is_(False),
            UserSessionModel.expires_at > datetime.now(UTC),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def purge_expired(self) -> int:
        """删除所有已过期的会话记录。

        Returns:
            删除的会话数量。
        """
        stmt = delete(UserSessionModel).where(UserSessionModel.expires_at <= datetime.now(UTC))
        result = await self._db.execute(stmt)
        await self._db.flush()
        return cast(int, result.rowcount)
