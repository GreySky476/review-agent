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
                _finding(severity=FindingSeverity.INFO, title="Sev 3"),
            ]
        )
        assert score == 74  # 100 - 15 - 8 - 3

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
            _finding(file_path="a.py", title="same", severity=FindingSeverity.INFO),
            _finding(file_path="a.py", title="same", severity=FindingSeverity.CRITICAL),
        ]
        deduped, _ = p.aggregate(findings)
        assert len(deduped) == 1
        assert deduped[0].severity == FindingSeverity.CRITICAL


class TestPublisherReport:
    def test_no_report_for_few_findings(self) -> None:
        p = Publisher()
        findings = [_finding(severity=FindingSeverity.WARNING)]
        assert p.should_generate_report(findings) is False

    def test_report_for_many_serious(self) -> None:
        p = Publisher()
        findings = [_finding(severity=FindingSeverity.CRITICAL) for _ in range(10)]
        assert p.should_generate_report(findings) is True

    def test_generate_summary_empty(self) -> None:
        p = Publisher()
        summary = p.generate_summary([], 100)
        assert "未发现问题" in summary

    def test_generate_summary_with_findings(self) -> None:
        p = Publisher()
        findings = [
            _finding(title="Test Bug", severity=FindingSeverity.WARNING),
        ]
        summary = p.generate_summary(findings, 92)
        assert "Test Bug" in summary
        assert "92" in summary

    def test_summary_sorted_by_severity(self) -> None:
        """Findings in summary should be sorted by severity then category priority."""
        p = Publisher()
        findings = [
            _finding(
                title="Info Style",
                severity=FindingSeverity.INFO,
                category=FindingCategory.STYLE,
            ),
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

        # 按出现顺序提取标题
        lines = summary.split("\n")
        table_lines = [ln for ln in lines if ln.startswith("|") and "**" in ln]
        titles_in_order = []
        for line in table_lines:
            cells = line.split("|")
            if len(cells) >= 5:
                titles_in_order.append(cells[4].strip())

        assert titles_in_order[0] == "Critical Bug"  # CRITICAL BUG
        assert titles_in_order[1] == "Warning Bug"  # WARNING BUG (before WARNING SECURITY)
        assert titles_in_order[2] == "Warning Security"  # WARNING SECURITY
        assert titles_in_order[3] == "Info Style"  # INFO STYLE
