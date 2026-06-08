"""健康检查端点。"""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def health_check() -> dict[str, str]:
    """健康检查。"""
    return {"status": "ok"}
