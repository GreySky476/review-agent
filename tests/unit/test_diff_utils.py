"""Tests for diff utility functions."""

from __future__ import annotations

from review_agent.service.diff_utils import (
    chunk_overlaps,
    extract_changed_lines,
    get_changed_lines_map,
)
from review_agent.service.git.base import PRFile


class TestExtractChangedLines:
    def test_none_patch_returns_none(self) -> None:
        assert extract_changed_lines(None) is None

    def test_empty_string_returns_empty(self) -> None:
        assert extract_changed_lines("") == set()

    def test_single_addition(self) -> None:
        patch = "@@ -0,0 +1 @@\n+new line\n"
        result = extract_changed_lines(patch)
        assert result == {1}

    def test_multiple_additions(self) -> None:
        patch = "@@ -0,0 +1,3 @@\n+line1\n+line2\n+line3\n"
        result = extract_changed_lines(patch)
        assert result == {1, 2, 3}

    def test_mixed_context_and_additions(self) -> None:
        patch = "@@ -10,7 +10,8 @@\n context\n+added\n context\n"
        result = extract_changed_lines(patch)
        assert result == {11}  # +added is at new line 11

    def test_deletions_only_returns_empty(self) -> None:
        patch = "@@ -1,1 +0,0 @@\n-removed\n"
        result = extract_changed_lines(patch)
        assert result == set()

    def test_multiple_hunks(self) -> None:
        patch = "@@ -1,1 +1,1 @@\n+line1\n@@ -10,1 +10,1 @@\n+line10\n"
        result = extract_changed_lines(patch)
        assert result == {1, 10}

    def test_no_newline_at_end_of_file(self) -> None:
        patch = "@@ -1,1 +1,1 @@\n+line\n\\ No newline at end of file\n"
        result = extract_changed_lines(patch)
        assert result == {1}

    def test_malformed_header_returns_empty(self) -> None:
        assert extract_changed_lines("not a diff") == set()


class TestChunkOverlaps:
    def test_changed_lines_none_returns_true(self) -> None:
        assert chunk_overlaps(1, 10, None) is True

    def test_changed_lines_empty_returns_false(self) -> None:
        assert chunk_overlaps(1, 10, set()) is False

    def test_exact_overlap(self) -> None:
        assert chunk_overlaps(5, 10, {7}) is True

    def test_no_overlap(self) -> None:
        assert chunk_overlaps(1, 5, {10, 20}) is False

    def test_boundary_overlap(self) -> None:
        assert chunk_overlaps(1, 10, {1}) is True
        assert chunk_overlaps(1, 10, {10}) is True


class TestGetChangedLinesMap:
    def test_empty_list(self) -> None:
        assert get_changed_lines_map([]) == {}

    def test_single_file(self) -> None:
        files = [
            PRFile(
                filename="a.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -0,0 +1 @@\n+new",
            ),
        ]
        result = get_changed_lines_map(files)
        assert result == {"a.py": {1}}

    def test_file_without_patch(self) -> None:
        files = [
            PRFile(filename="a.py", status="added", additions=1, deletions=0, patch=None),
        ]
        result = get_changed_lines_map(files)
        assert result == {"a.py": None}

    def test_multiple_files(self) -> None:
        files = [
            PRFile(
                filename="a.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -0,0 +1 @@\n+new",
            ),
            PRFile(
                filename="b.py",
                status="modified",
                additions=0,
                deletions=1,
                patch="@@ -1,1 +0,0 @@\n-removed",
            ),
        ]
        result = get_changed_lines_map(files)
        assert result == {"a.py": {1}, "b.py": set()}

    def test_object_with_file_path_attr(self) -> None:
        class FakeFile:
            file_path = "test.py"
            patch = "@@ -0,0 +1 @@\n+new"

        result = get_changed_lines_map([FakeFile()])
        assert result == {"test.py": {1}}

    def test_no_filename_attr_skipped(self) -> None:
        class NoName:
            patch = "@@ -0,0 +1 @@\n+new"

        result = get_changed_lines_map([NoName()])
        assert result == {}
