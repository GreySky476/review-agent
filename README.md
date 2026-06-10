# review-agent

企业级多平台智能代码评审与研发效能平台。

> **定位**：研发质量与产出可观测性平台，而非简单的 PR 评论机器人。
>
> [完整产品设计](docs/project-design.md) | [架构总览](docs/architecture/overview.md)

---

## 核心特性

- **风险左移**：PR 合并前自动发现安全漏洞、逻辑 Bug、性能隐患、边界问题、依赖风险
- **规范内建**：企业自定义审查规范知识库，AI 严格按规范评审
- **无感接入**：通过 Webhook 或 API 触发，自动运行
- **可观测**：跨仓库、跨成员的提交活跃度、质量趋势、问题分布仪表盘
- **自适应**：超大函数自动降级为结构评审，建议拆分重构
- **多平台**：支持 GitHub / GitLab / Gitee

---

## 快速开始

### 前置条件

- Python ≥ 3.12
- [uv](https://docs.astral.sh/uv/) 包管理器
- PostgreSQL 15+
- Redis 7+

### 安装

```bash
# 克隆仓库
git clone <repo-url>
cd review-agent

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入实际配置
```

### 运行（本地开发）

```bash
# 先启动数据库依赖
docker compose up -d postgres redis

# 数据库迁移
uv run alembic upgrade head

# 启动 API 服务（开发模式）
make dev

# 启动 Worker（另一个终端）
uv run arq review_agent.service.queue.WorkerSettings
```

### 运行（Docker Compose 一键启动）

```bash
# 启动全部服务（API + Worker + PostgreSQL + Redis）
docker compose up -d

# 查看服务状态
docker compose ps

# 查看 API 日志
docker compose logs -f api

# 停止
docker compose down
```

### 验证

```bash
make verify
```

---

## 项目结构

```
src/review_agent/
├── types/          # 数据模型与类型定义
│   ├── enums.py    # 枚举常量
│   ├── exceptions.py # 异常层次
│   └── models.py   # Pydantic 数据模型
├── config/         # 配置管理
│   ├── settings.py # Pydantic Settings
│   └── logging.py  # 日志与追踪配置
├── repo/           # 数据访问层（Repository 模式）
│   ├── base.py     # 通用 CRUD 基类
│   └── *.py        # 各实体 Repository
├── service/        # 业务逻辑层
│   ├── git/        # Git 平台适配器
│   ├── ai/         # AI Provider 抽象
│   ├── dimensions/ # 五维度评审引擎
│   ├── chunking.py # 代码分块
│   ├── publisher.py # 结果发布
│   └── queue.py    # 任务队列
├── api/            # API 路由层
│   ├── app.py      # FastAPI 应用组装
│   ├── webhook.py  # Webhook 接收
│   └── *.py        # 各路由模块
└── ui/             # 前端（React）
```

## 技术栈

| 组件 | 选型 |
|------|------|
| 语言 | Python 3.12+ |
| Web 框架 | FastAPI |
| 数据库 | PostgreSQL 15+ + SQLAlchemy 2.0 (async) |
| 缓存/队列 | Redis 7+ + ARQ |
| AI 模型 | DeepSeek (v4-flash / v4-pro) |
| 代码解析 | tree-sitter |
| 追踪 | OpenTelemetry |

---

## 开发指南

```bash
make lint        # 代码检查
make format      # 代码格式化
make typecheck   # 类型检查
make test        # 运行测试
make coverage    # 覆盖率报告
```

详细规范请参见 [代码风格](docs/coding/style.md)。

---

## 路线图

| 阶段 | 内容 | 状态 |
|------|------|------|
| M1 骨架搭建 | 脚手架、核心模型、API、Worker、Docker Compose、CI | ✅ 已完成 |
| M2 AI 流水线 | 多维评审、规范知识库、报告生成 | 📅 待开始 |
| M3 平台扩展 | GitLab/Gitee、完整后台 | 📅 待开始 |
| M4 生产加固 | 熔断降级、全链路追踪、K8s | 📅 待开始 |

详见 [实施路线图](docs/project-design.md#8-实施路线图)。

---

## 文档

- [产品设计文档](docs/project-design.md)
- [架构总览](docs/architecture/overview.md)
- [模块边界定义](docs/architecture/module-boundaries.md)
- [API 规范](docs/api/conventions.md)
- [安全规范](docs/security/guidelines.md)
- [部署运维](docs/deployment/ci-cd.md)

---

## 许可

内部项目。
