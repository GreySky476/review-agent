"""Tests for ARQ queue integration."""

from review_agent.service.queue import WorkerSettings, run_review
from review_agent.types.enums import ReviewStatus


class TestWorkerSettings:
    def test_worker_settings_have_functions(self) -> None:
        assert len(WorkerSettings.functions) == 1
        assert run_review in WorkerSettings.functions


class TestRunReview:
    async def test_run_review_returns_result(self) -> None:
        result = await run_review({}, "proj-1", 42, "abc123")
        assert result["project_id"] == "proj-1"
        assert result["pr_number"] == 42
        assert result["status"] == ReviewStatus.COMPLETED.value
