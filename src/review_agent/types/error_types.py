"""企业级错误分类枚举。

定义 ReviewAgent 系统中所有标准化的错误类型。
每个类型映射到特定的故障域，用于驱动告警路由、聚合分析和 UI 展示。
"""

from __future__ import annotations

from enum import StrEnum


class ErrorType(StrEnum):
    """标准化错误分类。

    命名规则：<domain>_<failure>（全小写蛇形）。
    """

    GIT_API_FAILED = "git_api_failed"
    """GitHub API 调用失败（PR 信息、diff 拉取、webhook 检查等）。"""

    GIT_FILE_FETCH_FAILED = "git_file_fetch_failed"
    """get_file_content 返回 None 或抛出异常（文件不存在 / 网络错误）。"""

    AI_CALL_FAILED = "ai_call_failed"
    """AI Provider 调用超时、返回错误、或无效响应。"""

    PIPELINE_CRASHED = "pipeline_crashed"
    """LangGraph 流水线节点未捕获异常（完整评审失败）。"""

    PIPELINE_PARTIAL_FAILURE = "pipeline_partial_failure"
    """流水线部分文件未能完成评审（COMPLETED_WITH_ERRORS）。"""

    WEBHOOK_PARSE_FAILED = "webhook_parse_failed"
    """Webhook 负载解析失败（JSON 格式错误 / 项目映射失败）。"""

    WEBHOOK_VERIFY_FAILED = "webhook_verify_failed"
    """Webhook 签名验证失败。"""

    QUEUE_ENQUEUE_FAILED = "queue_enqueue_failed"
    """评审任务入队失败（ARQ 队列异常）。"""

    DB_WRITE_FAILED = "db_write_failed"
    """数据库持久化写入失败。"""

    PUBLISH_FAILED = "publish_failed"
    """GitHub 评论发布失败（摘要 / 行内评论）。"""

    UNKNOWN = "unknown"
    """未分类错误兜底。"""
