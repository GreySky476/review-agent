# PR 数据同步功能设计

> 文档版本：v1.0 | 更新日期：2026-06-15 | 关联：[架构总览](../../architecture/overview.md)

---

## 一、问题

PR 详情页 (`/projects/:id/prs/:prNumber`) 每次加载都调用 GitHub API 获取 PR 的 commit 列表：
- `get_repo()` + `get_pull()` + `get_commits()`（分页）
- 最少 3 次 HTTP 请求到 `api.github.com`
- 加载耗时约 4 秒

## 二、方案：三层数据源

```
                    ┌──────────────────┐
用户加载 PR 详情 →  │   commits 表(DB)  │ < 100ms ✅
                    └────────┬─────────┘
                             │ 无数据时返回空数组
                             ▼
                    ┌──────────────────┐
  🔄 手动刷新  →    │  GitHub API 直调  │ 实时同步
                    │  写 DB → 返回数据  │
                    └──────────────────┘
                             ▲
                    ┌──────────────────┐
  ARQ 定时 5 分钟 →  │ sync_project_data │ 后台保新
                    └──────────────────┘
```

### 2.1 DB 优先（默认路径）

`get_pull_request_detail` 从 `commits` 表查询：
```python
commit_records = await CommitRepo(db).list_by_pr(project_id, pr_number)
```

commits 表已有 `pr_number` 字段，无需迁移。无数据时返回空数组。

### 2.2 手动刷新（实时路径）

`POST /projects/{id}/pull-requests/{num}/sync`

用户在 PR 详情页点击 🔄 按钮时：
1. 调 GitHub API 获取该 PR 的最新 commits
2. `bulk_upsert` 到 commits 表（先删后插）
3. 返回最新 commits + review 状态
4. 前端 `refetch()` 展示

### 2.3 定时同步（后台路径）

ARQ Worker 函数 `sync_project_data(project_id)`：
- 在 FastAPI lifespan 中启动定时调度器
- 每 5 分钟遍历所有活跃项目
- 对每个项目：获取 Open PRs → 获取 commits → upsert 到 DB

## 三、数据流

### PR 详情页加载

```
请求 GET /projects/{id}/pull-requests/{num}
  → 查 commits 表 → 查 reviews 表（匹配 head_sha）
  → 合并为 commits_data（commit + review 状态）
  → 返回
```

### 手动刷新

```
点击 🔄 按钮
  → POST /sync
  → GitHubProvider.get_pr_commits()
  → CommitRepo.bulk_upsert()  // 删旧写新
  → db.commit()
  → 返回最新数据
  → 前端 refetch()
```

### 定时同步

```
FastAPI lifespan → start_sync_scheduler
  → asyncio.create_task(_sync_loop)
  → 每 300 秒：
      → 查活跃项目
      → 向 ARQ 入队 sync_project_data(project_id)
      → Worker 执行：
          → GitHubProvider.list_open_prs()
          → 遍历 PR: get_pr_commits() → bulk_upsert()
          → upsert pull_requests 表
```

## 四、关键方法

### CommitRepo

| 方法 | 说明 |
|------|------|
| `list_by_pr(project_id, pr_number)` | 查询某 PR 的 commit 列表 |
| `bulk_upsert(project_id, pr_number, commits)` | 先删该 PR 旧记录，再批量插入新记录 |

### GitHubProvider

| 方法 | 说明 |
|------|------|
| `list_open_prs(repo_name)` | 列出仓库所有 Open PR |
| `get_pr_commits(repo_name, pr_number)` | 获取 PR 的 commit 列表（已有） |

### ARQ Worker

| 函数 | 说明 |
|------|------|
| `sync_project_data(project_id)` | 同步单个项目的所有 PR 数据 |

## 五、相关文件

| 文件 | 职责 |
|------|------|
| `repo/commit.py` | `list_by_pr()` + `bulk_upsert()` |
| `api/prs.py` | PR 详情读 DB + sync 端点 |
| `service/queue.py` | `sync_project_data` worker 函数 |
| `service/scheduler.py` | 定时调度器（5 分钟间隔） |
| `service/git/github_provider.py` | `list_open_prs()` |
| `api/app.py` | lifespan 启动 scheduler |
| `ui/src/pages/review-detail.tsx` | 🔄 刷新按钮 |

## 六、变更记录

| 日期 | 变更内容 |
|------|----------|
| 2026-06-15 | 初稿 |
