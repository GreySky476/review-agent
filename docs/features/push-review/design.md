# GitHub Push Webhook 自动代码评审 — 设计文档

> 文档版本：v1.1 | 更新日期：2026-06-10 | 关联：`docs/project-design.md`

---

## 一、概述

### 1.1 需求背景

当开发者向仓库推送代码时，系统应自动触发 AI 代码评审，将评审结果以评论形式发布到 GitHub 的对应 commit 上。评审应同时利用规则检查（零成本）和 AI 分析（上下文理解），并在 token 消耗和建议质量之间取得平衡。

### 1.2 触发条件

- **事件源**：GitHub Push Webhook（`x-github-event: push`）
- **评审范围**：仅 head commit（推送的最新提交），不逐个审查中间提交
- **跳过规则**：扩展名在 `review_skip_extensions` 中的文件（默认 `.md, .rst, .txt`）

---

## 二、系统流程

```
GitHub Push Webhook
  │ POST /webhook/github (x-github-event: push)
  ▼
webhook.py / _handle_push_event()
  │ 解析 payload → repo_name, head_commit, changed_files
  │ 保存 commit 记录 → CommitRepo.create()
  │ 入队 → enqueue_commit_review()
  ▼
ARQ Worker: run_commit_review()
  │ 初始化 GitHubProvider + DeepSeekProvider
  │ 调用 CommitReviewService.review_commit()
  ▼
CommitReviewService
  │ 遍历每个 changed file
  │   跳过 removed 文件和跳过扩展名
  │   获取文件源码 → get_file_content()
  │   分块 → chunk_file()
  │   对每个 chunk:
  │     ├─ 规则检查（全量，零成本）
  │     ├─ ≤1500 tokens → AI 评审（DeepSeek）
  │     ├─ 1500~2000 → 结构评审，跳过 AI
  │     └─ >2000 tokens → 结构评审，跳过 AI
  │   聚合 → Publisher.aggregate() + generate_summary()
  │   发布 → publish_commit_summary()
  ▼
GitHub Commit 评论
```

---

## 三、Token 与质量平衡策略

| Chunk 类型 | Token 范围 | 执行策略 | 原因 |
|------------|-----------|----------|------|
| Normal (详细评审) | ≤1500 | 规则检查 + AI 评审 | 最佳性价比：AI 能理解完整函数上下文 |
| Boundary (边界) | 1500-2000 | 规则检查 + 结构评审 | 接近边界，AI 收益递减，跳过 |
| Oversized (超大) | >2000 | 结构评审（圈复杂度/行数/参数） | AI prompt 过长浪费 token，仅结构检查 |

### 3.1 AI Prompt 设计

AI 调用发送函数源码 + diff + 注入语言特定评审规范：

```
System: ## 语言特定代码评审规范
        （由 standards.py 自动检测语言并注入对应规范 Markdown，
         如 python.md 按重要性分层：资源管理>并发>正确性>安全>性能>规范）

        你是一位资深代码评审专家。请严格参照上述规范审查下方的代码变更，
        找出其中的违规项、正确性缺陷、安全风险、错误处理遗漏和逻辑错误。
        以 JSON 数组格式返回。

User:   ## 函数源码（path/to/file.py）
        ```
        def foo():
            ...
        ```
        ## Diff
        ```diff
        @@ -1,5 +1,8 @@
         ...
        ```
```

返回格式：
```json
[
  {
    "severity": "critical|warning|info",
    "title": "问题标题",
    "description": "详细描述",
    "suggestion": "修复建议",
    "line": 42
  }
]
```

### 3.2 输出格式

评审结果以 Markdown 表格输出，按重要性排序：

```
## AI 代码评审结果

**总分：92/100** — 🟢 优秀

### 概览

| 严重性 | 数量 |
|--------|------|
| 🔴 Critical | 1 |
| 🟡 Warning | 2 |
| 🔵 Info | 0 |

### 问题详情

| 严重性 | 类别 | 位置 | 问题 | 建议 |
|--------|------|------|------|------|
| 🔴 **CRITICAL** | BUG | `app.py:42` | 资源未关闭 | 使用 `with` 语句管理文件句柄 |
| 🟡 **WARNING** | SECURITY | `db.py:15` | SQL 注入风险 | 使用参数化查询 |
| 🟡 **WARNING** | BUG | `util.py:33` | 裸 except | 指定异常类型 |
| 🔵 **INFO** | STYLE | `views.py:120` | 函数过长 | 拆分为小函数 |
```

排序规则：先按严重性降序（CRITICAL → WARNING → INFO），
同一严重性内按类别优先级降序（BUG → SECURITY → PERFORMANCE → STRUCTURE → STYLE → DEPENDENCY）。

---

## 四、模块职责

### 4.1 `service/git/base.py` — GitProvider 抽象

新增抽象方法：
- `get_commit_diff(repo_name, sha) → list[PRFile]`
- `publish_commit_summary(repo_name, sha, summary)`

### 4.2 `service/git/github_provider.py` — GitHubProvider 实现

使用 PyGithub：
- `repo.get_commit(sha).files` → 获取变更文件（含 patch）
- `commit.create_comment(body)` → 发布 commit 评论

### 4.3 `service/commit_review.py` — CommitReviewService（新增）

核心编排逻辑：
- `review_commit(repo_name, sha, files) → CommitReviewResult`
- `_review_file()` → 单个文件的处理
- `_review_chunk()` → 按 chunk 类型分流
- `_ai_review_chunk()` → AI 评审调用
- `_parse_ai_response()` → 解析 AI 返回的 JSON findings

### 4.4 `service/queue.py` — 任务队列

- `enqueue_commit_review()` → 入队函数
- `run_commit_review()` → ARQ worker

### 4.5 `api/webhook.py` — Webhook 入口

- `_handle_push_event()` → 解析 push payload，保存 commit，入队

---

## 五、边界情况

| 场景 | 处理方式 |
|------|----------|
| 空 push（无 head_commit） | 忽略，返回 `ignored` |
| 无对应项目（未注册仓库） | 忽略，返回 `ignored` |
| 无变更文件 | 正常返回 `accepted`，跳过评审 |
| AI API 调用失败 | 仅做规则检查，日志告警，不阻塞 |
| GitHub API 发布评论失败 | 评审结果仍保存，发布失败只记日志 |
| 超大文件（>2000 tokens） | 跳过大文件/超大函数，仅结构评审 |

---

## 六、文件清单

| 文件 | 类型 | 说明 |
|------|------|------|
| `src/review_agent/service/git/base.py` | 修改 | +2 抽象方法 |
| `src/review_agent/service/git/github_provider.py` | 修改 | +2 实现 + auth 修复 |
| `src/review_agent/service/commit_review.py` | 新增 | 评审编排核心（~110行） |
| `src/review_agent/service/queue.py` | 修改 | +worker + 入队函数 |
| `src/review_agent/api/webhook.py` | 修改 | +push 事件处理 |
| `tests/unit/test_commit_review.py` | 新增 | 11 个测试 |
| `tests/unit/test_queue.py` | 修改 | worker 测试 |

---

## 七、LangGraph 集成

从 M2 起，评审流水线可选由 LangGraph StateGraph 驱动。

### 7.1 模块路径

```
src/review_agent/service/review_graph/
├── state.py          # ReviewState TypedDict + reducer
├── graph.py          # StateGraph 构建与编译
├── evaluation.py     # 5 维度规则节点 + AI/结构评审节点
├── pipeline.py       # 流程编排节点（过滤、拉取、聚合、摘要、发布）
├── edges.py          # 条件路由（Send 并行分发）
└── checkpointer.py   # 检查点器
```

### 7.2 启用方式

配置项 `REVIEW_AGENT_USE_LANGGRAPH=true` 开启。开启后行为不变（Phase 1.1），但获得：

- **有状态编排**：TypedDict 状态透传所有节点
- **并行规则检查**：5 个维度通过 `Send()` API 并行执行（Phase 1.2）
- **Checkpointing**：支持进程内中断恢复
- **可观测**：LangGraph 内置步骤追踪

### 7.3 节点流转图

```
START → filter_files → fetch_and_chunk
    ↓ (fanout_to_dimensions — 5 × Send)
run_security / run_bug / run_perf / run_style / run_dep
    ↓ (汇聚到 dispatch_chunks)
dispatch_chunks → route_chunks (按 chunk 类型)
    ├── ai_review (正常 chunk)
    └── structural_review (超大 chunk)
    ↓
aggregate → summarize → publish → END
```

### 7.4 容错

AI Provider 为 `None` 时，`ai_review` 节点跳过，仅执行规则和结构评审。
Git 发布失败仅记录警告，不影响评审结果。
所有节点异常由 LangGraph 捕获，状态可检查点恢复。
