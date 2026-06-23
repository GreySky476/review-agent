"""评审服务共享工具函数。"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any

from review_agent.config.settings import get_settings

logger = logging.getLogger(__name__)


def parse_skip_patterns() -> list[str]:
    """从全局配置解析跳过路径模式列表。"""
    settings = get_settings()
    return [p.strip() for p in settings.review_skip_paths.split(",") if p.strip()]


def should_skip_file(filename: str, skip_patterns: list[str] | None = None) -> bool:
    """按路径模式判断是否跳过评审。

    支持的模式：
    - ``.claude/**`` → 目录前缀匹配（匹配 .claude/ 下所有文件）
    - ``*.md`` → 扩展名匹配
    - ``fnmatch`` 完整模式
    """
    patterns = skip_patterns if skip_patterns is not None else parse_skip_patterns()
    for pattern in patterns:
        if pattern.endswith("/**"):
            if filename.startswith(pattern[:-3]):
                return True
        elif pattern.startswith("*.") and "/" not in pattern:
            if filename.endswith(pattern[1:]):
                return True
        else:
            if fnmatch.fnmatch(filename, pattern):
                return True
    return False


def compute_reviewed_files(
    new_chunks: list[Any],
    findings: list[Any],
) -> list[dict[str, str | None]]:
    """从评审结果计算 reviewed_files。

    对每个被评审的文件，记录其最高严重级别：
    - critical > warning > info > None（无问题）

    Args:
        new_chunks: 本次实际评审的 chunk 列表。
        findings: 本次评审产出的 DimensionFinding 列表。

    Returns:
        list[dict]: [{"path": "src/a.py", "max_severity": "critical"}, ...]
    """
    file_max_sev: dict[str, str | None] = {}
    for chunk in new_chunks:
        file_max_sev[chunk.file_path] = None  # 默认无问题

    for finding in findings:
        path = finding.file_path
        current = file_max_sev.get(path)
        sev = finding.severity.value if hasattr(finding.severity, "value") else finding.severity
        if current is None or current == "info":
            if sev == "critical":
                file_max_sev[path] = "critical"
            elif sev == "warning" and current != "critical":
                file_max_sev[path] = "warning"
            elif sev == "info" and current is None:
                file_max_sev[path] = "info"

    return [{"path": p, "max_severity": s} for p, s in file_max_sev.items()]
