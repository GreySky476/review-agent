"""Tests for publisher service."""

from review_agent.service.dimensions.base import DimensionFinding
from review_agent.service.publisher import Publisher
from review_agent.types.enums import FindingCategory, FindingSeverity


def _finding(
    category: FindingCategory = FindingCategory.BUG,
    severity: FindingSeverity = FindingSeverity.WARNING,
    file_path: str = "src/main.py",
    title: str = "Test finding",
) -> DimensionFinding:
    return DimensionFinding(
        category=category,
        severity=severity,
        title=title,
        description="Test description",
        suggestion="Test suggestion",
        file_path=file_path,
    )


class TestPublisherScore:
    def test_perfect_score(self) -> None:
        p = Publisher()
        _, score = p.aggregate([])
        assert score == 100

    def test_critical_deduction(self) -> None:
        p = Publisher()
        _, score = p.aggregate(
            [
                _finding(severity=FindingSeverity.CRITICAL),
            ]
        )
        assert score == 85  # 100 - 15

    def test_multiple_deductions(self) -> None:
        p = Publisher()
        _, score = p.aggregate(
            [
                _finding(severity=FindingSeverity.CRITICAL, title="Sev 1"),
                _finding(severity=FindingSeverity.WARNING, title="Sev 2"),
            ]
        )
        assert score == 77  # 100 - 15 - 8

    def test_info_deduction_removed(self) -> None:
        """INFO findings are filtered out before scoring, so no deduction."""
        p = Publisher()
        _, score = p.aggregate(
            [
                _finding(severity=FindingSeverity.INFO, title="Info finding"),
            ]
        )
        assert score == 100  # INFO was filtered out

    def test_min_score_is_zero(self) -> None:
        p = Publisher()
        findings = [_finding(severity=FindingSeverity.CRITICAL) for _ in range(10)]
        _, score = p.aggregate(findings)
        assert score >= 0


class TestPublisherAggregate:
    def test_dedup_by_file_and_title(self) -> None:
        p = Publisher()
        findings = [
            _finding(file_path="a.py", title="bug1"),
            _finding(file_path="a.py", title="bug1"),  # duplicate
            _finding(file_path="b.py", title="bug2"),  # different
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 2

    def test_keeps_worst_severity_on_dup(self) -> None:
        p = Publisher()
        findings = [
            _finding(file_path="a.py", title="same", severity=FindingSeverity.WARNING),
            _finding(file_path="a.py", title="same", severity=FindingSeverity.CRITICAL),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 1
        assert deduped[0].severity == FindingSeverity.CRITICAL

    def test_info_severity_filtered_out(self) -> None:
        """INFO severity findings are filtered out before dedup."""
        p = Publisher()
        findings = [
            _finding(severity=FindingSeverity.INFO, title="info finding"),
            _finding(severity=FindingSeverity.CRITICAL, title="critical finding"),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 1  # only CRITICAL remains
        assert deduped[0].severity == FindingSeverity.CRITICAL

    def test_style_category_filtered_out(self) -> None:
        """STYLE category findings are filtered out."""
        p = Publisher()
        findings = [
            _finding(
                category=FindingCategory.STYLE,
                severity=FindingSeverity.WARNING,
                title="style issue",
            ),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 0

    def test_dependency_category_filtered_out(self) -> None:
        """DEPENDENCY category findings are filtered out."""
        p = Publisher()
        findings = [
            _finding(
                category=FindingCategory.DEPENDENCY,
                severity=FindingSeverity.CRITICAL,
                title="dep issue",
            ),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 0

    def test_structure_category_filtered_out(self) -> None:
        """STRUCTURE category findings are filtered out."""
        p = Publisher()
        findings = [
            _finding(
                category=FindingCategory.STRUCTURE,
                severity=FindingSeverity.CRITICAL,
                title="struct issue",
            ),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 0

    def test_allowed_categories_pass_through(self) -> None:
        """BUG, SECURITY, PERFORMANCE categories pass through the filter."""
        p = Publisher()
        findings = [
            _finding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.WARNING,
                title="bug",
            ),
            _finding(
                category=FindingCategory.SECURITY,
                severity=FindingSeverity.CRITICAL,
                title="security",
            ),
            _finding(
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="perf",
            ),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 3


class TestPublisherReport:
    def test_no_report_for_empty_findings(self) -> None:
        p = Publisher()
        assert p.should_generate_report([]) is False

    def test_report_for_non_empty_findings(self) -> None:
        p = Publisher()
        findings = [_finding(severity=FindingSeverity.CRITICAL)]
        assert p.should_generate_report(findings) is True

    def test_generate_summary_empty(self) -> None:
        p = Publisher()
        summary = p.generate_summary([], 100)
        assert "未发现问题" in summary

    def test_generate_summary_with_findings(self) -> None:
        p = Publisher()
        findings = [
            _finding(
                title="Test Bug",
                severity=FindingSeverity.WARNING,
                category=FindingCategory.BUG,
            ),
        ]
        summary = p.generate_summary(findings, 92)
        assert "Test Bug" in summary
        assert "92" in summary
        assert "### Bug（1 项）" in summary

    def test_summary_grouped_by_category(self) -> None:
        """Findings in summary should be grouped by category (Security, Bug, Performance)."""
        p = Publisher()
        findings = [
            _finding(
                title="Critical Bug",
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.BUG,
            ),
            _finding(
                title="Warning Security",
                severity=FindingSeverity.WARNING,
                category=FindingCategory.SECURITY,
            ),
            _finding(
                title="Warning Bug",
                severity=FindingSeverity.WARNING,
                category=FindingCategory.BUG,
            ),
        ]
        summary = p.generate_summary(findings, 70)

        # Security section comes before Bug section
        assert "### Security（1 项）" in summary
        assert "### Bug（2 项）" in summary
        security_pos = summary.index("### Security（1 项）")
        bug_pos = summary.index("### Bug（2 项）")
        assert security_pos < bug_pos

    def test_summary_with_unreviewed(self) -> None:
        p = Publisher()
        summary = p.generate_summary([], 100, unreviewed_count=3)
        assert "3 个文件未能完成评审" in summary
