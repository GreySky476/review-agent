# 当前开发计划

> 最后更新：2026-06-08 | 状态：**全部基础阶段已完成（M1）**

---

## 总体规划

```
P0 — 公共基础设施（"地基"）      ✅
  └→ P1 — 数据层（"骨架"）       ✅
      └→ P2 — 核心业务逻辑（"大脑"） ✅
          └→ P3 — API 与集成（"接口"） ✅
              └→ P4 — 部署与 CI（"环境"） ✅
```

> 🎉 **M1 基础骨架搭建完毕**。项目已具备完整开发、构建、部署链。
> 后续进入 M2-M4 功能迭代阶段。

---

## P0 — 公共基础设施

| 步骤 | 内容 | 状态 |
|------|------|------|
| 0.1 | 初始化 Git + pyproject.toml 完整依赖 | ✅ |
| 0.2 | 搭建 `src/review_agent/` 包结构 | ✅ |
| 0.3 | 定义错误类型层次 | ✅ |
| 0.4 | 定义枚举常量（Platform, Severity, Status 等） | ✅ |
| 0.5 | 配置管理（Pydantic Settings） | ✅ |
| 0.6 | 日志与追踪配置（OpenTelemetry） | ✅ |
| 0.7 | Makefile（封装 ruff/mypy/pytest/alembic/docker） | ✅ |
| 0.8 | `.env.example` + README.md | ✅ |

---

## P1 — 数据层

| 步骤 | 内容 | 状态 |
|------|------|------|
| 1.1 | Pydantic 数据模型（Project, Review, Finding, Rule, User） | ✅ |
| 1.2 | SQLAlchemy ORM 模型 + 基类（UUID + 时间戳） | ✅ |
| 1.3 | Alembic 初始化 + 初始迁移 | ✅ |
| 1.4 | Repository 基类（通用 CRUD + 软删除） | ✅ |
| 1.5 | ProjectRepo、ReviewRepo、FindingRepo、RuleRepo、UserRepo | ✅ |

---

## P2 — 核心业务逻辑

| 步骤 | 内容 | 状态 |
|------|------|------|
| 2.1 | AI Provider 抽象 + DeepSeek 实现 | ✅ |
| 2.2 | Git 平台抽象 + GitHub 适配器 | ✅ |
| 2.3 | 代码分块服务 | ✅ |
| 2.4 | 五维度评审引擎 | ✅ |
| 2.5 | 超大块结构评审 | ✅ |
| 2.6 | 结果聚合 + 发布策略 | ✅ |
| 2.7 | 规范知识库服务 | ✅ |

---

## P3 — API 与集成

| 步骤 | 内容 | 状态 |
|------|------|------|
| 3.1 | FastAPI 应用组装 + 异常处理 + 中间件 | ✅ |
| 3.2 | Webhook 接收端点（GitHub/GitLab/Gitee） | ✅ |
| 3.3 | 评审 REST API + 项目管理 REST API | ✅ |
| 3.4 | ARQ 任务队列集成 + Worker 进程 | ✅ |

---

## P4 — 部署与 CI

| 步骤 | 内容 | 状态 |
|------|------|------|
| 4.1 | Dockerfile（多阶段构建：development/production） | ✅ |
| 4.2 | Docker Compose（api + worker + postgres + redis） | ✅ |
| 4.3 | CI 配置（GitHub Actions：lint/typecheck/test/result） | ✅ |
| 4.4 | `.dockerignore` | ✅ |
| 4.5 | 文档更新（README + CI/CD 文档） | ✅ |

---

## 参考资料

- [项目设计文档](../project-design.md)
- [架构总览](../architecture/overview.md)
- [模块边界定义](../architecture/module-boundaries.md)
- [实施规划](../../.claude/plans/quirky-rolling-riddle.md)
