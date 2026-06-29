"""Diff 解析工具：从 PR diff patch 中提取变更行范围，映射到函数级别。"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


def extract_changed_lines(patch: str | None) -> set[int] | None:
    """从 git diff patch 中提取新增/修改的行号。

    解析 unified diff 格式的 @@ 头部并追踪新文件行号。

    Args:
        patch: git diff patch 字符串。None 表示无 patch 信息。

    Returns:
        set[int]: 变更行号集合。
        None: patch 为 None（保守处理：视为所有行都变更）。
        set(): patch 存在但无新增行（例如纯删除）。
    """
    if patch is None:
        return None

    changed: set[int] = set()
    # 按行分割，逐行解析
    lines = patch.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        # 匹配 @@ -old,count +new,count @@ 格式
        hdr = re.match(r"^@@\s+-(\d+)(?:,\d+)?\s+\+(\d+)(?:,\d+)?\s+@@", line)
        if hdr:
            new_start = int(hdr.group(2))
            line_num = new_start
            i += 1
            # 遍历 hunk 正文
            while i < len(lines):
                body_line = lines[i]
                # 下一个 @@ 或文件末尾结束
                if body_line.startswith("@@"):
                    break
                if not body_line:
                    i += 1
                    continue
                first_char = body_line[0]
                if first_char == "+":
                    changed.add(line_num)
                    line_num += 1
                elif first_char == " ":
                    line_num += 1
                elif first_char == "-":
                    pass  # 删除行
                elif first_char == "\\":
                    pass  # \ No newline at end of file
                i += 1
            continue
        i += 1

    return changed


def chunk_overlaps(
    chunk_start: int,
    chunk_end: int,
    changed_lines: set[int] | None,
) -> bool:
    """判断函数 chunk 的行范围是否与变更行重叠。

    Args:
        chunk_start: 函数起始行（包含）。
        chunk_end: 函数结束行（包含）。
        changed_lines: 变更行号集合（来自 extract_changed_lines）。

    Returns:
        重叠返回 True，否则 False。
    """
    if changed_lines is None:
        return True  # 无 patch 信息：视为变更
    if not changed_lines:
        return False  # 无新增行：不变
    chunk_range = set(range(chunk_start, chunk_end + 1))
    return bool(chunk_range & changed_lines)


def get_changed_lines_map(files: list[Any]) -> dict[str, set[int] | None]:
    """从 PRFile 列表中构建 文件名 → 变更行号 映射。

    Args:
        files: PRFile 对象列表（需有 filename 和 patch 属性）。

    Returns:
        dict: {filename: set[int] | None}
    """
    result: dict[str, set[int] | None] = {}
    for f in files:
        filename = getattr(f, "filename", None)
        if filename is None:
            filename = getattr(f, "file_path", None)
        if filename is None:
            continue
        patch = getattr(f, "patch", None)
        result[filename] = extract_changed_lines(patch)
    return result
