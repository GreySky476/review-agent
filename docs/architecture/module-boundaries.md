# 模块边界定义

> 文档版本：v1.1 | 更新日期：2026-06-09 | 关联文档：[架构总览](overview.md)、[API 规范](../api/conventions.md)

---

## 一、模块分层与依赖规则

```text
types/ ──→ config/ ──→ repo/ ──→ service/ ──→ api/ ──→ ui/
  │           │           │           │           │
  ▼           ▼           ▼           ▼           ▼
 纯数据类型  配置加载   数据访问    业务逻辑    HTTP 路由
```

### 核心规则

1. **依赖方向不可逆**：上层模块可以依赖下层，下层绝对不能依赖上层
2. **同层可调用**：同层模块之间可以通过接口互相调用
3. **依赖注入**：关键组件通过构造函数注入，便于测试替换

---

## 二、各层职责

### 2.1 types/ — 数据模型层

- 定义 Pydantic BaseModel / dataclass
- 定义枚举常量
- 定义类型别名
- **禁止**：导入任何业务模块

### 2.2 config/ — 配置层

- 定义 Pydantic Settings 模型
- 加载环境变量并验证
- **禁止**：运行时可变状态

### 2.3 repo/ — 数据访问层

- SQLAlchemy async repository 模式
- CRUD 操作封装
- 查询构建
- **禁止**：业务逻辑判断

### 2.4 service/ — 业务逻辑层

- 评审流水线编排
- 结果聚合与发布策略
- 调用外部 API（Git 平台、AI 模型）
- **禁止**：直接暴露 HTTP 端点

### 2.5 api/ — API 路由层

- FastAPI router 定义
- 请求/响应序列化
- 认证与权限校验
- **禁止**：业务逻辑实现
- **禁止**：从非权威数据源推导系统状态（见第六节）

### 2.6 ui/ — 前端展示层

- React 组件
- 状态管理（TanStack Query / Zustand）
- **禁止**：直接访问数据库

---

## 三、模块目录约定

```
src/
├── types/                     # 数据模型
│   ├── __init__.py
│   ├── enums.py               # 枚举常量
│   ├── exceptions.py          # 异常定义
│   ├── models.py              # Pydantic 请求/响应模型
│   └── orm.py                 # SQLAlchemy ORM 模型
├── config/
│   ├── __init__.py
│   ├── database.py            # DB Session 管理
│   ├── logging.py             # 日志配置
│   └── settings.py            # Pydantic Settings
├── repo/                      # 数据访问层
│   ├── __init__.py
│   ├── base.py                # 通用 CRUD 基类
│   ├── commit.py              # 提交 CRUD
│   ├── comment.py             # 评论 CRUD
│   ├── finding.py             # Finding CRUD
│   ├── project.py             # 项目 CRUD
│   ├── pull_request.py        # PR CRUD
│   ├── quality_snapshot.py    # 质量快照 CRUD
│   ├── review.py              # 评审记录 CRUD
│   ├── review_error.py        # 错误日志 CRUD
│   ├── rule.py                # 规则 CRUD
│   ├── user.py                # 用户 CRUD
│   └── webhook_event.py       # Webhook 事件 CRUD
├── service/                   # 业务逻辑层
│   ├── __init__.py
│   ├── chunking.py            # 代码分块
│   ├── commit_review.py       # Push 评审编排（M2）
│   ├── publisher.py           # 结果聚合与发布
│   ├── queue.py               # ARQ 任务队列集成
│   ├── ai/                    # AI 模型调用
│   │   ├── __init__.py
│   │   ├── base.py            # AIProvider 抽象
│   │   ├── deepseek.py        # DeepSeek 实现
│   │   └── types.py           # AI 数据模型
│   ├── dimensions/            # 评审维度
│   │   ├── __init__.py
│   │   ├── base.py            # 五维评审 + Finding 定义
│   │   └── structure.py       # 超大块结构评审
│   ├── git/                   # Git 平台适配
│   │   ├── __init__.py
│   │   ├── base.py            # GitProvider 抽象
│   │   └── github_provider.py # GitHub 实现
│   └── knowledge/             # 规范知识库
│       ├── __init__.py
│       └── service.py
├── api/                       # API 路由层
│   ├── __init__.py
│   ├── app.py                 # FastAPI 应用组装
│   ├── commits.py             # 提交 API
│   ├── dashboard.py           # 仪表盘 API
│   ├── errors.py              # 错误日志 API
│   ├── health.py              # 健康检查
│   ├── projects.py            # 项目管理 API
│   ├── prs.py                 # PR 管理 API
│   ├── reviews.py             # 评审 API
│   └── webhook.py             # Webhook 接收
└── ui/                        # 前端代码（另行管理）
    ├── src/
    ├── package.json
    └── vite.config.ts
```

---

## 四、模块间通信规范

| 通信方向 | 方式 | 示例 |
|---------|------|------|
| Webhook → Queue | 消息队列 | Redis Stream / RabbitMQ |
| Queue → Worker | 消费者组 | Celery task / ARQ |
| Worker → AI | gRPC / HTTP | LangChain call |
| Worker → Git | HTTP | GitHub API / GitLab API |
| API → DB | ORM | SQLAlchemy async |
| API → Cache | SDK | Redis async client |

---

## 五、边界违规处理

CI 中通过 `import-lint` 工具验证依赖方向：

```bash
# 验证 types/ 不依赖 config/
grep -r "from src\.config" src/types/ && exit 1

# 验证 api/ 不直接操作 repo/
grep -r "from src\.repo" src/api/ && exit 1
```

违反依赖方向规则的提交**不予合并**。

---

## 六、状态判定与数据源规则

> 本节的三个原则源自一次 Webhook 状态判定错误的事故复盘，详见 `docs/reflections/2026-06-14-webhook-status-architecture.md`。

### 6.1 单一权威数据源原则

**每个系统状态字段必须由一个确定的权威数据源维护，API 层只查询该数据源，不重新计算。**

如果一个后台任务（如心跳巡检）已经在模型上维护了一个布尔/枚举状态字段（如 `project.webhook_enabled`），API 层必须直接使用该字段，不得从其他表重新推导相同状态。

🔴 **反模式**（本项目实际发生）：`_format_project()` 从 `webhook_events` 表查询最后事件时间并用 24 小时间隔推导连接状态，忽略了 `project.webhook_enabled`。

```python
# ❌ 错误：从事件日志表推导状态
elif (datetime.now(UTC) - webhook_last_event_at) > timedelta(hours=24):
    webhook_status = "inactive"
```

🟢 **正确模式**：

```python
# ✅ 正确：直接使用权威数据源
webhook_status = "disconnected" if not project.webhook_enabled else "connected"
```

**检测方法**：当编写一个计算状态（connected/disconnected、active/inactive）的函数时，先检查对应模型上是否已有表示此概念的字段。如果有，直接使用，不再重新计算。

### 6.2 日志表不作为状态表

**职责为记录事件的表（审计日志、事件流、`webhook_events`）不可用于推导系统状态。日志表中的事件缺失不等于系统故障——它可能仅表示一段无活动期。**

🔴 **反模式**：

```python
# ❌ 错误：用事件日志的缺席推断系统故障
last_event = await webhook_repo.last_event_time(project_id)
if last_event and (now - last_event) > 24h:
    status = "inactive"  # 误报——可能只是项目无活动
```

🟢 **正确模式**：

- 状态字段应由专门的生命周期过程维护（心跳、Worker、事件处理器）
- 日志表只用于：审计追溯、调试排查、事件重放
- 如果确实需要从事件推导状态，创建一个专门的汇总表或状态字段，由事件处理器在事件到达时更新

**检测方法**：如果查询以 `WHERE event_table.project_id = X ORDER BY create_time DESC LIMIT 1` 开头，且意图是用结果判定系统功能是否正常——这是一个代码异味。

### 6.3 测试端点只验证不修复

**"测试连接"类型的端点应当是只读的验证操作。它检查系统状态并报告结果，不应通过副作用来补偿其他代码路径的缺陷。**

🔴 **反模式**（本项目实际发生）：

```python
# ❌ 错误：测试端点写数据库来"修复"状态显示
result = await git.check_webhook(...)
if result["found"]:
    await WebhookEventRepo(db).create_from_payload(...)  # 副作用
    await db.flush()
```

🟢 **正确模式**：

```python
# ✅ 正确：测试端点只验证并报告
result = await git.check_webhook(...)
if result["found"]:
    project.webhook_enabled = True  # 更新权威字段
    await db.flush()
return result
```

**检测方法**：如果测试端点的处理函数包含写数据库的副作用，问自己：这个副作用是在补偿其他代码路径的缺陷吗？如果是，修复那个缺陷，而不是在这里打补丁。

---

## 七、关联文档

- [架构反思：Webhook 状态判定数据源错误](../reflections/2026-06-14-webhook-status-architecture.md)
- [架构总览](overview.md)

