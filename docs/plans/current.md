# Plan: Webhook 日志增强 + Review 流程修复

> 状态：✅ 已完成 | 2026-06-14

---

## 改动

### 1. webhook.py — 日志全面增强

之前只有 3 条 info log，现在每个决策点都有清晰的带 `[delivery_id]` 前缀的结构化日志：

| 场景 | 日志内容 |
|------|---------|
| 事件到达 | `Webhook[xxx] received: event=push` |
| ping | `Webhook[xxx] ping: hook_id=42` |
| push 处理 | `Webhook[xxx] push event -> handle_push_event` → `Webhook[xxx] push result: status=accepted` |
| PR project 查找 | `Webhook[xxx] project found: id=...` 或 `Webhook[xxx] project not found for repo=...` |
| PR 同步 | `Webhook[xxx] PR synced: project=... pr=6` |
| 分支过滤 | `Webhook[xxx] branch skipped: base='main' not in ['release/*']` |
| 触发评审 | `Webhook[xxx] triggering PR review: pr=6 sha=abc12345` |
| 非触发 | `Webhook[xxx] no review: action=opened` |
| 解析失败 | `Webhook[xxx] parse failed: repo=None` |
| 最终结果 | `Webhook[xxx] accepted: pr=6 action=opened` |

### 2. webhook_helpers.py — `trigger_pr_review` 修复

| 问题 | 修复 |
|------|------|
| 标题"PR #6" | 改为从 `PullRequestModel.title` 取真实 PR 标题 |
| diff 失败静默跳过 | 改为创建 FAILED 状态的 review 记录，让用户知道出错了 |
| enqueue 失败无日志 | 区分 task_id 有无分别 log |
| 增量上下文无日志 | log 是否找到上次 review 及其 files 数 |

### 3. 前端 reviews.tsx

路由和点击跳转 `navigate(\`/reviews/${review.id}\`)` 正确，PR 行可点击。
