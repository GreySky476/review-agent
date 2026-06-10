"""Tests for config module: settings."""

from review_agent.config.settings import get_settings


class TestSettings:
    """配置加载测试。"""

    def test_settings_uses_defaults(self) -> None:
        """未设置环境变量时使用默认值。"""
        s = get_settings()
        assert s.app_name == "review-agent"
        assert s.debug is False
        assert s.log_level == "INFO"
        assert s.chunk_normal_max == 1500
        assert s.chunk_oversized_min == 2000
        assert s.verbose_report_threshold == 5
        assert s.review_cache_ttl_days == 7
        assert s.webhook_dedup_window == 60

    def test_settings_is_singleton(self) -> None:
        """get_settings 应返回同一实例。"""
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
