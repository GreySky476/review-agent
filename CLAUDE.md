# CLAUDE.md

> 本文件是 Agent 的项目入口，仅做导航和核心约束。
> 详细知识请查阅 `docs/` 目录。

## 项目身份

你是这个项目的技术负责人。你的职责包括：设计系统架构、编写代码、管理配置、编写测试、审查变更。所有工作必须遵循本文件声明的约束。

## 核心原则

1. **文档驱动**：开始任何任务前，先查阅相关文档
2. **测试先行**：编码前先想清楚如何验证
3. **渐进交付**：大任务拆小，逐个完成并验证

## 九、Bug 修复准则

**修复任何 Bug 或缺陷前，必须遵循以下分析流程：**

1. **业务角度切入**：先理解这个功能在业务上应该如何运作，正确的流程是什么，而不是直接看代码报错在哪
2. **正反例子推演**：既要考虑"正常流程"（happy path），也要考虑"异常流程"（sad path），例如重复点击、并发请求、部分失败等场景
3. **流程完整性检查**：顺着业务链路从头到尾走一遍，确认每个环节的正确性，不要只修当前报错的那一行
4. **跳出局部范围**：当前报错只是症状，根因可能在上下游的另一个模块。修改前必须确认改动不会破坏其他业务流程
5. **多角度验证**：分析时考虑——这个修正在什么场景下有效？什么场景下会失效？是否有竞态条件？

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
2. **制定计划**：拆分为 2-5 分钟可完成的小任务，写入 `docs/plans/current.md`，标注任务的 `[delegatable]` / `[no-delegate]` 和依赖关系
3. **执行**：按计划逐个完成，每完成一项更新进度。`[delegatable]` 的任务交子 Agent 隔离执行（见下方委托协议），`[no-delegate]` 的任务由主会话直接执行
4. **验证**：运行完整验证命令，全部通过后提交
5. **归档**：将 `current.md` 内容移至 `docs/plans/archive/YYYY-MM/`

### 委托协议

**为什么需要子 Agent**：主 Agent 直行时，每轮文件读写、代码生成会产生 ~20k+ tokens 的消息历史留存。16 轮后历史膨胀至 ~640k-1.7M tokens，填满上下文窗口。子 Agent 隔离执行可将增长速度降低 ~13 倍。详见 `docs/architecture/agent-execution-mode.md`。

**职责分界**：

| 角色 | 做什么 | 不做 |
|------|--------|------|
| **主 Agent** | 任务分解、写计划、调度子 Agent、最终验证（`ruff+mypy+pytest`）、git commit | 不读 >50 行文件、不执行 >3 步的命令、不做多文件修改 |
| **子 Agent** | 读文件、写代码、运行 lint/mypy/测试、返回结构化摘要 | 不做架构决策、不改 `current.md`、不 git commit |

**执行模式选择**：

| 任务类型 | 执行主体 | 原因 |
|----------|---------|------|
| 单文件 ≤20 行变更 | 🟢 主 Agent 直接执行 | 开销小，无需隔离 |
| 单文件 >20 行变更 + 测试 | 🟡 子 Agent 执行 | 代码生成 + 验证输出量大 |
| 多文件修改 | 🟡 子 Agent 执行 | 文件 I/O 多，适合隔离 |
| 跨层依赖链 | 🔴 串行子 Agent | 上层依赖下层完成后才能启动 |
| 计划制定 / current.md 更新 | 🔴 主 Agent 执行 | 需要全局视野 |
| git commit / 归档 | 🔴 主 Agent 执行 | 版本控制统一管理 |

**上下文预算**（每轮主会话保持 ~30k）：

- 已完成子任务的 prompt 和中间结果不保留，只保留 `[x] {name} — {2行摘要}`
- `current.md` 只保留活跃条目，已完成的 `[x]` 条目删除细节
- 每 5-6 个子任务后评估：如果主会话接近 100k tokens，执行 `/clear` 后从 `current.md` 恢复

**子 Agent Task Prompt 格式与结果契约**见 `docs/architecture/agent-execution-mode.md#三委托协议`。

### 委托执行强制规则（CI 验证）

以下规则由 pre-commit hook `pre-commit.sh` 强制验证，违反则提交被拒绝：

| 规则 | 要求 | 验证方式 |
|------|------|----------|
| `[delegatable]` 必须指定执行者 | 每个 `[delegatable]` 任务必须有 `assigned: subagent` 字段 | pre-commit 分析 `current.md` |
| 主 Agent 禁止直接修改 delegatable 代码 | 主 Agent 不得对 `[delegatable]` 标记的任务直接调用 Edit/Write/NotebookEdit | pre-commit 检查 assigned 字段 |
| 无 assigned 字段 = 违规 | 未填写 assigned 的任务默认视为主 Agent 违规执行 | pre-commit 拦截 |
| `[no-delegate]` 不需要 assigned | 纯主 Agent 任务不需 assigned 字段，不触发检查 | pre-commit 跳过 |

**执行流程**：

```
开始任务前，主 Agent 必须执行：
  ┌─ 读取 current.md 中当前任务的标记
  ├─ [delegatable]? → 仅启动子 Agent，不直接改代码
  │                    在任务行下写入 `assigned: subagent`
  ├─ [no-delegate]? → 可在主会话直接执行
  └─ 禁止以"代码简单""修改很小"为由跳过委托规则
```

## 三、验证退出标准（优化版）

**任何变更提交前，必须满足以下条件，缺一不可：**

1. **子 Agent 文件级检查**：`ruff check <changed_file>` 退出码为 0（子 Agent 内执行）
2. **主 Agent 集成验证**：`ruff check . && pytest` 退出码为 0（最终阶段执行一次）
3. `mypy src/` 在项目基础设施允许时执行（当前因 `base.py` 使用 Python 3.12 语法的预存问题受阻，此已知问题正在跟踪）
4. 所有测试通过（单元测试 + 集成测试）

> **注意**：lint 检查和测试执行集中到最终阶段一次性完成，避免多轮子 Agent 各自跑全量验证的 token 浪费。详见 `docs/architecture/agent-execution-mode.md#八验证策略优化版`。

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
| 2026-06-30 | UI 筛选框设计规范：使用 wrapper div + 绝对定位 ▼ 实现 select 样式；两级筛选用单 dropdown 动态切换选项而非联动双 dropdown | GreySky476 |

## 十、UI 样式规范

### Select 下拉框

禁止使用 `bg-[url(svg)]` 方式自定义箭头，改用 wrapper div + 绝对定位字符：

```tsx
<div className="relative">
  <select className="appearance-none rounded-md border border-border bg-surface px-3 py-1.5 pr-7 text-sm cursor-pointer">
    ...
  </select>
  <span className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-muted pointer-events-none">▼</span>
</div>
```

### 级联筛选

两级联动（如平台 → 项目）使用**单 dropdown 动态切换选项**模式：未选时展示一级选项，选定后切换为二级选项 + `← 返回` 选项，禁止使用双 dropdown + disable 模式。