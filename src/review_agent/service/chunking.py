"""代码分块服务。

根据函数/方法的 Token 数将代码分为正常块、边界块、超大块，
不同路径采用不同评审策略。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from review_agent.config.settings import get_settings
from review_agent.types.enums import ChunkPath

if TYPE_CHECKING:
    from review_agent.service.ai.base import AIProvider


@dataclass
class CodeChunk:
    """一个代码分块。"""

    file_path: str
    function_name: str
    source_code: str
    start_line: int
    end_line: int
    estimated_tokens: int
    path: ChunkPath

    @property
    def prompt_text(self) -> str:
        """用于嵌入检索的简化文本。"""
        return f"{self.file_path}:{self.function_name or '?'}\n{self.source_code[:500]}"


def adjust_line_number(chunk: CodeChunk, ai_line: int | None) -> int | None:
    """将 AI 返回的相对于函数源码的行号转换为文件绝对行号。

    AI 收到的 prompt 中函数源码起始于行 1，而文件中该函数起始于
    chunk.start_line。此函数将相对行号转换为绝对行号。

    Args:
        chunk: 对应的代码分块。
        ai_line: AI 返回的行号（相对于函数源码），可能为 None。

    Returns:
        文件中的绝对行号，输入为 None 时返回 None。
    """
    if ai_line is None:
        return None
    return chunk.start_line + ai_line - 1


def _estimate_tokens(text: str) -> int:
    """估算 Token 数（中英文混合约 3 字符/token）。"""
    return max(1, len(text) // 3)


def _extract_functions(source_code: str) -> list[dict[str, Any]]:
    """使用正则从代码中提取函数/方法定义。

    这是简化的提取逻辑，不对 AST。适合 M1 阶段的快速实现。

    Args:
        source_code: 完整源代码。

    Returns:
        函数定义列表，每项包含 name, code, start_line, end_line。
    """
    functions = []
    lines = source_code.split("\n")

    # 匹配 def / async def 行
    func_pattern = re.compile(r"^(async\s+)?def\s+([a-zA-Z_]\w*)\s*\(")
    decorator_pattern = re.compile(r"^\s*@")

    current_func: dict[str, Any] | None = None
    func_start = None
    in_func = False
    paren_depth = 0

    for i, line in enumerate(lines):
        # 跳过装饰器行（标记函数开始）
        if decorator_pattern.match(line) and not in_func:
            func_start = i
            continue

        match = func_pattern.match(line)
        if match and not in_func:
            name = match.group(2)
            func_start = func_start if func_start is not None else i
            in_func = True
            current_func = {
                "name": name,
                "start_line": func_start + 1,
                "lines": [line],
            }
            # 计算括号深度以处理多行签名
            paren_depth = line.count("(") - line.count(")")
            continue

        if in_func and current_func is not None:
            current_func["lines"].append(line)
            if "(" in line or ")" in line:
                paren_depth += line.count("(") - line.count(")")

            # 函数结束：新的顶级 def 或缩进回到 0（不在签名中）
            if paren_depth <= 0 and line.strip() and not line[0].isspace():
                # 前一函数结束
                code = "\n".join(current_func["lines"])
                functions.append(
                    {
                        "name": current_func["name"],
                        "code": code,
                        "start_line": current_func["start_line"],
                        "end_line": i,
                    }
                )
                # 当前行是新函数的开始
                if func_pattern.match(line):
                    name = match.group(2) if match else line.split("def ")[1].split("(")[0]
                    current_func = {
                        "name": name,
                        "start_line": i + 1,
                        "lines": [line],
                    }
                    paren_depth = line.count("(") - line.count(")")
                else:
                    current_func = None
                    in_func = False

    # 捕获最后一个函数
    if current_func is not None:
        code = "\n".join(current_func["lines"])
        functions.append(
            {
                "name": current_func["name"],
                "code": code,
                "start_line": current_func["start_line"],
                "end_line": len(lines),
            }
        )

    return functions


async def chunk_file(
    file_path: str,
    source_code: str,
    ai_provider: AIProvider | None = None,
) -> list[CodeChunk]:
    """将源代码分块为函数级别。

    每个函数/方法作为一个 CodeChunk，根据 Token 数分配路径。

    Args:
        file_path: 文件路径。
        source_code: 完整源代码。
        ai_provider: AI Provider（用于精确 Token 计数，None 时使用估算）。
        context_lines: 函数上下文上溯行数。

    Returns:
        代码分块列表。
    """
    settings = get_settings()
    oversized_min = settings.chunk_oversized_min

    functions = _extract_functions(source_code)
    chunks: list[CodeChunk] = []

    for func in functions:
        code = func["code"]

        # 估算 Token
        if ai_provider:
            tokens = await ai_provider.count_tokens(code)
        else:
            tokens = _estimate_tokens(code)

        # 分路径
        if tokens > oversized_min:
            chunk_path = ChunkPath.STRUCTURAL_REVIEW
        else:
            chunk_path = ChunkPath.DETAILED_REVIEW

        chunks.append(
            CodeChunk(
                file_path=file_path,
                function_name=func["name"],
                source_code=code,
                start_line=func["start_line"],
                end_line=func["end_line"],
                estimated_tokens=tokens,
                path=chunk_path,
            )
        )

    # 如果没有提取到函数，把整个文件作为一个块
    if not chunks:
        tokens = _estimate_tokens(source_code)
        chunks.append(
            CodeChunk(
                file_path=file_path,
                function_name="__file__",
                source_code=source_code,
                start_line=1,
                end_line=len(source_code.split("\n")),
                estimated_tokens=tokens,
                path=(
                    ChunkPath.DETAILED_REVIEW
                    if tokens <= oversized_min
                    else ChunkPath.STRUCTURAL_REVIEW
                ),
            )
        )

    return chunks
