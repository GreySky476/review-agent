# Plan: PR 详情页数据链路重构（DB 优先 + 定时同步 + 手动刷新）

> 状态：✅ 已完成 | 2026-06-15 ｜ 根据 `docs/features/data-sync/design.md` 实施

---

## 任务完成情况

### 第一阶段：Git 平台抽象层

- [x] 1. `service/git/base.py` — 新增 `list_open_prs()` 抽象方法
- [x] 2. `service/git/github_provider.py` — 实现 `list_open_prs()`

### 第二阶段：数据访问层

- [x] 3. `repo/commit.py` — 新增 `list_by_pr()` + `bulk_upsert()`

### 第三阶段：后台任务层

- [x] 4. `service/queue.py` — 新增 `sync_project_data` worker + `_extract_repo_name_from_url`
- [x] 5. `service/scheduler.py` — **新增**：定时同步调度器（5 分钟间隔）

### 第四阶段：API 层

- [x] 6. `api/prs.py` — 新增 `POST /projects/{id}/pull-requests/{num}/sync` 端点
- [x] 7. `api/prs.py` — `get_pull_request_detail` 改为从 commits 表读数据（DB 优先）

### 第五阶段：应用组装

- [x] 8. `api/app.py` — lifespan 启动 scheduler

### 第六阶段：前端

- [x] 9. `ui/src/hooks/use-reviews.ts` — 新增 `useSyncPullRequest()` hook
- [x] 10. `ui/src/pages/review-detail.tsx` — PR 详情页添加 🔄 刷新按钮

### 测试与验证

- [x] 11. 修复 `test_queue.py` 中过时的测试断言（2 → 3 个 worker 函数）
- [x] 12. 新增 `sync_project_data` 和 `_extract_repo_name_from_url` 单元测试
- [x] 13. `ruff check .` → All checks passed （修复 3 个 lint 问题）
- [x] 14. `mypy src/` → 仅剩预存错误（非本次改动引入）
- [x] 15. `pytest --no-cov` → 272 passed

## 验证结果

| 检查项 | 结果 |
|--------|------|
| `ruff check .` | ✅ All checks passed |
| `mypy src/` | ✅ 无新增错误（仅预存 40 个） |
| `pytest` | ✅ 272 passed（+2 新测试） |

## 详细改动摘要

### `service/git/base.py`
- 新增 `list_open_prs()` 抽象方法，返回 `list[dict[str, Any]]`

### `service/git/github_provider.py`
- 实现 `list_open_prs()`，使用 `get_pulls(state="open")`

### `repo/commit.py`
- `list_by_pr(project_id, pr_number)` → 按 PR 编号查询 commits
- `bulk_upsert(project_id, pr_number, commits)` → 先删后插批量写入

### `service/queue.py`
- `sync_project_data` → 同步单个项目的所有 Open PR 数据
- `_extract_repo_name_from_url` → URL 解析辅助函数
- `WorkerSettings.functions` → 注册 `sync_project_data`

### `service/scheduler.py`
- 后台异步循环，每 5 分钟遍历所有活跃项目，向 ARQ 入队 `sync_project_data`

### `api/prs.py`
- `get_pull_request_detail`：从 commits 表读取数据（DB 优先），无数据返回空数组
- `POST /sync`：手动触发同步，调 GitHub API → `bulk_upsert` → 返回带 review 状态的数据

### `api/app.py`
- lifespan 中启动 `start_sync_scheduler(interval_minutes=5)`

### UI
- `useSyncPullRequest` hook（POST + 自动刷新 query cache）
- PR 详情页 header 添加 「🔄 刷新」 按钮（同步中显示 ⏳ 同步中...）
