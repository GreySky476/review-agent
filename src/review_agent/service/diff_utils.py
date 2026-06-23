"""Diff 解析工具函数。"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_changed_lines(patch: str | None) -> set[int] | None:
    """解析 unified diff，提取新文件中被新增/修改行的行号集合。

    返回 None 表示没有 patch（应评审全部 chunk），
    返回空集合表示 patch 中无增加行（跳过所有 chunk 的 AI 评审）。
    """
    if not patch:
        return None

    changed: set[int] = set()
    current_new_line: int | None = None
    has_hunk = False

    for line in patch.split("\n"):
        hunk_match = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
        if hunk_match:
            current_new_line = int(hunk_match.group(1))
            has_hunk = True
            continue
        if current_new_line is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            changed.add(current_new_line)
            current_new_line += 1
        elif line.startswith("-"):
            continue  # 已删除的行，不推进行号
        elif line == r"\ No newline at end of file":
            continue  # 非实际内容行
        else:
            current_new_line += 1  # 上下文行

    # patch 有内容但无法解析 hunk header（如非标准格式），退回全量评审
    if not has_hunk:
        return None

    return changed


def chunk_overlaps(chunk: Any, changed_lines: set[int]) -> bool:
    """判断 chunk 的行范围是否与任何改动行重叠。"""
    if not changed_lines:
        return False
    start = getattr(chunk, "start_line", None)
    end = getattr(chunk, "end_line", None)
    if start is None or end is None:
        return True  # 无法判断时退回全量
    min_ln = min(changed_lines)
    max_ln = max(changed_lines)
    return bool(end >= min_ln and start <= max_ln)
