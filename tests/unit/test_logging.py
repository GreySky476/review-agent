"""Tests for config/logging module."""

import json
import logging
from unittest.mock import MagicMock, patch

from review_agent.config.logging import StructuredJSONFormatter, setup_logging, setup_opentelemetry


class TestStructuredJSONFormatter:
    """JSON 格式化器测试。"""

    def setup_method(self):
        self.formatter = StructuredJSONFormatter()
        self.logger = logging.getLogger("test_logger")
        self.logger.setLevel(logging.DEBUG)

    def test_formatter_outputs_valid_json(self):
        record = self.logger.makeRecord(
            name="test", level=logging.INFO, fn="test.py", lno=1,
            msg="hello world", args=(), exc_info=None,
        )
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["message"] == "hello world"

    def test_formatter_includes_trace_id(self):
        record = self.logger.makeRecord(
            name="test", level=logging.INFO, fn="test.py", lno=1,
            msg="test", args=(), exc_info=None,
        )
        record.trace_id = "abc123"
        output = self.formatter.format(record)
        parsed = json.loads(output)
        assert parsed["trace_id"] == "abc123"


class TestSetupLogging:
    def test_setup_logging_creates_handler(self):
        setup_logging(level="DEBUG")
        root = logging.getLogger()
        assert any(isinstance(h, logging.StreamHandler) for h in root.handlers)

    def test_setup_logging_replaces_handlers(self):
        setup_logging(level="INFO")
        count_before = len(logging.getLogger().handlers)
        setup_logging(level="DEBUG")
        count_after = len(logging.getLogger().handlers)
        assert count_after == count_before


class TestSetupOpenTelemetry:
    def test_disabled_otel_does_nothing(self):
        setup_opentelemetry("test", "http://localhost:4318", enabled=False)
        assert True

    def test_enabled_otel_initializes_provider(self):
        mock_trace = MagicMock()
        mock_resource = MagicMock()
        mock_tp = MagicMock()
        mock_exporter = MagicMock()
        with (
            patch("opentelemetry.trace", mock_trace),
            patch("opentelemetry.sdk.resources.Resource", mock_resource),
            patch("opentelemetry.sdk.trace.TracerProvider", mock_tp),
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", mock_exporter),
        ):
            setup_opentelemetry("test", "http://localhost:4318", enabled=True)
            mock_tp.assert_called_once()
            mock_exporter.assert_called_once()
            mock_trace.set_tracer_provider.assert_called_once()

    def test_fastapi_instrumentation(self):
        mock_fastapi_instr = MagicMock()
        with (
            patch("opentelemetry.trace", MagicMock()),
            patch("opentelemetry.sdk.resources.Resource", MagicMock()),
            patch("opentelemetry.sdk.trace.TracerProvider", MagicMock()),
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", MagicMock()),
            patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor", mock_fastapi_instr),
        ):
            mock_app = MagicMock()
            setup_opentelemetry("test", "http://localhost:4318", enabled=True, app=mock_app)
            mock_fastapi_instr.instrument_app.assert_called_once_with(mock_app)

    def test_httpx_instrumentation(self):
        mock_httpx_cls = MagicMock()
        mock_httpx_inst = MagicMock()
        mock_httpx_cls.return_value = mock_httpx_inst
        with (
            patch("opentelemetry.trace", MagicMock()),
            patch("opentelemetry.sdk.resources.Resource", MagicMock()),
            patch("opentelemetry.sdk.trace.TracerProvider", MagicMock()),
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", MagicMock()),
            patch("opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor", mock_httpx_cls),
        ):
            setup_opentelemetry("test", "http://localhost:4318", enabled=True)
            mock_httpx_cls.assert_called_once()
            mock_httpx_inst.instrument.assert_called_once()

    def test_instrumentation_failure_does_not_crash(self):
        mock_fi = MagicMock()
        mock_fi.instrument_app.side_effect = RuntimeError("boom")
        mock_hc = MagicMock()
        mock_hi = MagicMock()
        mock_hi.instrument.side_effect = RuntimeError("boom")
        mock_hc.return_value = mock_hi
        with (
            patch("opentelemetry.trace", MagicMock()),
            patch("opentelemetry.sdk.resources.Resource", MagicMock()),
            patch("opentelemetry.sdk.trace.TracerProvider", MagicMock()),
            patch("opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter", MagicMock()),
            patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor", mock_fi),
            patch("opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor", mock_hc),
        ):
            setup_opentelemetry("test", "http://localhost:4318", enabled=True, app=MagicMock())
            assert True
