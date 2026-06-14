# PR 多 Commit 增量评审

> 文档版本：v1.0 | 更新日期：2026-06-14 | 关联：[架构总览](../architecture/overview.md#41-pr-评审流程)

---

## 背景

当开发者向一个已打开的 PR 推送新 commit（GitHub 发送 `action: synchronize`），系统应自动触发评审，但不应重复评审之前已评过的文件。需要支持跨 commit 增量去重。

---

## 数据流

```
首次 synchronize (commit A):
  → get_pr_diff() 拉全量 diff
  → 评审所有文件
  → DB: review + findings（独立记录）
  → GitHub PR Comment: 首次完整摘要
  → pull_requests.last_reviewed_sha = sha(A)

二次 synchronize (commit B):
  → get_pr_diff() 拉全量 diff
  → 查 pull_requests.last_reviewed_sha → 获前次 review 的 file_paths
  → fetch_and_chunk 所有文件
  → resolve_incremental → new_chunks（file_path 不在上次的）
  → 只评 new_chunks
  → DB: 新 review + 新 findings（独立记录）
  → GitHub PR Comment: 追加增量摘要（标注 commit SHA）
  → pull_requests.last_reviewed_sha = sha(B)
```

**不继承旧 finding**：各次 review 独立记录，不合并 findings。历史可通过 `reviews` 表按 `project_id + pr_number` 查询。

---

## LangGraph 节点

```
START
  → filter_files（路径模式过滤）
  → fetch_and_chunk（取源码 + 按函数分块）
  → resolve_incremental（对比 previous_file_paths → new_chunks）
  → [fanout over new_chunks] → 5 路并行规则检查（Send）
  → route_chunks（按类型分 AI/结构评审）
  → aggregate（去重 + 打分）
  → summarize（生成 Markdown）
  → END
```

---

## 关键设计

| 方面 | 决策 |
|------|------|
| 增量依据 | `previous_file_paths`：上次已评的 file_path 集合 |
| 去重粒度 | file 级（chunk 按 file_path 筛选） |
| findings 继承 | 不继承，各 review 独立 |
| GitHub 评论 | 首次完整摘要，增量标注 commit SHA |
| 进度追踪 | `pull_requests.last_reviewed_sha` |
| Checkpointer | `thread_id = pr:{repo}:{pr_number}:{sha[:12]}` |

---

## 表结构变更

`PullRequestModel` 新增：

| 字段 | 类型 | 说明 |
|------|------|------|
| `last_reviewed_sha` | String(64), nullable | 上次评审的 commit SHA |
| `last_review_id` | String(36), FK→reviews.id, nullable | 上次评审的 review ID |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `api/webhook_helpers.py` | `trigger_pr_review()` 改用 `get_pr_diff()` + 增量上下文 |
| `service/queue.py` | `run_review()` 替换 stub + `enqueue_pr_review()` |
| `service/review_graph/pipeline.py` | `resolve_incremental` 节点 + `aggregate_findings` 改进 |
| `service/review_graph/edges.py` | fanout/route 基于 `new_chunks` |
| `service/review_graph/state.py` | ReviewState 新增增量字段 |

---

## 变更记录

| 日期 | 变更内容 |
|------|----------|
| 2026-06-14 | 初稿 |
