"""超大块结构评审。

对超过 Token 阈值的函数进行结构评审，计算圈复杂度、行数、参数数、
嵌套层级等指标，并执行最小化安全检查。
"""

from __future__ import annotations

from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.types.enums import FindingCategory, FindingSeverity


def _calculate_complexity(code: str) -> int:
    """估算圈复杂度（McCabe）。

    计数 if/elif/for/while/and/or/except 的数量 + 1。
    """
    complexity = 1
    for keyword in ["if ", "elif ", "for ", "while ", "and ", "or ", "except "]:
        complexity += code.count(keyword)
    return complexity


def _estimate_nesting_depth(code: str) -> int:
    """估算最大嵌套深度（基于缩进）。"""
    max_depth = 0
    for line in code.split("\n"):
        stripped = line.rstrip()
        if not stripped or stripped.startswith(("#", '"""', "'''")):
            continue
        depth = len(line) - len(line.lstrip())
        # 每 4 空格算一层
        level = depth // 4
        if level > max_depth:
            max_depth = level
    return max_depth


def _count_params(code: str, function_name: str) -> int:
    """从函数签名中统计参数数量。"""
    import re

    # 匹配 def func_name(param1, param2, ...)
    pattern = rf"def\s+{re.escape(function_name)}\s*\(([^)]*)\)"
    match = re.search(pattern, code)
    if match:
        params_str = match.group(1).strip()
        if not params_str:
            return 0
        # 过滤掉 self 和 cls
        params = [p.strip() for p in params_str.split(",") if p.strip()]
        return len([p for p in params if p not in ("self", "cls")])
    return 0


async def review_structure(chunk: CodeChunk) -> list[DimensionFinding]:
    """对超大块执行结构评审。

    检查项：
    1. 圈复杂度（阈值 20）
    2. 函数行数（阈值 200）
    3. 参数数量（阈值 5）
    4. 嵌套层级
    5. 最小化安全检查（eval/exec/os.system）

    Args:
        chunk: 超大代码块。

    Returns:
        结构评审 Findings。
    """
    findings: list[DimensionFinding] = []
    code = chunk.source_code
    lines = code.split("\n")
    line_count = len(lines)

    # 1. 圈复杂度
    complexity = _calculate_complexity(code)
    if complexity > 20:
        findings.append(
            DimensionFinding(
                category=FindingCategory.STRUCTURE,
                severity=FindingSeverity.WARNING,
                title=f"圈复杂度过高 ({complexity})",
                description=f"函数 `{chunk.function_name}` 圈复杂度为 {complexity}，超过阈值 20",
                suggestion="建议拆分函数，减少条件分支和循环嵌套，可将条件逻辑提取为独立函数",
                file_path=chunk.file_path,
                line_start=chunk.start_line,
                line_end=chunk.end_line,
            )
        )

    # 2. 函数行数
    if line_count > 200:
        findings.append(
            DimensionFinding(
                category=FindingCategory.STRUCTURE,
                severity=FindingSeverity.WARNING,
                title=f"函数行数超限 ({line_count})",
                description=f"函数 `{chunk.function_name}` 共 {line_count} 行，超过阈值 200",
                suggestion="建议将函数拆分为多个小函数，每个函数聚焦于单一职责",
                file_path=chunk.file_path,
                line_start=chunk.start_line,
                line_end=chunk.end_line,
            )
        )

    # 3. 参数数量
    params = _count_params(code, chunk.function_name)
    if params > 5:
        findings.append(
            DimensionFinding(
                category=FindingCategory.STRUCTURE,
                severity=FindingSeverity.WARNING,
                title=f"参数数量过多 ({params})",
                description=f"函数 `{chunk.function_name}` 有 {params} 个参数，超过阈值 5",
                suggestion="考虑使用参数字典、dataclass 或将函数拆分为多个独立函数",
                file_path=chunk.file_path,
            )
        )

    # 4. 嵌套层级
    depth = _estimate_nesting_depth(code)
    if depth > 4:
        findings.append(
            DimensionFinding(
                category=FindingCategory.STRUCTURE,
                severity=FindingSeverity.INFO,
                title=f"嵌套层级过深 ({depth} 层)",
                description=f"函数 `{chunk.function_name}` 最大嵌套深度为 {depth}，超过建议值 4",
                suggestion="提前返回（early return）或提取内层逻辑为独立函数",
                file_path=chunk.file_path,
            )
        )

    # 5. 最小化安全检查
    for pattern, title, suggestion in [
        ("eval(", "eval 函数调用", "移除 eval，使用 ast.literal_eval 或安全替代方案"),
        ("exec(", "exec 函数调用", "移除 exec，使用其他方式实现动态执行"),
        ("os.system(", "os.system 调用", "使用 subprocess 模块替代 os.system"),
        ("subprocess.Popen(", "subprocess.Popen 调用", "检查 shell=True 参数，确保使用列表参数"),
    ]:
        if pattern in code:
            findings.append(
                DimensionFinding(
                    category=FindingCategory.SECURITY,
                    severity=FindingSeverity.CRITICAL,
                    title=f"超大块中含有高危调用: {title}",
                    description=(
                        f"超大函数 `{chunk.function_name}` "
                        f"使用了 `{pattern}`，可能被用于执行任意代码"
                    ),
                    suggestion=suggestion,
                    file_path=chunk.file_path,
                )
            )

    return findings
