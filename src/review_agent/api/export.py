"""评审历史 Markdown 导出 API。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import FindingModel, ProjectModel, ReviewModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["export"])

_SEVERITY_ICONS = {
    "critical": "🔴",
    "warning": "🟡",
    "info": "🔵",
}


def _render_findings_table(findings: list[FindingModel]) -> list[str]:
    """生成 findings 的 Markdown 表格。"""
    if not findings:
        return ["✅ 未发现问题。\n"]

    critical = sum(1 for f in findings if f.severity == "critical")
    warning = sum(1 for f in findings if f.severity == "warning")
    info = sum(1 for f in findings if f.severity == "info")

    lines = ["### 概览\n", "| 严重性 | 数量 |", "|--------|------|"]
    if critical:
        lines.append(f"| 🔴 Critical | {critical} |")
    if warning:
        lines.append(f"| 🟡 Warning | {warning} |")
    if info:
        lines.append(f"| 🔵 Info | {info} |")
    lines.append("")

    lines.extend([
        "### 问题详情\n",
        "| 严重性 | 类别 | 位置 | 问题 | 建议 |",
        "|--------|------|------|------|------|",
    ])

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    category_priority = {
        "bug": 0, "security": 1, "performance": 2,
        "structure": 3, "style": 4, "dependency": 5,
    }

    sorted_f = sorted(
        findings,
        key=lambda f: (
            severity_order.get(f.severity, 99),
            category_priority.get(f.category, 99),
        ),
    )

    for f in sorted_f:
        icon = _SEVERITY_ICONS.get(f.severity, "⚪")
        label = f.severity.upper()
        location = f"`{f.file_path}`"
        if f.line_start:
            location += f":{f.line_start}"
        title = f.title.replace("|", "\\|")
        suggestion = f.suggestion.replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {icon} **{label}** | {f.category} |"
            f" {location} | {title} | {suggestion} |"
        )

    return lines


def _score_rating(score: int | None) -> str:
    if score is None:
        return "—"
    if score >= 90:
        return "🟢 优秀"
    if score >= 70:
        return "🟡 良好"
    return "🔴 待改进"


def _incremental_label(idx: int, reviews_count: int) -> str:
    """判断是首次评审还是增量评审。"""
    if reviews_count == 1 or idx == 0:
        return "首次评审"
    return "增量评审"


# ── 单次评审导出 ─────────────────────────────────────────


@router.get("/reviews/{review_id}/export/md")
async def export_review_md(
    review_id: str,
    db: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    """导出单次评审为 Markdown 文件。"""
    row = await db.execute(
        select(ReviewModel, ProjectModel.name.label("project_name"))
        .join(ProjectModel, ReviewModel.project_id == ProjectModel.id)
        .where(ReviewModel.id == review_id, ReviewModel.is_deleted.is_(False))
    )
    result = row.one_or_none()
    if not result:
        return PlainTextResponse(
            f"# Review Not Found\n\nReview `{review_id}` does not exist.\n",
            media_type="text/markdown",
            status_code=404,
        )
    review, project_name = result

    finding_rows = await db.execute(
        select(FindingModel).where(
            FindingModel.review_id == review_id,
            FindingModel.is_deleted.is_(False),
        )
    )
    findings: list[FindingModel] = list(finding_rows.scalars().all())

    sha_short = review.head_sha[:8] if review.head_sha else "unknown"
    dt = review.create_time.strftime("%Y-%m-%d %H:%M:%S") if review.create_time else "—"
    score = review.score or 0
    lines = [
        "# AI Code Review Report\n",
        f"**Project:** {project_name}",
        f"**Commit:** `{sha_short}`",
        f"**Date:** {dt}",
        f"**Score:** {score}/100 — {_score_rating(score)}",
        "",
        f"**Findings:** {len(findings)} total",
        "",
        "---",
        "",
    ]
    lines.extend(_render_findings_table(findings))

    content = "\n".join(lines)
    return PlainTextResponse(
        content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": f'attachment; filename="review-{sha_short}.md"',
        },
    )


# ── PR 全量评审导出 ─────────────────────────────────────


@router.get("/projects/{project_id}/pull-requests/{pr_number}/export/md")
async def export_pr_reviews_md(
    project_id: str,
    pr_number: int,
    db: AsyncSession = Depends(get_session),
) -> PlainTextResponse:
    """导出 PR 所有评审记录为合并的 Markdown 文件。"""
    # 查项目
    proj_row = await db.execute(
        select(ProjectModel.name, ProjectModel.repo_url).where(
            ProjectModel.id == project_id,
            ProjectModel.is_deleted.is_(False),
        )
    )
    proj = proj_row.one_or_none()
    project_name = proj.name if proj else "Unknown"
    repo_url = proj.repo_url if proj else ""

    # 查该 PR 下所有已完成的 review（按时间升序）
    completed = [ReviewStatus.COMPLETED.value, ReviewStatus.COMPLETED_WITH_ERRORS.value]
    review_rows = await db.execute(
        select(ReviewModel)
        .where(
            ReviewModel.project_id == project_id,
            ReviewModel.pr_number == pr_number,
            ReviewModel.status.in_(completed),
            ReviewModel.is_deleted.is_(False),
        )
        .order_by(ReviewModel.create_time.asc())
    )
    all_reviews: list[ReviewModel] = list(review_rows.scalars().all())

    if not all_reviews:
        return PlainTextResponse(
            f"# AI Code Review Report — PR #{pr_number}\n\n暂无评审记录。\n",
            media_type="text/markdown",
        )

    # 查每个 review 的 findings
    review_ids = [r.id for r in all_reviews]
    finding_rows = await db.execute(
        select(FindingModel).where(
            FindingModel.review_id.in_(review_ids),
            FindingModel.is_deleted.is_(False),
        )
    )
    findings_by_review: dict[str, list[FindingModel]] = {rid: [] for rid in review_ids}
    for f in finding_rows.scalars().all():
        findings_by_review.setdefault(f.review_id, []).append(f)

    # 汇总表格
    summary_rows: list[str] = []
    lines = [
        f"# AI Code Review Report — PR #{pr_number}\n",
        f"**Repository:** {repo_url}",
        f"**Project:** {project_name}",
        f"**Reviews:** {len(all_reviews)} 次评审\n",
        "---\n",
    ]

    for i, rv in enumerate(all_reviews):
        rv_findings = findings_by_review.get(rv.id, [])
        sha_short = rv.head_sha[:8] if rv.head_sha else "unknown"
        dt = rv.create_time.strftime("%Y-%m-%d %H:%M") if rv.create_time else "—"
        review_type = _incremental_label(i, len(all_reviews))
        score = rv.score or 0

        lines.append(f"## Review #{i + 1} — {review_type}")
        lines.append(f"**Commit:** `{sha_short}` | **Date:** {dt}")
        lines.append(f"**Score:** {score}/100 — {_score_rating(score)}")
        lines.append(f"**Findings:** {len(rv_findings)}\n")
        lines.extend(_render_findings_table(rv_findings))
        lines.append("---\n")

        summary_rows.append(
            f"| {i + 1} | `{sha_short}` | {review_type} | {score} | {len(rv_findings)} |"
        )

    # 汇总表
    total_score = sum(r.score or 0 for r in all_reviews if r.score)
    avg_score = round(total_score / len(all_reviews), 1) if all_reviews else 0
    total_findings = sum(len(f) for f in findings_by_review.values())

    lines.extend([
        "## 汇总\n",
        "| # | Commit | 类型 | 评分 | Findings |",
        "|--:|--------|------|----:|---------:|",
        *summary_rows,
        f"| | **合计** | | **{avg_score}** | **{total_findings}** |",
        "",
    ])

    content = "\n".join(lines)
    return PlainTextResponse(
        content,
        media_type="text/markdown",
        headers={
            "Content-Disposition": (
                f'attachment; filename="pr-{pr_number}-review-report.md"'
            ),
        },
    )
