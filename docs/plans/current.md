# 当前开发计划

> 最后更新：2026-06-09 | 状态：**功能迭代中（M2）**

---

## 总体规划

```
P0-P4 — M1 基础骨架 ✅
  └→ M2 — 核心功能迭代（进行中）
```

---

## M2 — 功能迭代

### F1 — GitHub Push Webhook 自动评审

| 步骤 | 内容 | 状态 |
|------|------|------|
| 1.1 | GitProvider 新增 commit 级别方法（get_commit_diff, publish_commit_summary） | ✅ |
| 1.2 | GitHubProvider 实现 commit diff 获取 + 评论发布 | ✅ |
| 1.3 | CommitReviewService 编排服务（规则 + AI + 结构评审分流） | ✅ |
| 1.4 | ARQ commit review worker + 入队函数 | ✅ |
| 1.5 | Webhook push 事件处理分支 | ✅ |
| 1.6 | 单元测试（14 tests） | ✅ |
| 1.7 | 环境配置（GitHub Token + DeepSeek API Key） | ✅ |
| 1.8 | 文件级并发评审（asyncio.gather + semaphore 控制） | ✅ |

**下一步计划**：
- PR 事件 review 的完整实现（目前 `run_review` 仍是 stub）
- 行级 inline comment 发布（目前仅发布摘要 comment）

---

## 参考资料

- [项目设计文档](../project-design.md)
- [架构总览](../architecture/overview.md)
- [模块边界定义](../architecture/module-boundaries.md)
- [Push Review 功能设计](../features/push-review/design.md)
