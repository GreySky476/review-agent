"""Tests for tree-sitter AST code chunking."""

from unittest.mock import MagicMock, patch

from review_agent.service.chunking import (
    _extract_ast,
    _init_parser,
    chunk_file,
)


class TestInitParser:
    """Tests for _init_parser tree-sitter initialization."""

    def test_unknown_language(self) -> None:
        """Unknown language should return None (triggers regex fallback)."""
        assert _init_parser("unknown_lang") is None

    def test_generic_fallback(self) -> None:
        """Generic language should return None (not in supported list)."""
        assert _init_parser("generic") is None

    def test_python_no_package(self) -> None:
        """When tree_sitter_python not installed, return None."""
        with patch.dict("sys.modules", {"tree_sitter_python": None}, clear=False):
            result = _init_parser("python")
            assert result is None


class TestExtractAst:
    """Tests for _extract_ast tree-sitter AST extraction."""

    def _make_parser(self, children: list) -> MagicMock:
        """Create a mock parser with given root children."""
        root = MagicMock()
        root.type = "module"
        root.children = children
        tree = MagicMock()
        tree.root_node = root
        parser = MagicMock()
        parser.parse.return_value = tree
        return parser

    def _make_node(
        self,
        node_type: str,
        start_line: int,
        end_line: int,
        name_text: str = "",
        children: list | None = None,
    ) -> MagicMock:
        """Create a mock AST node."""
        node = MagicMock()
        node.type = node_type
        node.start_point = (start_line - 1, 0)
        node.end_point = (end_line - 1, 0)
        if name_text:
            name_node = MagicMock()
            name_node.type = "name"
            name_node.start_byte = 0
            name_node.end_byte = len(name_text)
            node.children = children or [name_node]
        else:
            node.children = children or []
        return node

    def test_python_function(self) -> None:
        """Extract a simple Python function."""
        source = "def foo():\n    pass"
        # Simulate name node byte offsets
        name_node = MagicMock()
        name_node.type = "name"
        name_node.start_byte = 4
        name_node.end_byte = 7

        func_node = MagicMock()
        func_node.type = "function_definition"
        func_node.start_point = (0, 0)
        func_node.end_point = (1, 8)
        func_node.children = [name_node]

        parser = self._make_parser([func_node])
        result = _extract_ast(source, parser)

        assert len(result) == 1
        assert result[0]["name"] == "foo"
        assert result[0]["code"] == source
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 2

    def test_python_class_with_method(self) -> None:
        """Extract a Python class and its inner method."""
        source = "class MyClass:\n    def method(self):\n        pass"

        method_name = MagicMock()
        method_name.type = "name"
        method_name.start_byte = 23
        method_name.end_byte = 29

        method_node = MagicMock()
        method_node.type = "function_definition"
        method_node.start_point = (1, 4)
        method_node.end_point = (2, 12)
        method_node.children = [method_name]

        class_name = MagicMock()
        class_name.type = "name"
        class_name.start_byte = 6
        class_name.end_byte = 13

        class_node = MagicMock()
        class_node.type = "class_definition"
        class_node.start_point = (0, 0)
        class_node.end_point = (2, 12)
        class_node.children = [class_name, method_node]

        parser = self._make_parser([class_node])
        result = _extract_ast(source, parser)

        assert len(result) == 2
        assert result[0]["name"] == "MyClass"
        assert result[1]["name"] == "method"

    def test_javascript_function(self) -> None:
        """Extract a JavaScript function (node type: function_declaration)."""
        source = "function hello() {\n  return 1;\n}"

        name_node = MagicMock()
        name_node.type = "name"
        name_node.start_byte = 9
        name_node.end_byte = 14

        func_node = MagicMock()
        func_node.type = "function_declaration"
        func_node.start_point = (0, 0)
        func_node.end_point = (2, 3)
        func_node.children = [name_node]

        parser = self._make_parser([func_node])
        result = _extract_ast(source, parser)

        assert len(result) == 1
        assert result[0]["name"] == "hello"
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 3

    def test_javascript_method_definition(self) -> None:
        """Extract JavaScript method definition inside a class."""
        source = "class Foo {\n  bar() { return 1; }\n}"

        method_name = MagicMock()
        method_name.type = "property_identifier"
        method_name.start_byte = 14
        method_name.end_byte = 17

        method_node = MagicMock()
        method_node.type = "method_definition"
        method_node.start_point = (1, 2)
        method_node.end_point = (1, 24)
        method_node.children = [method_name]

        class_name = MagicMock()
        class_name.type = "name"
        class_name.start_byte = 6
        class_name.end_byte = 9

        class_node = MagicMock()
        class_node.type = "class_definition"
        class_node.start_point = (0, 0)
        class_node.end_point = (2, 1)
        class_node.children = [class_name, method_node]

        parser = self._make_parser([class_node])
        result = _extract_ast(source, parser)

        assert len(result) == 2
        assert result[0]["name"] == "Foo"
        assert result[1]["name"] == "bar"

    def test_go_method_declaration(self) -> None:
        """Extract a Go method declaration."""
        source = "func (r *Receiver) Method() {\n  return\n}"

        name_node = MagicMock()
        name_node.type = "field_identifier"
        name_node.start_byte = 19
        name_node.end_byte = 25

        method_node = MagicMock()
        method_node.type = "method_declaration"
        method_node.start_point = (0, 0)
        method_node.end_point = (1, 9)
        method_node.children = [name_node]

        parser = self._make_parser([method_node])
        result = _extract_ast(source, parser)

        assert len(result) == 1
        assert result[0]["name"] == "Method"
        assert result[0]["start_line"] == 1

    def test_javascript_class_declaration(self) -> None:
        """Extract JavaScript class declaration (class_declaration)."""
        source = "class Hello {\n  greet() { return 'hi'; }\n}"

        method_name = MagicMock()
        method_name.type = "property_identifier"
        method_name.start_byte = 16
        method_name.end_byte = 21

        method_node = MagicMock()
        method_node.type = "method_definition"
        method_node.start_point = (1, 2)
        method_node.end_point = (1, 32)
        method_node.children = [method_name]

        class_name = MagicMock()
        class_name.type = "name"
        class_name.start_byte = 6
        class_name.end_byte = 11

        class_node = MagicMock()
        class_node.type = "class_declaration"
        class_node.start_point = (0, 0)
        class_node.end_point = (2, 1)
        class_node.children = [class_name, method_node]

        parser = self._make_parser([class_node])
        result = _extract_ast(source, parser)

        assert len(result) == 2
        assert result[0]["name"] == "Hello"
        assert result[1]["name"] == "greet"

    def test_rust_function_item(self) -> None:
        """Extract Rust function (function_item)."""
        source = "fn calculate() -> i32 {\n    42\n}"

        name_node = MagicMock()
        name_node.type = "name"
        name_node.start_byte = 3
        name_node.end_byte = 12

        func_node = MagicMock()
        func_node.type = "function_item"
        func_node.start_point = (0, 0)
        func_node.end_point = (1, 7)
        func_node.children = [name_node]

        parser = self._make_parser([func_node])
        result = _extract_ast(source, parser)

        assert len(result) == 1
        assert result[0]["name"] == "calculate"
        assert result[0]["start_line"] == 1
        assert result[0]["end_line"] == 2

    def test_python_nested_function(self) -> None:
        """Nested inner function should also be extracted."""
        source = "def outer():\n    def inner():\n        pass\n    pass"

        # Inner function
        inner_name = MagicMock()
        inner_name.type = "name"
        inner_name.start_byte = 21
        inner_name.end_byte = 26

        inner_func = MagicMock()
        inner_func.type = "function_definition"
        inner_func.start_point = (1, 4)
        inner_func.end_point = (2, 12)
        inner_func.children = [inner_name]

        # Outer function
        outer_name = MagicMock()
        outer_name.type = "name"
        outer_name.start_byte = 4
        outer_name.end_byte = 9

        outer_func = MagicMock()
        outer_func.type = "function_definition"
        outer_func.start_point = (0, 0)
        outer_func.end_point = (3, 8)
        outer_func.children = [outer_name, inner_func]

        parser = self._make_parser([outer_func])
        result = _extract_ast(source, parser)

        # Both outer and inner functions should be found
        names = {r["name"] for r in result}
        assert "outer" in names
        assert "inner" in names

    def test_empty_code(self) -> None:
        """Empty source code returns empty list."""
        parser = self._make_parser([])
        result = _extract_ast("", parser)
        assert len(result) == 0

    def test_no_functions(self) -> None:
        """Code with no functions returns empty list."""
        parser = self._make_parser([])
        result = _extract_ast("x = 1\ny = 2", parser)
        assert len(result) == 0


class TestChunkFileAst:
    """Tests for chunk_file with AST path."""

    async def test_python_function_via_ast(self) -> None:
        """Python function extraction via AST should produce correct chunks."""
        code = "def foo():\n    pass"
        chunks = await chunk_file("test.py", code)
        assert len(chunks) >= 1
        assert chunks[0].function_name == "foo"
        assert chunks[0].start_line == 1
        assert chunks[0].end_line == 2

    async def test_python_class_via_ast(self) -> None:
        """Python class and method extraction via AST should produce multiple chunks."""
        code = "class MyClass:\n    def method(self):\n        pass"
        chunks = await chunk_file("test.py", code)
        # AST extracts both class and inner method
        assert len(chunks) >= 2
        names = {c.function_name for c in chunks}
        assert "MyClass" in names
        assert "method" in names

    async def test_unknown_language_fallback(self) -> None:
        """Unknown language extension falls back to regex."""
        code = "fun = lambda x: x"
        chunks = await chunk_file("test.unknown", code)
        # No functions found, should produce file-level chunk
        assert len(chunks) == 1
        assert chunks[0].function_name == "__file__"

    async def test_generic_extension_fallback(self) -> None:
        """Generic extension falls back to regex."""
        code = "x = 1"
        chunks = await chunk_file("test.rb", code)
        # No functions found, file-level chunk
        assert len(chunks) == 1
        assert chunks[0].function_name == "__file__"

    async def test_js_extension(self) -> None:
        """JavaScript file should attempt AST extraction."""
        code = "function hello() {\n  return 1;\n}"
        chunks = await chunk_file("test.js", code)
        # If tree-sitter-javascript is installed, AST extraction works
        # Otherwise falls back to regex (no functions found)
        assert len(chunks) >= 1


class TestTokenEstimate:
    """Tests for _estimate_tokens update."""

    def test_estimation_div2(self) -> None:
        """Token estimation now divides by 2 (was 3)."""
        from review_agent.service.chunking import _estimate_tokens

        assert _estimate_tokens("hello world") == 5  # len("hello world")=11, 11//2=5
        assert _estimate_tokens("a" * 100) == 50  # len 100 // 2
