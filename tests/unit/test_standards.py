"""Tests for language standards module."""

from review_agent.service.standards import (
    _CACHE,
    clear_cache,
    detect_language,
    load_standards,
)


class TestDetectLanguage:
    def test_dot_py(self) -> None:
        assert detect_language("src/app.py") == "python"

    def test_dot_pyw(self) -> None:
        assert detect_language("script.pyw") == "python"

    def test_unknown_extension(self) -> None:
        assert detect_language("Makefile") == "generic"

    def test_unknown_dot_ext(self) -> None:
        assert detect_language("data.xyz") == "generic"

    def test_js_file(self) -> None:
        assert detect_language("ui/index.js") == "javascript"

    def test_tsx_file(self) -> None:
        assert detect_language("ui/Component.tsx") == "javascript"

    def test_go_file(self) -> None:
        assert detect_language("server.go") == "go"

    def test_java_file(self) -> None:
        assert detect_language("Main.java") == "java"

    def test_rust_file(self) -> None:
        assert detect_language("lib.rs") == "rust"


class TestLoadStandards:
    def setup_method(self) -> None:
        clear_cache()

    def test_load_python_standards(self) -> None:
        content = load_standards("src/app.py")
        assert content
        assert "## 1. 资源管理" in content
        assert "## 2. 并发安全" in content
        assert "## 3. 正确性" in content
        assert "## 4. 安全" in content

    def test_fallback_to_generic(self) -> None:
        content = load_standards("main.go")
        assert content
        assert "通用代码评审规范" in content

    def test_fallback_for_unknown_language(self) -> None:
        content = load_standards("data.xyz")
        assert content
        assert "通用代码评审规范" in content

    def test_caching(self) -> None:
        cache_key = "generic.md"
        _CACHE.pop(cache_key, None)
        load_standards("unknown.ext")
        assert cache_key in _CACHE

    def test_load_nonexistent_language_no_error(self) -> None:
        """未知语言 fallback 到 generic.md，不应抛异常。"""
        result = load_standards("wibble.wobble")
        assert result is not None


class TestClearCache:
    def test_clear_cache(self) -> None:
        load_standards("src/app.py")
        assert _CACHE
        clear_cache()
        assert not _CACHE
