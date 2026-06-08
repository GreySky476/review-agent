"""评审维度基类和 Finding 模型。"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from review_agent.service.chunking import CodeChunk
from review_agent.types.enums import FindingCategory, FindingSeverity


@dataclass
class DimensionFinding:
    """单个维度的评审结果。"""

    category: FindingCategory
    severity: FindingSeverity
    title: str
    description: str
    suggestion: str
    file_path: str
    id: UUID = uuid4()
    line_start: int | None = None
    line_end: int | None = None
    rule_id: str | None = None


async def review_security(chunk: CodeChunk) -> list[DimensionFinding]:
    """安全维度评审。"""
    findings: list[DimensionFinding] = []
    code = chunk.source_code

    checks = [
        ("eval/exec 使用", "eval", "eval(", "使用 ast.literal_eval 或安全替代方案"),
        ("exec 使用", "exec", "exec(", "使用安全替代方案"),
        ("SQL 拼接", "sql_injection", "execute(", "使用参数化查询或 ORM"),
        ("shell=True", "shell_true", "shell=True", "禁止 shell=True，使用列表参数"),
        ("mktemp 使用", "mktemp", "mktemp(", "使用 TemporaryFile 或 mkstemp"),
        ("pickle 反序列化", "pickle", "pickle.loads(", "避免反序列化不可信数据"),
    ]

    for title, category_key, pattern, suggestion in checks:
        if pattern in code:
            line_num = _find_line(code, pattern)
            findings.append(
                DimensionFinding(
                    category=FindingCategory.SECURITY,
                    severity=(
                        FindingSeverity.CRITICAL
                        if category_key in ("eval", "exec", "shell_true")
                        else FindingSeverity.WARNING
                    ),
                    title=title,
                    description=f"检测到 {title}，可能存在安全风险",
                    suggestion=suggestion,
                    file_path=chunk.file_path,
                    line_start=line_num,
                    line_end=line_num,
                )
            )

    return findings


async def review_bug_risk(chunk: CodeChunk) -> list[DimensionFinding]:
    """Bug 风险维度评审。"""
    findings: list[DimensionFinding] = []
    code = chunk.source_code

    if "return None" in code and "Optional" not in code and "| None" not in code:
        findings.append(
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.WARNING,
                title="可能缺少 Optional 类型标注",
                description="函数返回 None 但返回类型未标注 Optional",
                suggestion="将返回类型标注为 Optional[...] 或 ... | None",
                file_path=chunk.file_path,
                line_start=_find_line(code, "return None"),
            )
        )

    if "except:" in code:
        findings.append(
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.WARNING,
                title="裸 except 捕获所有异常",
                description="使用裸 except 会捕获包括 KeyboardInterrupt 在内的所有异常",
                suggestion="指定要捕获的异常类型，如 except ValueError:",
                file_path=chunk.file_path,
                line_start=_find_line(code, "except:"),
            )
        )

    return findings


async def review_performance(chunk: CodeChunk) -> list[DimensionFinding]:
    """性能与边界维度评审。"""
    findings: list[DimensionFinding] = []
    code = chunk.source_code

    db_patterns = [".query(", ".filter(", ".get("]
    if "for " in code and any(p in code for p in db_patterns):
        findings.append(
            DimensionFinding(
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="循环内可能存在 N+1 查询",
                description="循环内调用数据库查询可能导致 N+1 性能问题",
                suggestion="使用 select_related / prefetch_related 预加载关联数据",
                file_path=chunk.file_path,
            )
        )

    return findings


async def review_code_style(chunk: CodeChunk) -> list[DimensionFinding]:
    """代码规范维度评审。"""
    findings: list[DimensionFinding] = []

    lines = chunk.source_code.split("\n")
    line_count = len(lines)

    if line_count > 100:
        findings.append(
            DimensionFinding(
                category=FindingCategory.STYLE,
                severity=FindingSeverity.WARNING,
                title=f"函数过长 ({line_count} 行)",
                description=f"函数 `{chunk.function_name}` 共 {line_count} 行，超过建议的 50 行",
                suggestion="建议将函数拆分为多个小函数",
                file_path=chunk.file_path,
                line_start=chunk.start_line,
                line_end=chunk.end_line,
            )
        )

    return findings


async def review_dependency(chunk: CodeChunk) -> list[DimensionFinding]:
    """依赖安全维度评审。"""
    findings: list[DimensionFinding] = []
    code = chunk.source_code

    if "import pickle" in code:
        findings.append(
            DimensionFinding(
                category=FindingCategory.DEPENDENCY,
                severity=FindingSeverity.INFO,
                title="pickle 反序列化风险",
                description="pickle 模块存在反序列化安全风险",
                suggestion="使用 json 或安全序列化格式替代 pickle",
                file_path=chunk.file_path,
            )
        )

    return findings


def _find_line(code: str, pattern: str) -> int | None:
    """查找模式在代码中首次出现的行号。"""
    lines = code.split("\n")
    for i, line in enumerate(lines):
        if pattern in line:
            return i + 1
    return None
