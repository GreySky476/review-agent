# 系统架构总览

> 文档版本：v1.2 | 更新日期：2026-06-15 | 关联文档：[模块边界](module-boundaries.md)、[API 规范](../api/conventions.md)

---

## 一、架构原则

系统采用 **异步解耦、无状态计算、存储下沉** 的架构原则：

| 原则 | 说明 |
|------|------|
| **异步解耦** | Webhook 接收与 AI 评审分离，通过消息队列削峰填谷 |
| **无状态计算** | API 层和 Worker 层支持水平扩展，状态下沉至数据库和缓存 |
| **存储下沉** | 所有持久化数据由专门的存储层管理，上层不直接操作存储 |

---

## 二、六层架构

```text
┌─────────────────────────────────────────────────────────┐
│                    接入层 (Ingress)                       │
│   Webhook 接收 / 签名验证 / 流量整形 / 协议适配            │
└──────────────┬──────────────────────────────────────────┘
               │ 事件
┌──────────────▼──────────────────────────────────────────┐
│              消息队列与任务层 (Queue)                     │
│      Celery/ARQ + Redis Stream / 持久化 / 死信队列        │
└──────────────┬──────────────────────────────────────────┘
               │ 任务
┌──────────────▼──────────────────────────────────────────┐
│              AI 评审引擎层 (Engine)                       │
│   LangGraph 编排 / 五维评审 / 规范检索 / 结果聚合          │
└──────────────┬──────────────────────────────────────────┘
               │ 平台调用
┌──────────────▼──────────────────────────────────────────┐
│            平台 API 网关层 (Gateway)                      │
│   GitHub / GitLab / Gitee 抽象 / 限流 / 重试 / 错误处理   │
└──────────────┬──────────────────────────────────────────┘
               │ 数据读写
┌──────────────▼──────────────────────────────────────────┐
│             数据与存储层 (Storage)                        │
│  PostgreSQL / Redis / MinIO / 读写分离 / 历史归档         │
└──────────────┬──────────────────────────────────────────┘
               │ API
┌──────────────▼──────────────────────────────────────────┐
│           管理后台与 API 层 (Admin)                       │
│   FastAPI / 前端 / 权限 / 审计 / 仪表盘                   │
└─────────────────────────────────────────────────────────┘
```

### 依赖方向

`types/` → `config/` → `repo/` → `service/` → `api/` → `ui/`

**禁止逆向依赖**，违反则 CI 不通过。

---

## 三、技术栈详情

### 3.1 后端

| 组件 | 选型 | 用途 |
|------|------|------|
| 语言 | Python 3.11+ | 运行时 |
| Web 框架 | FastAPI | 异步 Webhook 接收与管理后台 API |
| 任务队列 | ARQ + Redis | 异步化 AI 评审任务 |
| 数据库 | PostgreSQL 15+ | 主存储 |
| 缓存 | Redis 7+ | 缓存、分布式锁、ARQ 队列 |
| ORM | SQLAlchemy 2.0 (async) + Alembic | 数据库操作与迁移 |
| Git 平台 | PyGithub | GitHub API 封装 |
| AI 调用 | httpx → DeepSeek / OpenAI API | 代码评审大模型调用 |
| AI 编排 | LangGraph (已集成) | 有状态、可观测的评审流水线，节点：`service/review_graph/` |
| 代码解析 | tree-sitter (规划中) | AST 分析与指标提取 |
| 配置管理 | Pydantic Settings | 环境变量加载与验证 |
| 日志与追踪 | OpenTelemetry | 全链路追踪，结构化 JSON 日志 |

### 3.2 AI 模型

| 模型 | 用途 |
|------|------|
| deepseek-v4-flash / deepseek-v4-pro | 安全、Bug 等高价值维度审查（主模型） |
| deepseek-v4-flash / Claude Haiku | 规范、风格等经济维度审查 |
| vLLM + 开源模型 (Llama 3, Qwen 2) | 私有化部署，代码不出企业网络 |
| text-embedding-3-small / BGE-M3 | 规范知识库向量嵌入 |

### 3.3 前端

| 组件 | 选型 |
|------|------|
| 框架 | React 18+ + TypeScript |
| 构建工具 | Vite |
| 样式 | Tailwind CSS |
| 组件库 | shadcn/ui + Radix Themes |
| 图表 | Recharts / Tremor |
| 状态管理 | TanStack Query + Zustand |
| 路由 | React Router v6 |
| Diff 展示 | react-diff-viewer / 自研组件 |

### 3.4 基础设施

| 组件 | 选型 |
|------|------|
| 容器化 | Docker Compose（开发），Kubernetes（生产） |
| 监控 | Prometheus + Grafana（指标） |
| 日志 | Loki |
| 追踪 | Tempo |
| CI/CD | GitHub Actions / GitLab CI |
| 密钥管理 | HashiCorp Vault / 云平台 Secret Manager |

---

## 四、核心流程

### 4.1 PR 评审流程

```text
GitHub Webhook (pull_request: opened/synchronize/reopened)
       │
       ▼
webhook.py → 解析 event → 提取 repo_name + pr_number + action
       │
       ├── ensure_project_connected() → 查找 project → 记录 webhook_event
       ├── sync_pull_request() → upsert PR 数据到 pull_requests 表
       │
       ▼
   分支过滤（review_branches）
       │ 匹配
       ▼
   trigger_pr_review()
       │
       ├── get_pr_diff() 拉全量 diff（所有 commit 变更）
       ├── 查上次评审记录（增量上下文）
       ├── ReviewRepo.create(status=PENDING)
       └── enqueue_pr_review() → ARQ Redis 队列
       │
       ▼
   ARQ Worker: run_review()  (支持 LangGraph)
       │
       ├── 初始化 GitHubProvider + DeepSeekProvider
       ├── 加载企业规则到 KnowledgeBase
       ├── (可选) LangGraph 图编排
       │    ├── filter_files → 路径模式过滤（.claude/** 等）
       │    ├── fetch_and_chunk → 取源码 → 按函数分块
       │    ├── resolve_incremental → 对比上次评审，标记 new_chunks
       │    ├── 5 路并行规则检查 (Send) → 安全/Bug/性能/风格/依赖
       │    ├── route_chunks → AI 评审 (DeepSeek) / 结构评审
       │    └── aggregate → 去重 → 打分 → 摘要
       │
       ├── publish_summary_comment() → GitHub PR Comment（标注 commit SHA）
       ├── DB: ReviewModel + FindingModel 写入
       └── DB: pull_requests.last_reviewed_sha 更新
```

**增量评审**：二次 synchronize 时，对比上次评审的 `previous_file_paths`，只评审新增/修改的文件，已评文件跳过。

### 4.2 Push 评审流程

```text
GitHub Push Webhook (x-github-event: push)
       │
       ▼
handle_push_event()
       │
       ├── 查找 project → 标记 webhook_enabled
       ├── 提取 head_commit.sha + ref → branch
       ├── 分支过滤（review_branches）
       ├── CommitRepo → create/update
       ├── ReviewRepo.create(status=PENDING)
       └── enqueue_commit_review() → ARQ Redis 队列
       │
       ▼
ARQ Worker: run_commit_review()
       │
       ├── 初始化 GitHubProvider + DeepSeekProvider
       ├── 加载企业规则到 KnowledgeBase
       ├── CommitReviewService (文件级并发，Semaphore=3)
       │    ├── 路径模式过滤（.claude/** 等跳过）
       │    ├── get_file_content() → chunk_file() → 按函数分块
       │    ├── 逐 chunk:
       │    │   ├── ≤1500 → 规则检查 + RAG + AI 评审 (DeepSeek)
       │    │   ├── 1500~2000 → 规则检查 + 结构评审
       │    │   └── >2000 → 结构评审（圈复杂度/行数/参数）
       │    └── Publisher.aggregate() → 去重 → 打分
       │
       ├── publish_commit_summary() → GitHub Commit 评论
       └── DB: ReviewModel + FindingModel 写入
```

**与 PR 评审的关键区别：**

| 维度 | PR 评审 | Push 评审 |
|------|---------|-----------|
| 触发事件 | `pull_request` (opened/synchronize/reopened) | `push` |
| 数据来源 | `get_pr_diff()` 全量 diff | `get_commit_diff()` commit diff |
| 并发策略 | 文件级并发 (Semaphore=3) + LangGraph Send() | 文件级并发 (Semaphore=3) |
| 增量去重 | 支持（对比上次评审的 file_paths） | 不支持（单次 commit） |
| 评论位置 | PR Comment（标注 commit SHA） | Commit Comment |
| 进度追踪 | 更新 `pull_requests.last_reviewed_sha` | 无 |

### 4.3 平台心跳检测

系统每 1 分钟自动检测外部平台（GitHub/Gitee）的 API 连通性：

```text
FastAPI 启动 → lifespan
  → asyncio background task (每1分钟)
    → 创建 DB session
    → httpx GET api.github.com/user (with token)
    → httpx GET gitee.com/api/v5/user (with token)
    → PlatformHealthRepo.upsert() → platform_health 表
```

管理后台通过 `GET /health/platforms` 获取最新状态，含延迟和错误信息。
表数据实时反映平台可用性，展示在仪表盘供及时发现连接故障。

### 4.4 Webhook 连通性验证

| 方式 | 端点/来源 | 说明 |
|------|----------|------|
| GitHub Ping | `POST /api/webhook/github` (自动) | GitHub 创建/重发 webhook 时自动触发 |
| Gitee Test Hook | `POST /api/webhook/gitee` (自动) | Gitee 测试事件 |
| 手动验证 | `GET /api/webhook/health` | curl/浏览器直接访问验证服务在线 |
| **主动巡检（权威来源）** | `service/health.py:check_project_webhooks` | **每 5 分钟通过 GitHub API 验证 webhook 配置，更新 `project.webhook_enabled` — 这是 webhook 状态的权威来源** |

> **状态判定规则**：项目 webhook 状态仅由 `project.webhook_enabled` 决定（由主动巡检维护），`webhook_events` 表是被动事件日志，仅用于审计和调试，不参与状态判定。详见 [模块边界 → 状态判定与数据源规则](module-boundaries.md#六状态判定与数据源规则)。

### 4.5 数据同步策略

系统采用 **DB 优先 + 定时同步 + 手动刷新** 三层数据源策略，避免 PR 详情页加载时直接调用 GitHub API。

```text
用户加载 PR 详情
       │
       ├── commits 表有数据 → 直接返回（< 100ms） ✅
       │
       ├── 定时同步（ARQ，每 5 分钟）
       │   └── sync_project_data(project_id)
       │       ├── 遍历项目的所有活跃 PR
       │       ├── 调 GitHub API 获取 commits
       │       └── bulk_upsert 到 commits 表
       │
       └── 手动刷新（🔄 按钮）
           └── POST /projects/{id}/pull-requests/{num}/sync
               ├── 实时调 GitHub API
               ├── 更新 commits 表
               └── 返回最新数据
```

**定时调度器**在 FastAPI lifespan 中启动，复用 ARQ 任务队列。
详见 [数据同步功能设计](../features/data-sync/design.md)。

### 4.6 代码分块策略

| 分类 | Token 范围 | 处理方式 |
|------|-----------|---------|
| 正常块 | ≤ 1500 | 五个维度并行详细评审 |
| 边界块 | 1500 ~ 2000 | 五个维度并行详细评审 |
| 超大块 | > 2000 | 结构评审 + 最小化安全检查 |

---

## 五、非功能特性

| 维度 | 指标 |
|------|------|
| Webhook 接收延迟 | P99 < 500ms |
| 正常 PR 评审时间 | 3 分钟内完成评论 |
| API 查询 | P95 < 500ms，统计接口 ≤ 2s |
| 报告生成 | 30 秒内完成 |

详见各专项文档。

---

## 六、相关文档

- [模块边界定义](module-boundaries.md)
- [API 设计规范](../api/conventions.md)
- [安全编码规范](../security/guidelines.md)
- [测试策略](../testing/strategy.md)
- [CI/CD 部署](../deployment/ci-cd.md)
