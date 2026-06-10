"""User Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import UserModel


class UserRepo(BaseRepository[UserModel]):  # type: ignore[misc]
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
