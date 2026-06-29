"""用户相关 Pydantic 模型。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from review_agent.types.enums import UserRole


class User(BaseModel):
    """管理后台用户。"""

    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(default_factory=uuid4)
    username: str
    email: str
    role: UserRole = UserRole.VIEWER
    is_active: bool = True
    is_deleted: bool = False
    create_time: datetime | None = None
    update_time: datetime | None = None


class UserLogin(BaseModel):
    """用户登录请求。"""

    username: str
    password: str


class UserCreate(BaseModel):
    """创建用户请求。"""

    username: str = Field(min_length=3, max_length=128)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = ""


class TokenResponse(BaseModel):
    """JWT Token 响应。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105
    expires_in: int


class TokenRefresh(BaseModel):
    """Token 刷新请求。"""

    refresh_token: str


class UserResponse(BaseModel):
    """用户信息响应（不含敏感数据）。"""

    id: str
    username: str
    email: str
    role: str
    is_active: bool
