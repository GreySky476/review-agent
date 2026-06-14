# Plan: 评审历史 MD 导出功能

> 状态：✅ 已完成 | 2026-06-14

---

## 进度

| 步骤 | 状态 | 文件 |
|------|------|------|
| 新建 api/export.py | ✅ 完成 | `api/export.py`（2 个端点） |
| 注册 export_router | ✅ 完成 | `api/app.py` |
| 前端加导出按钮 | ✅ 完成 | `ui/.../review-detail.tsx`, `ui/.../review-history-detail.tsx` |
| 验证 | ✅ 完成 | ruff ✅ mypy（仅预存错误） |

---

## 交付物

### 后端

| 端点 | 方法 | 用途 |
|------|------|------|
| `/api/v1/reviews/{review_id}/export/md` | GET | 单次评审导出为 MD，文件名 `review-{sha}.md` |
| `/api/v1/projects/{id}/pull-requests/{num}/export/md` | GET | PR 全量评审导出为 MD，文件名 `pr-{num}-review-report.md` |

两个端点均返回 `Content-Type: text/markdown` + `Content-Disposition: attachment`，浏览器直接触发下载。

### 前端

- **PR 详情页**（`review-detail.tsx`）：header 行右侧新增"📥 导出 MD"按钮，与"💬 评论"并排
- **评审历史详情页**（`review-history-detail.tsx`）：header 右侧新增"📥 导出 MD"按钮
- 使用 `window.open()` 直接触发下载，无需 loading 状态
- 按钮使用现有 `<Button variant="secondary" size="sm">`
