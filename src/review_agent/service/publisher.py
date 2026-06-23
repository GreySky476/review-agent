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

        # 严重性排序
        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.INFO: 2,
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
        - info: -3
        """
        deductions = {
            FindingSeverity.CRITICAL: 15,
            FindingSeverity.WARNING: 8,
            FindingSeverity.INFO: 3,
        }
        total_deduction = sum(deductions.get(f.severity, 0) for f in findings)
        return max(0, 100 - total_deduction)

    def should_generate_report(self, findings: list[DimensionFinding]) -> bool:
        """判断是否需要生成详细报告。

        当 critical 和 warning 的 Finding 数量超过阈值时返回 True。

        Args:
            findings: 去重后的 Finding 列表。

        Returns:
            是否需要生成详细报告。
        """
        serious_count = sum(
            1 for f in findings if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.WARNING)
        )
        threshold = int(self._settings.verbose_report_threshold)
        return serious_count > threshold

    def generate_summary(
        self,
        findings: list[DimensionFinding],
        score: int,
        unreviewed_count: int = 0,
    ) -> str:
        """生成 Markdown 格式的评审摘要。

        Findings 按重要性排序输出：先按严重性降序（critical→warning→info），
        同一严重性内按类别优先级降序（bug→security→performance→...）。

        Args:
            findings: 去重后的 Finding 列表。
            score: 评审总分。
            unreviewed_count: 因错误无法评审的文件数。

        Returns:
            Markdown 格式的摘要文本。
        """
        lines = ["## AI 代码评审结果\n"]

        # 评分评级
        if score >= 90:
            rating = "🟢 优秀"
        elif score >= 70:
            rating = "🟡 良好"
        else:
            rating = "🔴 待改进"

        lines.append(f"**总分：{score}/100** — {rating}\n")

        if unreviewed_count:
            lines.append(
                f"⚠ **{unreviewed_count} 个文件未能完成评审**（无法获取源码）\n",
            )

        if not findings:
            lines.append("✅ 未发现问题。\n")
            return "\n".join(lines)

        # 统计
        critical = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL)
        warning = sum(1 for f in findings if f.severity == FindingSeverity.WARNING)
        info = sum(1 for f in findings if f.severity == FindingSeverity.INFO)

        lines.append("### 概览\n")
        lines.append("| 严重性 | 数量 |")
        lines.append("|--------|------|")
        lines.append(f"| 🔴 Critical | {critical} |")
        lines.append(f"| 🟡 Warning | {warning} |")
        lines.append(f"| 🔵 Info | {info} |")
        lines.append("")

        # 排序：严重性降序 + 类别优先级降序
        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.INFO: 2,
        }
        category_priority = {
            FindingCategory.BUG: 0,
            FindingCategory.SECURITY: 1,
            FindingCategory.PERFORMANCE: 2,
            FindingCategory.STRUCTURE: 3,
            FindingCategory.STYLE: 4,
            FindingCategory.DEPENDENCY: 5,
        }

        sorted_findings = sorted(
            findings,
            key=lambda f: (
                severity_order.get(f.severity, 99),
                category_priority.get(f.category, 99),
            ),
        )

        # Markdown 表格输出（按重要性排列）
        severity_icons = {
            FindingSeverity.CRITICAL: "🔴",
            FindingSeverity.WARNING: "🟡",
            FindingSeverity.INFO: "🔵",
        }

        lines.append("### 问题详情\n")
        lines.append("| 严重性 | 类别 | 位置 | 问题 | 建议 |")
        lines.append("|--------|------|------|------|------|")
        for f in sorted_findings:
            icon = severity_icons.get(f.severity, "⚪")
            severity_label = f.severity.value.upper()
            location = f"`{f.file_path}`"
            if f.line_start:
                location += f":{f.line_start}"
            # 转义 Markdown 表格中的管道符
            title = f.title.replace("|", "\\|")
            suggestion = f.suggestion.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {icon} **{severity_label}** | {f.category.value} |"
                f" {location} | {title} | {suggestion} |"
            )

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
        不包含历史 findings。历史记录可通过 DB 查询。

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
            rating = "🟢 优秀"
        elif score >= 70:
            rating = "🟡 良好"
        else:
            rating = "🔴 待改进"

        lines.append(f"**本次评分：{score}/100** — {rating}\n")

        if unreviewed_count:
            lines.append(f"⚠ **{unreviewed_count} 个文件未能完成评审**（无法获取源码）\n")

        if not findings:
            lines.append("✅ 本次变更未发现新问题。\n")
            return "\n".join(lines)

        critical = sum(1 for f in findings if f.severity == FindingSeverity.CRITICAL)
        warning = sum(1 for f in findings if f.severity == FindingSeverity.WARNING)
        info = sum(1 for f in findings if f.severity == FindingSeverity.INFO)

        lines.append(f"发现 {len(findings)} 个新问题: ")
        if critical:
            lines.append(f"🔴 {critical} 个 Critical")
        if warning:
            lines.append(f"🟡 {warning} 个 Warning")
        if info:
            lines.append(f"🔵 {info} 个 Info")

        lines.append("")

        severity_order = {
            FindingSeverity.CRITICAL: 0,
            FindingSeverity.WARNING: 1,
            FindingSeverity.INFO: 2,
        }
        category_priority = {
            FindingCategory.BUG: 0,
            FindingCategory.SECURITY: 1,
            FindingCategory.PERFORMANCE: 2,
            FindingCategory.STRUCTURE: 3,
            FindingCategory.STYLE: 4,
            FindingCategory.DEPENDENCY: 5,
        }

        sorted_findings = sorted(
            findings,
            key=lambda f: (
                severity_order.get(f.severity, 99),
                category_priority.get(f.category, 99),
            ),
        )

        severity_icons = {
            FindingSeverity.CRITICAL: "🔴",
            FindingSeverity.WARNING: "🟡",
            FindingSeverity.INFO: "🔵",
        }

        lines.append("| 严重性 | 类别 | 位置 | 问题 | 建议 |")
        lines.append("|--------|------|------|------|------|")
        for f in sorted_findings:
            icon = severity_icons.get(f.severity, "⚪")
            location = f"`{f.file_path}`"
            if f.line_start:
                location += f":{f.line_start}"
            title = f.title.replace("|", "\\|")
            suggestion = f.suggestion.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {icon} **{f.severity.value.upper()}** | {f.category.value} |"
                f" {location} | {title} | {suggestion} |"
            )

        return "\n".join(lines)
