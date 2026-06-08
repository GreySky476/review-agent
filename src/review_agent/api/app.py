"""FastAPI 应用组装。"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from review_agent.api.commits import router as commits_router
from review_agent.api.dashboard import router as dashboard_router
from review_agent.api.errors import router as errors_router
from review_agent.api.health import router as health_router
from review_agent.api.projects import router as projects_router
from review_agent.api.prs import router as prs_router
from review_agent.api.reviews import router as reviews_router
from review_agent.api.webhook import router as webhook_router
from review_agent.config.logging import setup_logging, setup_opentelemetry
from review_agent.config.settings import get_settings
from review_agent.types.exceptions import (
    ConfigError,
    NotFoundError,
    ReviewAgentError,
    ValidationError,
    WebhookValidationError,
)


def create_app() -> FastAPI:
    """创建并配置 FastAPI 应用实例。"""
    settings = get_settings()
    setup_logging(level=settings.log_level)
    setup_opentelemetry(
        service_name=settings.otel_service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
        enabled=settings.otel_enabled,
    )

    app = FastAPI(title=settings.app_name, version="0.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _register_exception_handlers(app)
    app.include_router(health_router)
    app.include_router(webhook_router, prefix="/webhook")
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(reviews_router, prefix="/api/v1")
    app.include_router(prs_router, prefix="/api/v1")
    app.include_router(commits_router, prefix="/api/v1")
    app.include_router(errors_router, prefix="/api/v1")

    return app


def _register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(ReviewAgentError)
    async def review_agent_error_handler(
        _request: Request, exc: ReviewAgentError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=_status_code(exc),
            content={
                "error": {
                    "code": type(exc).__name__,
                    "message": str(exc),
                    "details": [],
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An unexpected error occurred",
                    "details": [],
                }
            },
        )


def _status_code(exc: ReviewAgentError) -> int:
    """根据异常类型返回 HTTP 状态码。"""
    mapping = {
        ValidationError: 422,
        WebhookValidationError: 403,
        NotFoundError: 404,
        ConfigError: 500,
    }
    for exc_type, code in mapping.items():
        if isinstance(exc, exc_type):
            return code
    return 500


app = create_app()
