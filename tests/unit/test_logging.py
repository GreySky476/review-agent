"""Tests for config/logging module."""

import json
import logging
from io import StringIO

from review_agent.config.logging import (
    StructuredJSONFormatter,
    setup_logging,
    setup_opentelemetry,
)


class TestStructuredJSONFormatter:
    """JSON 格式化器测试。"""

    def setup_method(self) -> None:
        self.formatter = StructuredJSONFormatter()
        self.logger = logging.getLogger("test_logger")
        self.logger.setLevel(logging.DEBUG)

    def test_formatter_outputs_valid_json(self) -> None:
        """格式化输出应为合法 JSON。"""
        record = self.logger.makeRecord(
            name="test",
            level=logging.INFO,
            fn="test.py",
            lno=1,
            msg="hello world",
            args=(),
            exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"
        assert parsed["name"] == "test"

    def test_formatter_includes_trace_id(self) -> None:
        """trace_id 字段应被包含。"""
        record = self.logger.makeRecord(
            name="test",
            level=logging.INFO,
            fn="test.py",
            lno=1,
            msg="test",
            args=(),
            exc_info=None,
        )
        record.trace_id = "abc123"  # type: ignore[attr-defined]
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["trace_id"] == "abc123"


class TestSetupLogging:
    """setup_logging 测试。"""

    def test_setup_logging_creates_handler(self) -> None:
        """配置日志后应有 StreamHandler。"""
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    def test_setup_logging_replaces_handlers(self) -> None:
        """重复调用应替换已有 handler。"""
        setup_logging(level="INFO")
        count_before = len(logging.getLogger().handlers)
        setup_logging(level="DEBUG")
        count_after = len(logging.getLogger().handlers)
        assert count_after == count_before


class TestSetupOpenTelemetry:
    """OpenTelemetry 配置测试。"""

    def test_disabled_otel_does_nothing(self) -> None:
        """otel_enabled=False 时不应崩溃。"""
        setup_opentelemetry("test-service", "http://localhost:4318", enabled=False)
        # 不应抛出异常
        assert True
