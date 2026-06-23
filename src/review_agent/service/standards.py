"""语言特定的代码评审规范加载模块。

职责：
1. 根据文件扩展名判断编程语言
2. 加载对应语言的评审规范 Markdown
3. 提供 Fallback 到 generic.md 的兜底逻辑
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

logger = logging.getLogger(__name__)


# 扩展名 → 语言标识
# 第一期为 Python + generic，后续按需扩展
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "javascript",
    ".tsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".kt": "java",
    ".swift": "generic",
    ".rb": "generic",
    ".php": "generic",
    ".c": "generic",
    ".cpp": "generic",
    ".h": "generic",
    ".hpp": "generic",
    ".cs": "generic",
    ".scala": "generic",
    ".vue": "javascript",
    ".svelte": "javascript",
}

# 语言 → 规范文档文件名（仅列出有独立规范的语言）
LANGUAGE_DOC_MAP: dict[str, str] = {
    "python": "python.md",
}

_STANDARDS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "docs/coding/language-standards"
)
_CACHE: dict[str, str] = {}
_CACHE_LOCK = threading.Lock()


def detect_language(file_path: str) -> str:
    """根据文件路径判断编程语言。

    Args:
        file_path: 文件路径（如 ``src/app.py``）。

    Returns:
        语言标识字符串（如 ``python``、``javascript``），
        未知扩展名返回 ``generic``。
    """
    ext = Path(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "generic")


def load_standards(file_path: str) -> str:
    """加载文件对应语言的代码评审规范 Markdown 内容。

    结果按语言缓存，首次读取后不再重复 IO。

    Args:
        file_path: 文件路径。

    Returns:
        对应语言的评审规范 Markdown 字符串。
        若规范文档不存在或读取失败，返回空字符串。
    """
    lang = detect_language(file_path)
    doc_name = LANGUAGE_DOC_MAP.get(lang, "generic.md")

    # 缓存命中（读锁）
    with _CACHE_LOCK:
        if doc_name in _CACHE:
            return _CACHE[doc_name]

    doc_path = _STANDARDS_DIR / doc_name
    try:
        content = doc_path.read_text(encoding="utf-8")
        with _CACHE_LOCK:
            _CACHE[doc_name] = content
        logger.debug("Loaded standards: %s (from %s)", doc_name, doc_path)
        return content
    except FileNotFoundError:
        logger.warning("Standards file not found: %s", doc_path)
        with _CACHE_LOCK:
            _CACHE[doc_name] = ""
        return ""
    except OSError as exc:
        logger.warning("Failed to read standards file %s: %s", doc_path, exc)
        with _CACHE_LOCK:
            _CACHE[doc_name] = ""
        return ""


def clear_cache() -> None:
    """清空规范文档缓存（仅测试场景使用）。"""
    with _CACHE_LOCK:
        _CACHE.clear()
