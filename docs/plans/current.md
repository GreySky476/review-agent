# 当前开发计划

> 最后更新：2026-06-08 | 状态：M1 骨架搭建进行中

---

## M1 — 骨架搭建（当前阶段）

> 目标：GitHub Webhook 自动评论

### 待完成任务

- [ ] 项目脚手架搭建（目录结构、基础配置、Makefile）
- [ ] 核心数据模型定义（Project、Review、Finding）
- [ ] 数据库初始化（SQLAlchemy + Alembic 迁移）
- [ ] Webhook 接收端点（GitHub 签名验证）
- [ ] 消息队列集成（Redis Stream / Celery）
- [ ] 单维 AI 评审（安全维度）
- [ ] 结果发布（PR 行级评论）
- [ ] 基本管理后台（项目管理界面）
- [ ] Makefile 与 CI 配置

### 完成标准

```
✅ GitHub Webhook 接收到 PR 事件后自动运行安全检查
✅ 检查结果以行级评论发布到 PR 中
✅ 管理后台可查看项目列表和评审记录
```

---

## M2 — AI 流水线

> 目标：LangGraph 多维评审 + 规范知识库

- [ ] LangGraph 多维度评审流水线
- [ ] 规范知识库（向量检索 + 版本管理）
- [ ] 代码分块：超大块结构评审
- [ ] 评审报告生成（Markdown + HTML）
- [ ] 结果聚合与发布策略决策

---

## M3 — 平台扩展

> 目标：支持 GitLab、Gitee + 完整后台

- [ ] GitLab 平台适配器
- [ ] Gitee 平台适配器
- [ ] Hook 配置向导前端
- [ ] 成员分析（雷达图）
- [ ] 依赖风险面板

---

## M4 — 生产加固

> 目标：熔断降级 + 全链路追踪 + K8s 部署

- [ ] 熔断降级机制
- [ ] OpenTelemetry 全链路追踪
- [ ] Prometheus 指标 + Grafana 面板
- [ ] 私有模型部署（vLLM）
- [ ] Kubernetes Helm Chart

---

## 当前 Sprint 任务

| 任务 | 负责人 | 状态 | 预期完成 |
|------|--------|------|---------|
| 脚手架搭建 | - | ⏳ 待开始 | - |
| 数据模型 | - | ⏳ 待开始 | - |
| Webhook 端点 | - | ⏳ 待开始 | - |

---

## 参考资料

- [项目设计文档](../project-design.md)
- [架构总览](../architecture/overview.md)
- [模块边界定义](../architecture/module-boundaries.md)
