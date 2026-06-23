"""代码分块服务。

根据函数/方法的 Token 数将代码分为正常块、边界块、超大块，
不同路径采用不同评审策略。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from review_agent.config.settings import get_settings
from review_agent.service.standards import detect_language
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
    """将 AI 返回的相对于函数源码的行号转换为文件绝对行号。AI 看到的起始行为 1。"""
    if ai_line is None:
        return None
    return chunk.start_line + ai_line - 1


def _estimate_tokens(text: str) -> int:
    """估算 Token 数（保守估计约 2 字符/token，涵盖中文和多语言）。"""
    return max(1, len(text) // 2)


def _init_parser(lang_name: str) -> Any | None:
    """按语言名初始化 tree-sitter Parser。加载失败返回 None（走正则 fallback）。"""
    try:
        from tree_sitter import Language, Parser

        lang_map: dict[str, Any] = {}
        for mod_name, lang_name_val in [
            ("tree_sitter_python", "python"),
            ("tree_sitter_javascript", "javascript"),
            ("tree_sitter_java", "java"),
            ("tree_sitter_go", "go"),
            ("tree_sitter_rust", "rust"),
        ]:
            try:
                mod = __import__(mod_name)
                lang_map[lang_name_val] = Language(mod.language())
            except ImportError:
                pass

        if lang_name not in lang_map:
            return None

        return Parser(language=lang_map[lang_name])
    except Exception:
        return None


def _extract_ast(source_code: str, parser: Any) -> list[dict[str, Any]]:
    """使用 tree-sitter AST 查询提取函数/类定义。

    Args:
        source_code: 完整源代码。
        parser: 已初始化的 tree-sitter Parser 实例。

    Returns:
        函数/类定义列表，每项包含 name, code, start_line, end_line。
    """
    tree = parser.parse(bytes(source_code, "utf-8"))
    root = tree.root_node

    functions: list[dict[str, Any]] = []
    lines = source_code.split("\n")

    def _find_name(node: Any) -> str:
        """从 AST 节点中获取名称字符串。"""
        for child in node.children:
            if child.type in ("name", "identifier", "property_identifier", "field_identifier"):
                return source_code[child.start_byte:child.end_byte]
            deeper = _find_name(child)
            if deeper:
                return deeper
        return ""

    def _collect(node: Any) -> None:
        ntype = node.type
        if ntype in (
            "function_definition", "function_declaration", "method_declaration",
            "method_definition", "function_item",
            "class_definition", "class_declaration",
        ):
            name = _find_name(node)
            sl = node.start_point[0] + 1
            el = node.end_point[0] + 1
            functions.append({
                "name": name,
                "code": "\n".join(lines[sl - 1:el]),
                "start_line": sl,
                "end_line": el,
            })
            # Recurse into children to find nested functions/classes
            for child in node.children:
                _collect(child)
            return
        for child in node.children:
            _collect(child)

    _collect(root)
    return functions


def _extract_functions(source_code: str) -> list[dict[str, Any]]:
    """正则提取函数/方法定义（AST fallback）。"""
    functions = []
    lines = source_code.split("\n")
    func_pat = re.compile(r"^(async\s+)?def\s+([a-zA-Z_]\w*)\s*\(")
    deco_pat = re.compile(r"^\s*@")

    current_func: dict[str, Any] | None = None
    func_start = None
    in_func = False
    paren_depth = 0

    for i, line in enumerate(lines):
        if deco_pat.match(line) and not in_func:
            func_start = i
            continue

        match = func_pat.match(line)
        if match and not in_func:
            name = match.group(2)
            func_start = func_start if func_start is not None else i
            in_func = True
            current_func = {"name": name, "start_line": func_start + 1, "lines": [line]}
            paren_depth = line.count("(") - line.count(")")
            continue

        if in_func and current_func is not None:
            current_func["lines"].append(line)
            if "(" in line or ")" in line:
                paren_depth += line.count("(") - line.count(")")

            if paren_depth <= 0 and line.strip() and not line[0].isspace():
                code = "\n".join(current_func["lines"])
                functions.append({
                    "name": current_func["name"],
                    "code": code,
                    "start_line": current_func["start_line"],
                    "end_line": i,
                })
                if func_pat.match(line):
                    name = match.group(2) if match else line.split("def ")[1].split("(")[0]
                    current_func = {"name": name, "start_line": i + 1, "lines": [line]}
                    paren_depth = line.count("(") - line.count(")")
                else:
                    current_func = None
                    in_func = False

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

    优先使用 tree-sitter AST 提取函数/类定义（多语言支持），
    失败或语言不支持时回退到正则提取。

    Args:
        file_path: 文件路径。
        source_code: 完整源代码。
        ai_provider: AI Provider（用于精确 Token 计数，None 时使用估算）。

    Returns:
        代码分块列表。
    """
    settings = get_settings()
    oversized_min = settings.chunk_oversized_min

    # 尝试 tree-sitter AST 提取（多语言），失败则回退到正则
    lang = detect_language(file_path)
    parser = _init_parser(lang)
    if parser is not None:
        functions = _extract_ast(source_code, parser)
    else:
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
