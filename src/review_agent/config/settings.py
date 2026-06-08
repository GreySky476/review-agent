"""应用配置管理。

所有配置项通过环境变量加载（前缀 REVIEW_AGENT_），Pydantic Settings 自动验证。
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # ── AI 模型 ──────────────────────────────────────────
    ai_model_name: str = Field(default="deepseek-v4-flash", description="主 AI 模型名称")
    ai_economy_model: str = Field(default="deepseek-v4-flash", description="经济模型名称")
    ai_base_url: str = Field(default="https://api.deepseek.com", description="AI API 基础 URL")
    ai_api_key: str = Field(default="", description="AI API 密钥")
    ai_request_timeout: int = Field(default=30, description="AI 请求超时（秒）")
    ai_max_retries: int = Field(default=1, description="AI 请求最大重试次数")

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
    verbose_report_threshold: int = Field(
        default=5,
        description="触发详细报告的 critical/warning Finding 数量阈值",
    )

    # ── Git 平台 ─────────────────────────────────────────
    github_token: str = Field(default="", description="GitHub API Token")

    # ── Webhook ──────────────────────────────────────────
    webhook_dedup_window: int = Field(default=60, description="Webhook 事件去重窗口（秒）")

    # ── 报告 ─────────────────────────────────────────────
    report_token_ttl_days: int = Field(default=7, description="报告临时 Token 有效期")

    # ── OpenTelemetry ────────────────────────────────────
    otel_service_name: str = Field(default="review-agent", description="OTel 服务名")
    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description="OTLP 导出端点",
    )
    otel_enabled: bool = Field(default=False, description="是否启用 OpenTelemetry")


_settings: AppSettings | None = None


def get_settings() -> AppSettings:
    """获取全局配置单例。"""
    global _settings  # noqa: PLW0603
    if _settings is None:
        _settings = AppSettings()
    return _settings
