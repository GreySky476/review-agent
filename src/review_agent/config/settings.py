"""应用配置管理。

所有配置项通过环境变量加载（前缀 REVIEW_AGENT_），Pydantic Settings 自动验证。
"""

from __future__ import annotations

import logging

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class AppSettings(BaseSettings):
    """应用全局配置。

    所有配置项前缀为 REVIEW_AGENT_，可通过 .env 文件或环境变量覆盖。
    """

    model_config = SettingsConfigDict(
        env_prefix="REVIEW_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── 应用基础 ──────────────────────────────────────────
    app_name: str = Field(default="review-agent", description="应用名称")
    debug: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别")

    # ── 数据库 ────────────────────────────────────────────
    database_url: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/review_agent",
        description="PostgreSQL 连接串 (async)",
    )

    # ── Redis / 缓存 ─────────────────────────────────────
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis 连接串")

    # ── Arq 任务队列 ──────────────────────────────────────
    arq_redis_url: str = Field(
        default="redis://localhost:6379/1", description="Arq 使用的 Redis 连接串"
    )
    arq_job_retry: int = Field(
        default=3,
        description="ARQ 任务失败最大重试次数",
    )
    arq_job_retry_after: int = Field(
        default=60,
        description="ARQ 任务重试间隔（秒）",
    )

    # ── AI 模型 ──────────────────────────────────────────
    ai_model_name: str = Field(default="deepseek-v4-flash", description="主 AI 模型名称")
    ai_economy_model: str = Field(default="deepseek-v4-flash", description="经济模型名称")
    ai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="嵌入模型名称",
    )
    ai_base_url: str = Field(default="https://api.deepseek.com", description="AI API 基础 URL")
    ai_api_key: SecretStr = Field(
        default=SecretStr(""), description="AI API 密钥（SecretStr 防日志泄漏）"
    )
    ai_request_timeout: int = Field(default=120, description="AI 请求总超时（秒）")
    ai_connect_timeout: int = Field(default=10, description="AI 请求连接超时（秒）")
    ai_read_timeout: int = Field(default=120, description="AI 请求读取超时（秒，含模型推理时间）")
    ai_max_retries: int = Field(default=1, description="AI 请求最大重试次数")
    ai_cb_failure_threshold: int = Field(default=3, description="AI 断路器连续失败阈值")
    ai_cb_recovery_timeout: int = Field(default=60, description="AI 断路器恢复超时（秒）")
    ai_review_max_tokens: int = Field(
        default=32768,
        description="AI 评审最大输出 Token（含推理 Token）",
    )

    # ── 代码分块 ─────────────────────────────────────────
    chunk_normal_max: int = Field(default=1500, description="正常块最大 Token 数")
    chunk_oversized_min: int = Field(default=2000, description="超大块最小 Token 数")
    chunk_context_lines: int = Field(default=200, description="函数上下文上溯行数")

    # ── 评审 ─────────────────────────────────────────────
    review_max_token_per_run: int = Field(default=15_000, description="单次评审 Token 上限")
    review_cache_ttl_days: int = Field(default=7, description="评审结果缓存天数")
    review_skip_extensions: str = Field(
        default=".md,.rst,.txt",
        description="跳过评审的文件扩展名（逗号分隔）",
    )
    review_skip_paths: str = Field(
        default=".claude/**,node_modules/**,__pycache__/**,.git/**,*.md,*.rst,*.txt",
        description="评审跳过的路径模式（逗号分隔，glob 模式），支持 ** 递归匹配",
    )
    ai_batch_max_input_tokens: int = Field(
        default=128000,
        description="单次批量调用的最大预估输入 token，0=禁用批量",
    )
    verbose_report_threshold: int = Field(
        default=5,
        description="触发详细报告的 critical/warning Finding 数量阈值",
    )
    stale_review_timeout_minutes: int = Field(
        default=30,
        description=(
            "评审超时回收时间（分钟）。超过此时间的 PENDING/RUNNING 评审将被自动标记为 FAILED"
        ),
    )

    # ── Git 平台 ─────────────────────────────────────────
    github_token: SecretStr = Field(
        default=SecretStr(""), description="GitHub API Token（SecretStr 防日志泄漏）"
    )

    # ── CORS ──────────────────────────────────────────────
    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:8000"],
        description="CORS 允许的源列表（REVIEW_AGENT_CORS_ORIGINS 为 JSON 数组字符串）",
    )

    # ── Webhook ──────────────────────────────────────────
    webhook_dedup_window: int = Field(default=60, description="Webhook 事件去重窗口（秒）")
    public_url: str = Field(
        default="http://localhost:8000",
        description="服务公网地址（用于 Webhook 连通性验证）",
    )
    # ── Webhook 安全 ──────────────────────────────────────
    webhook_rate_limiter_backend: str = Field(
        default="redis",
        description="Webhook 速率限制后端：redis（推荐，跨进程共享）或 memory（单进程）",
    )
    webhook_ip_whitelist_enabled: bool = Field(
        default=True,
        description="启用 GitHub Webhook IP 白名单检查",
    )
    webhook_rate_limiter_enabled: bool = Field(
        default=True,
        description="启用 Webhook 端点速率限制",
    )

    # ── 健康检查 ─────────────────────────────────────────
    health_check_interval_minutes: int = Field(
        default=5,
        description="平台连通性心跳检测间隔（分钟），设为 0 禁用",
    )
    webhook_health_interval_minutes: int = Field(
        default=5,
        description="Webhook 连接巡检间隔（分钟），与健康检查解耦",
    )

    # ── 报告 ─────────────────────────────────────────────
    report_token_ttl_days: int = Field(default=7, description="报告临时 Token 有效期")

    # ── OpenTelemetry ────────────────────────────────────
    otel_service_name: str = Field(default="review-agent", description="OTel 服务名")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTLP 导出端点",
    )
    otel_enabled: bool = Field(default=True, description="是否启用 OpenTelemetry")

    # ── JWT 认证 ─────────────────────────────────────────
    jwt_secret: str = Field(
        default="dev-jwt-secret-change-me-in-prod-min32",
        min_length=32,
        description="JWT 签名密钥（至少 32 字符）",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT 签名算法")
    jwt_access_token_expire_minutes: int = Field(
        default=30, description="Access Token 有效期（分钟）"
    )
    jwt_refresh_token_expire_days: int = Field(default=7, description="Refresh Token 有效期（天）")


_settings: AppSettings | None = None

_WARNED_KEYS: set[str] = set()


def validate_production_settings(settings: AppSettings) -> None:
    """启动时验证生产环境配置，对不安全配置发出警告。

    仅在首次调用时输出警告，避免重复日志。
    """
    global _WARNED_KEYS  # noqa: PLW0603

    if (
        settings.jwt_secret == "dev-jwt-secret-change-me-in-prod-min32"
        and "jwt" not in _WARNED_KEYS
    ):
        _WARNED_KEYS.add("jwt")
        logger.warning(
            "SECURITY: JWT secret is set to the development default. "
            "Set REVIEW_AGENT_JWT_SECRET to a unique value in production."
        )

    if not settings.ai_api_key.get_secret_value() and "ai" not in _WARNED_KEYS:
        _WARNED_KEYS.add("ai")
        logger.warning("CONFIG: REVIEW_AGENT_AI_API_KEY is empty. AI review calls will fail.")

    if not settings.github_token.get_secret_value() and "github" not in _WARNED_KEYS:
        _WARNED_KEYS.add("github")
        logger.warning(
            "CONFIG: REVIEW_AGENT_GITHUB_TOKEN is empty. "
            "GitHub API calls will use unauthenticated access with low rate limits."
        )


def get_settings() -> AppSettings:
    """获取全局配置单例。"""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = AppSettings()
    return _settings
