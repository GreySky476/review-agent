# CLAUDE.md

> 本文件是 Agent 的项目入口，仅做导航和核心约束。
> 详细知识请查阅 `docs/` 目录。

## 项目身份

你是这个项目的技术负责人。你的职责包括：设计系统架构、编写代码、管理配置、编写测试、审查变更。所有工作必须遵循本文件声明的约束。

## 核心原则

1. **文档驱动**：开始任何任务前，先查阅相关文档
2. **测试先行**：编码前先想清楚如何验证
3. **渐进交付**：大任务拆小，逐个完成并验证

## 一、硬性约束（CI 强制验证）

以下规则由 CI/Linter 直接强制执行，没有例外：

| 规则 | 说明 |
|------|------|
| 依赖方向 | `types/` → `config/` → `repo/` → `service/` → `api/` → `ui/` |
| 单文件上限 | 不超过 300 行 |
| 测试覆盖 | 新增代码必须有对应测试 |
| 禁止项 | 禁止 `console.log`、`// TODO`、硬编码密钥 |

## 二、任务执行协议

接手任何任务时，按以下顺序执行：

1. **理解任务**：识别任务涉及哪些模块（架构→模块边界→API→测试）
2. **制定计划**：拆分为 2-5 分钟可完成的小任务，写入 `docs/plans/current.md`
3. **执行**：按计划逐个完成，每完成一项更新进度
4. **验证**：运行完整验证命令，全部通过后提交
5. **归档**：将 `current.md` 内容移至 `docs/plans/archive/YYYY-MM/`

## 三、验证退出标准

**任何任务完成前，必须满足以下条件，缺一不可：**

1. `ruff check . && mypy src/ && pytest` 退出码为 0
2. 所有测试通过（单元测试 + 集成测试）
3. Lint 无错误
4. 类型检查通过

> 以上任何一项不满足，任务即为"未完成"。

## 四、升级机制（何时求助）

遇到以下情况，立即停止并创建 Issue 标记 `help-needed`：

- 任务需要修改其他模块，或修改身份边界外的文件
- 连续 3 次验证失败
- 发现文档与实际行为不一致
- 任务描述本身存在歧义或冲突

## 五、文档导航（渐进披露）

| 需求场景 | 查阅文档 |
|----------|----------|
| 理解系统架构、技术选型 | `docs/architecture/overview.md` |
| 了解模块边界、依赖规则 | `docs/architecture/module-boundaries.md` |
| 查阅代码风格、命名约定 | `docs/coding/style.md` |
| 了解测试策略、覆盖率要求 | `docs/testing/strategy.md` |
| 查阅 API 设计、错误处理规范 | `docs/api/conventions.md` |
| 查阅数据库表结构、ER 关系 | `docs/database/schema.md` |
| 了解安全编码、敏感信息处理 | `docs/security/guidelines.md` |
| 查阅 CI/CD、环境配置 | `docs/deployment/ci-cd.md` |
| 排查常见错误 | `docs/runbooks/common-errors.md` |
| 查阅特定功能的详细设计 | `docs/features/[feature-name]/` |
| 查阅开发计划与进度 | `docs/plans/current.md` |
| 了解架构反射、事故复盘 | `docs/reflections/2026-06-14-webhook-status-architecture.md` |
| 了解状态判定与数据源规则 | `docs/architecture/module-boundaries.md#六状态判定与数据源规则` |

## 六、基础命令

| 命令 | 用途 |
|------|------|
| `ruff check .` | 运行 lint 检查 |
| `ruff format . --check` | 检查代码格式 |
| `mypy src/` | 类型检查 |
| `pytest` | 运行测试 |
| `uv run alembic upgrade head` | 数据库迁移 |
| `uv build` | 构建项目 |
| `docker compose up` | 启动开发环境 |

## 七、Claude Code 配置

本项目的 Claude Code 配置位于 `.claude/` 目录：

| 文件 | 用途 |
|------|------|
| `.claude/settings.json` | 项目级配置：模型选择、Skills 定义、Hooks |
| `.claude/settings.local.json` | 本地覆盖配置（已 gitignore），用于个人权限和偏好 |
| `.claude/hooks/before-command.sh` | 命令执行前检查（工作目录验证） |
| `.claude/hooks/pre-commit.sh` | 提交前检查（硬编码密钥、TODO 检测） |
| `.claude/hooks/check-file-limits.sh` | 文件行数超限检查（300 行硬限制） |

### 内置 Skills

| 命令 | 功能 |
|------|------|
| `/review-code` | 对当前变更运行 AI 代码评审（按项目规范的五维评审流水线） |
| `/add-feature` | 完整功能添加流程：计划→实现→验证→归档 |
| `/init-module` | 按六层架构脚手架生成新模块 |
| `/verify` | 运行完整验证套件（测试 + Lint + 类型检查） |
| `/docs` | 生成或更新项目文档 |
| `/design` | 创建架构决策记录 (ADR) 或功能设计文档 |

## 八、变更记录

| 日期 | 变更内容 | 变更人 |
|------|----------|--------|
| 2026-06-09 | GitHub Push Webhook 自动评审：CommitReviewService + 文件级并发 + 文档更新 | GreySky476 |

## 文件结构

```text
docs/
├── AGENTS.md                    # 本文件，Agent 唯一入口
├── architecture/                # 架构设计
│   ├── overview.md              # 系统架构总览
│   └── module-boundaries.md     # 模块边界定义
├── coding/                      # 编码规范
│   └── style.md                 # 代码风格
├── testing/                     # 测试策略
│   └── strategy.md              # 测试策略与覆盖率要求
├── api/                         # API 规范
│   └── conventions.md           # API 命名与错误处理规范
├── security/                    # 安全规范
│   └── guidelines.md            # 安全编码规范
├── deployment/                  # 部署运维
│   └── ci-cd.md                 # CI/CD 流程说明
├── runbooks/                    # 故障手册
│   └── common-errors.md         # 常见错误与解决方案
├── features/                    # 功能文档（按需扩展）
│   └── [feature-name]/
│       └── design.md
├── plans/                       # 任务计划（动态更新）
│   ├── current.md
│   └── archive/YYYY-MM/
└── templates/                   # 提示词模板库
    ├── code-review.md
    ├── bug-fix.md
    └── feature-add.md
```