# Plan: Commit 评审分支过滤

> 状态：已完成 | 2026-06-10

---

## Context

当前系统对所有分支的 push 都会触发 AI 评审。实际场景中，只有 main、develop、release/* 等稳定分支需要评审，feature 和个人分支的大量推送会导致不必要的 AI 调用和噪声。

**目标**：在每个项目的配置中指定需要触发评审的分支模式，push webhook 只对匹配分支触发评审。

---

## 设计要点

| 问题 | 决策 |
|------|------|
| 配置存储 | 使用 `ProjectModel.settings` JSON 字段（已存在），新增 `review_branches` 键 |
| 匹配方式 | `fnmatch` 通配符（支持 `main`, `release/*`, `feature/*`），默认 `["*"]`（全员匹配） |
| 过滤位置 | `webhook_helpers.py` 的 `handle_push_event()` 中，提取 branch 后立即检查 |
| 前端的 API | 复用现有 `PATCH /projects/{id}` + `ProjectUpdate`，新增 `review_branches` 字段 |
| 前端 UI | 在项目设置弹窗中追加"分支过滤"配置区，输入框 + 提示文字 |

---

## 完成工作

### 后端

| 文件 | 操作 |
|------|------|
| `src/review_agent/types/models.py` | — `ProjectUpdate` 新增 `review_branches: list[str] \| None` |
| `src/review_agent/repo/project.py` | — 新增 `get_settings()`、`update_settings()`、`get_review_branches()`（默认 `["*"]`） |
| `src/review_agent/api/projects.py` | — `_format_project()` 返回 `review_branches`；`update_project()` 接收并写入 settings JSON |
| `src/review_agent/api/webhook_helpers.py` | — `handle_push_event()` 提取 branch 后 `fnmatch` 检查；不匹配则跳过并返回 |

### 前端

| 文件 | 操作 |
|------|------|
| `ui/src/hooks/use-projects.ts` | — `Project` 接口新增 `review_branches`；新增 `useUpdateProject()` mutation |
| `ui/src/pages/project-detail.tsx` | — 设置弹窗新增"评审分支过滤"区域，含输入框、保存按钮、成功/错误反馈、使用示例 |

### 测试

| 文件 | 操作 |
|------|------|
| `tests/unit/test_webhook_helpers.py` | — 13 个测试：精确匹配、通配符、默认值、无效 JSON、settings 合并 |

## 数据流

```
Push Webhook → handle_push_event()
  → 提取 repo_url → 查找 Project
  → 提取 branch (from ref)
  → 读 project.settings.review_branches（默认 ["*"]）
  → fnmatch 匹配 branch
     ├── 匹配 → 继续评审流程（保存 commit + 入队）
     └── 不匹配 → log + return {"status": "skipped", "reason": "branch_not_matched"}
```

## 验证结果

```
pytest          → 236 passed ✓
ruff check .    → 通过（仅预存 issue）
mypy src/       → 通过（预存类型标记，非本次改动）
```
