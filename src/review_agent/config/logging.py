"""日志与 OpenTelemetry 追踪配置。

结构化 JSON 日志，所有日志行携带 trace_id 用于全链路追踪。
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class StructuredJSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式化器。"""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
        }
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    """配置全局日志。

    Args:
        level: 日志级别字符串（DEBUG/INFO/WARNING/ERROR）。
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    handler.setLevel(level.upper())

    root_logger = logging.getLogger()
    root_logger.setLevel(level.upper())
    # 清除已有 handler，避免重复添加
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # 关闭第三方库的噪音日志
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def setup_opentelemetry(
    service_name: str,
    endpoint: str,
    enabled: bool = False,
    app: Any = None,
) -> None:
    """初始化 OpenTelemetry。

    Args:
        service_name: 服务名（用于在追踪系统中标识）。
        endpoint: OTLP HTTP 导出端点。
        enabled: 是否启用导出。False 时跳过所有初始化。
        app: 可选 FastAPI 应用实例。传入后自动注册 FastAPI 仪表。
    """
    if not enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to setup OpenTelemetry: %s", exc)
        return

    # FastAPI 仪表（lazy import）
    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
            logging.getLogger(__name__).info("OpenTelemetry: FastAPI instrumented")
        except Exception as exc:
            logging.getLogger(__name__).warning("Failed to instrument FastAPI: %s", exc)

    # httpx 仪表（lazy import）
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        logging.getLogger(__name__).info("OpenTelemetry: httpx instrumented")
    except Exception as exc:
        logging.getLogger(__name__).warning("Failed to instrument httpx: %s", exc)
