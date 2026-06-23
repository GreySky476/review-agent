"""结果聚合与发布决策服务。

职责：
1. 合并所有维度的 Finding，去重
2. 根据 Finding 数量和严重性决策发布策略
3. 生成 Markdown 摘要报告
"""

from __future__ import annotations

from review_agent.config.settings import get_settings
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.types.enums import FindingCategory, FindingSeverity


class Publisher:
    """评审结果发布器。"""

    def __init__(self) -> None:
        self._settings = get_settings()

    def aggregate(self, findings: list[DimensionFinding]) -> tuple[list[DimensionFinding], int]:
        """聚合和去重 Finding。

        按 (file_path, title) 去重，保留严重性最高的。

        Args:
            findings: 各维度返回的 Finding 列表。

        Returns:
            (去重后的 Finding 列表, 总分)
        """
        seen: set[tuple[str, str]] = set()
        deduped: list[DimensionFinding] = []

        # 过滤：只保留 BUG/SECURITY/PERFORMANCE 类别且非 INFO 级别的 finding
        allowed_categories = {
            FindingCategory.BUG,
            FindingCategory.SECURITY,
            FindingCategory.PERFORMANCE,
        }
        findings = [
            f
            for f in findings
            if f.category in allowed_categories and f.severity != FindingSeverity.INFO
        ]

        # 严重性排序
        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
        }

        for f in findings:
            key = (f.file_path, f.title)
            if key not in seen:
                seen.add(key)
                deduped.append(f)
            else:
                # 保留更严重的
                existing = next(d for d in deduped if (d.file_path, d.title) == key)
                if severity_order.get(f.severity, 99) < severity_order.get(existing.severity, 99):
                    deduped.remove(existing)
                    deduped.append(f)

        score = self._calculate_score(deduped)
        return deduped, score

    def _calculate_score(self, findings: list[DimensionFinding]) -> int:
        """计算评审总分（0-100）。

        初始 100 分，按严重性扣分：
        - critical: -15
        - warning: -8
        """
        deductions = {
            FindingSeverity.CRITICAL: 15,
            FindingSeverity.WARNING: 8,
        }
        total_deduction = sum(deductions.get(f.severity, 0) for f in findings)
        return max(0, 100 - total_deduction)

    def should_generate_report(self, findings: list[DimensionFinding]) -> bool:
        """判断是否需要生成详细报告。

        所有 findings 已过滤为仅 CRITICAL/WARNING，有值即生成。

        Args:
            findings: 去重后的 Finding 列表。

        Returns:
            是否需要生成详细报告。
        """
        return len(findings) > 0

    def generate_summary(
        self,
        findings: list[DimensionFinding],
        score: int,
        unreviewed_count: int = 0,
    ) -> str:
        """生成 Markdown 格式的评审摘要。

        按 Security / Bug / Performance 分组输出，每组展示代码片段。

        Args:
            findings: 去重后的 Finding 列表。
            score: 评审总分。
            unreviewed_count: 因错误无法评审的文件数。

        Returns:
            Markdown 格式的摘要文本。
        """
        lines = ["## \U0001f50d AI 代码评审结果\n"]

        # Score + rating
        if score >= 90:
            rating = "\U0001f7e0 优秀"
        elif score >= 70:
            rating = "\U0001f7e1 良好"
        else:
            rating = "\U0001f534 待改进"
        lines.append(f"**评分：{score}/100** — {rating}\n")

        if unreviewed_count:
            lines.append(f"⚠ **{unreviewed_count} 个文件未能完成评审**\n")

        if not findings:
            lines.append("✅ 未发现问题。\n")
            return "\n".join(lines)

        severity_icons = {
            FindingSeverity.CRITICAL: "\U0001f534",
            FindingSeverity.WARNING: "\U0001f7e1",
        }

        # Define category groups and their display order
        category_groups = [
            (FindingCategory.SECURITY, "Security"),
            (FindingCategory.BUG, "Bug"),
            (FindingCategory.PERFORMANCE, "Performance"),
        ]

        for cat, cat_label in category_groups:
            cat_findings = [f for f in findings if f.category == cat]
            if not cat_findings:
                continue

            lines.append(f"### {cat_label}（{len(cat_findings)} 项）\n")
            lines.append("| 严重性 | 位置 | 代码 | 问题 | 建议 |")
            lines.append("|--------|------|------|------|------|")

            for f in cat_findings:
                icon = severity_icons.get(f.severity, "⚪")
                location = f"`{f.file_path}:{f.line_start}`" if f.line_start else f"`{f.file_path}`"  # noqa: SIM108
                snippet = f"`{f.code_snippet}`" if f.code_snippet else ""
                title = f.title.replace("|", "\\|")
                suggestion = f.suggestion.replace("|", "\\|").replace("\n", " ")
                lines.append(
                    f"| {icon} **{f.severity.value.upper()}** | {location}"
                    f" | {snippet} | {title} | {suggestion} |"
                )
            lines.append("")

        return "\n".join(lines)

    def generate_incremental_summary(
        self,
        findings: list[DimensionFinding],
        score: int,
        commit_sha: str,
        unreviewed_count: int = 0,
    ) -> str:
        """生成增量评审的 Markdown 摘要。

        用于 PR 增量评审场景，只输出本次 commit 的新 findings，
        不包含历史 findings。按 Security / Bug / Performance 分组输出。

        Args:
            findings: 本次新增的 Finding 列表。
            score: 本次评审总分。
            commit_sha: 正在评审的 commit SHA。
            unreviewed_count: 无法评审的文件数。

        Returns:
            Markdown 格式的增量摘要。
        """
        short_sha = commit_sha[:8]
        lines = [f"## AI 增量代码评审 — commit `{short_sha}`\n"]

        if score >= 90:
            rating = "\U0001f7e0 优秀"
        elif score >= 70:
            rating = "\U0001f7e1 良好"
        else:
            rating = "\U0001f534 待改进"
        lines.append(f"**本次评分：{score}/100** — {rating}\n")

        if unreviewed_count:
            lines.append(f"⚠ **{unreviewed_count} 个文件未能完成评审**\n")

        if not findings:
            lines.append("✅ 本次变更未发现新问题。\n")
            return "\n".join(lines)

        severity_icons = {
            FindingSeverity.CRITICAL: "\U0001f534",
            FindingSeverity.WARNING: "\U0001f7e1",
        }

        category_groups = [
            (FindingCategory.SECURITY, "Security"),
            (FindingCategory.BUG, "Bug"),
            (FindingCategory.PERFORMANCE, "Performance"),
        ]

        for cat, cat_label in category_groups:
            cat_findings = [f for f in findings if f.category == cat]
            if not cat_findings:
                continue

            lines.append(f"### {cat_label}（{len(cat_findings)} 项）\n")
            lines.append("| 严重性 | 位置 | 代码 | 问题 | 建议 |")
            lines.append("|--------|------|------|------|------|")

            for f in cat_findings:
                icon = severity_icons.get(f.severity, "⚪")
                location = f"`{f.file_path}:{f.line_start}`" if f.line_start else f"`{f.file_path}`"  # noqa: SIM108
                snippet = f"`{f.code_snippet}`" if f.code_snippet else ""
                title = f.title.replace("|", "\\|")
                suggestion = f.suggestion.replace("|", "\\|").replace("\n", " ")
                lines.append(
                    f"| {icon} **{f.severity.value.upper()}** | {location}"
                    f" | {snippet} | {title} | {suggestion} |"
                )
            lines.append("")

        return "\n".join(lines)
