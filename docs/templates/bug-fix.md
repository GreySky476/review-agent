# Bug 修复提示词模板

> 用于 `/bug-fix` 流程 | 关联文档：[任务执行协议](../CLAUDE.md#二任务执行协议)

---

## 模板

```markdown
## Bug 描述

{bug_description}

## 复现步骤

1. {step_1}
2. {step_2}
3. {step_3}

## 期望行为

{expected_behavior}

## 实际行为

{actual_behavior}

## 环境信息

- 版本：{version}
- 部署环境：{environment}
- 关联的 trace_id / task_id：{trace_id}

## 排查指引

1. **定位根因**
   - 阅读相关模块文档
   - 检查日志中对应 trace_id 的记录
   - 定位到具体代码位置

2. **修复方案**
   - 最小化修改原则 — 不改动无关代码
   - 添加对应测试覆盖此次修复
   - 验证所有现有测试仍通过

3. **验证标准**
   - 修复后按复现步骤验证 Bug 不再出现
   - 相关功能的现有测试全部通过
   - 新增测试覆盖该 Bug 场景
```

## 输出要求

| 产出物 | 路径 |
|--------|------|
| 根因分析 | 写入修复 commit message 的 body |
| 修复代码 | 对应源文件 |
| 测试用例 | `tests/` 目录对应位置 |
| 更新 current.md | `docs/plans/current.md` |

## Commit 示例

```
fix(service): handle null result from AI provider

When the AI provider returns a null result (timeout or service
unavailable), the orchestrator raised an unhandled TypeError.

Root cause: missing null check after ai_client.analyze() call.

Fix: add null check and return empty findings list with a warning
log message instead of crashing.

Closes #142
```
