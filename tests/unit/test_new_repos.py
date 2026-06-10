"""Tests for new dashboard-related Repository classes."""

from review_agent.repo.comment import CommentRepo
from review_agent.repo.commit import CommitRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.quality_snapshot import QualitySnapshotRepo
from review_agent.repo.review_error import ReviewErrorRepo


class TestPullRequestRepo:
    def test_repo_has_model(self) -> None:
        repo = PullRequestRepo(None)  # type: ignore[arg-type]
        model = repo._model
        assert model.__tablename__ == "pull_requests"

    def test_has_upsert_method(self) -> None:
        assert hasattr(PullRequestRepo, "upsert")

    def test_has_list_by_project_method(self) -> None:
        assert hasattr(PullRequestRepo, "list_by_project")


class TestCommitRepo:
    def test_repo_has_model(self) -> None:
        repo = CommitRepo(None)  # type: ignore[arg-type]
        model = repo._model
        assert model.__tablename__ == "commits"

    def test_has_list_by_project_method(self) -> None:
        assert hasattr(CommitRepo, "list_by_project")

    def test_has_get_by_sha_method(self) -> None:
        assert hasattr(CommitRepo, "get_by_sha")


class TestCommentRepo:
    def test_repo_has_model(self) -> None:
        repo = CommentRepo(None)  # type: ignore[arg-type]
        model = repo._model
        assert model.__tablename__ == "comments"

    def test_has_list_by_review_method(self) -> None:
        assert hasattr(CommentRepo, "list_by_review")

    def test_has_list_by_finding_method(self) -> None:
        assert hasattr(CommentRepo, "list_by_finding")


class TestReviewErrorRepo:
    def test_repo_has_model(self) -> None:
        repo = ReviewErrorRepo(None)  # type: ignore[arg-type]
        model = repo._model
        assert model.__tablename__ == "review_errors"

    def test_has_list_with_filters_method(self) -> None:
        assert hasattr(ReviewErrorRepo, "list_with_filters")

    def test_has_count_by_type_method(self) -> None:
        assert hasattr(ReviewErrorRepo, "count_by_type")


class TestQualitySnapshotRepo:
    def test_repo_has_model(self) -> None:
        repo = QualitySnapshotRepo(None)  # type: ignore[arg-type]
        model = repo._model
        assert model.__tablename__ == "quality_snapshots"

    def test_has_list_by_project_and_period_method(self) -> None:
        assert hasattr(QualitySnapshotRepo, "list_by_project_and_period")
