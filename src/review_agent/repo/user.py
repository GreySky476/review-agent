"""User Repository。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import UserModel


class UserRepo(BaseRepository):  # type: ignore[misc]
    """用户仓库 CRUD。"""

    @property
    def _model(self) -> type[UserModel]:
        return UserModel  # type: ignore[no-any-return]

    async def get_by_username(self, username: str) -> UserModel | None:
        """按用户名查询用户。"""
        stmt = select(UserModel).where(
            UserModel.username == username,
            UserModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> UserModel | None:
        """按邮箱查询用户。"""
        stmt = select(UserModel).where(
            UserModel.email == email,
            UserModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_user(
        self,
        username: str,
        email: str,
        password_hash: str,
        display_name: str = "",
    ) -> UserModel:
        """创建新用户。

        Args:
            username: 用户名（唯一）。
            email: 邮箱地址（唯一）。
            password_hash: 已哈希的密码。
            display_name: 显示名称。

        Returns:
            已创建的用户 ORM 实例。
        """
        return await self.create(
            username=username,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
        )

    async def update_password(self, user_id: str, new_password_hash: str) -> UserModel:
        """更新用户密码。

        Args:
            user_id: 用户 ID。
            new_password_hash: 新的哈希密码。

        Returns:
            更新后的用户实例。
        """
        return await self.update(user_id, password_hash=new_password_hash)

    async def update_last_login(self, user_id: str) -> UserModel:
        """更新用户最后登录时间。

        Args:
            user_id: 用户 ID。

        Returns:
            更新后的用户实例。
        """
        return await self.update(user_id, last_login_at=datetime.now(UTC))
