"""Tests for ARQ queue integration."""

from review_agent.service.queue import (
    WorkerSettings,
    _extract_repo_name_from_url,
    run_commit_review,
    run_review,
    sync_project_data,
)
from review_agent.types.enums import ReviewStatus


class TestWorkerSettings:
    def test_worker_settings_have_all_functions(self) -> None:
        assert len(WorkerSettings.functions) == 3
        assert run_review in WorkerSettings.functions
        assert run_commit_review in WorkerSettings.functions
        assert sync_project_data in WorkerSettings.functions


class TestRunReview:
    async def test_run_review_returns_result(self) -> None:
        result = await run_review({}, "proj-1", "owner/repo", "abc123", 42, [])
        assert result["project_id"] == "proj-1"
        assert result["pr_number"] == 42
        assert result["status"] == ReviewStatus.COMPLETED.value


class TestRunCommitReview:
    async def test_run_commit_review_empty_files(self) -> None:
        """Commit review with no changed files returns completed."""
        result = await run_commit_review({}, "proj-1", "owner/repo", "abc123", [])
        assert result["project_id"] == "proj-1"
        assert result["sha"] == "abc123"
        assert result["status"] == ReviewStatus.COMPLETED.value
        assert result["findings_count"] == 0


class TestSyncProjectData:
    async def test_sync_project_data_skipped_no_project(self) -> None:
        """Unknown project returns skipped."""
        result = await sync_project_data({}, "nonexistent-project")
        assert result["status"] == "skipped"
        assert result["reason"] == "project_not_found"


class TestExtractRepoName:
    def test_extract_repo_name_from_url(self) -> None:
        assert _extract_repo_name_from_url("https://github.com/owner/repo") == "owner/repo"
        assert _extract_repo_name_from_url("https://github.com/owner/repo.git") == "owner/repo"
        assert _extract_repo_name_from_url("") is None
        assert _extract_repo_name_from_url("invalid") is None
