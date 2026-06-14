# 反思：Webhook 状态判定数据源错误

> 事故日期：2026-06-14 | 涉及模块：`api/projects.py`, `service/health.py`  
> 关联文档：[模块边界](../architecture/module-boundaries.md#六状态判定与数据源规则)、[架构总览](../architecture/overview.md#44-webhook-连通性验证)

---

## 症状

用户在前端点击"测试连接"按钮，返回 `{"status": "connected"}` 确认 webhook 正常工作，但同一页面的项目状态仍显示 **"连接超时"**（inactive）。状态信息互相矛盾。

## 时间线

1. **用户反馈**：测试按钮成功，状态未更新
2. **首次修复尝试**（错误）：在测试端点中向 `webhook_events` 表插入一条测试事件
   - 思路：认为状态需要"最新事件时间戳"
   - 问题：治标不治本，测试端点不应该负责维护系统状态
3. **二次修复尝试**（错误）：让心跳巡检也向 `webhook_events` 表写入心跳事件
   - 思路：心跳确认连通后顺便刷新时间戳
   - 问题：污染被动日志表，数据语义不纯
4. **根因发现**：`_format_project()` 用错了数据源
5. **最终修复**：删除 `webhook_last_event_at` 的状态依赖，直接使用 `project.webhook_enabled`

---

## 根因分析

### 数据源混淆

系统中有两条独立链路：

```
心跳巡检 (service/health.py)
  └→ GitHub API → webhook 配置存在 → 更新 project.webhook_enabled  ✅ 权威来源

状态显示 (api/projects.py)
  └→ webhook_events 表 → 最后事件时间 > 24h → status = "inactive"  ❌ 错误来源
```

**核心问题**：`_format_project()` 选择 `webhook_events` 表（被动事件日志）作为状态判定的数据源，完全忽略了 `project.webhook_enabled`（由心跳巡检持续维护的权威字段）。

### 为什么选择 webhook_events 是错的

| 对比维度 | `project.webhook_enabled` | `webhook_events` 表 |
|---------|--------------------------|-------------------|
| 维护方式 | 主动巡检（每 5 分钟查 GitHub API） | 被动记录（有事件才写入） |
| 数据语义 | "Webhook 配置是否存在" | "Webhook 收到过什么事件" |
| 空值含义 | webhook 未启用 | 项目无活动（正常情况） |
| 更新频率 | 每 5 分钟 | 不定（取决于开发活动） |

`webhook_events` 表设计上是一份审计日志：它只记录"发生了什么事"。没有事件不代表系统有问题——可能只是项目无人提交。用事件日志的缺席来推断连接状态，是一个逻辑错误。

---

## 错误做法回顾

### 做法 A：测试端点写 webhook_event

```python
# api/projects.py（已回退）
await WebhookEventRepo(db).create_from_payload(...)
```

**为什么错了**：测试端点（POST `/projects/{id}/webhook/test`）的职责是验证连通性并报告结果，不应该有写数据库的副作用。如果测试端点需要写数据才能让系统正确工作，说明系统的状态判定逻辑本身有缺陷，应该在缺陷处修复，而不是在测试端点打补丁。

### 做法 B：心跳写 webhook_event

```python
# service/health.py（已回退）
session.add(WebhookEventModel(action="heartbeat", ...))
```

**为什么错了**：`webhook_events` 表的设计目的是记录来自外部平台的真实事件（PR opened、push 等）。向其中写入应用层合成的心跳数据，违反了表的单一职责，污染了审计日志。如果开发者在日后排查问题时查看 `webhook_events`，会看到大量的 `action="heartbeat"` 合成事件，干扰真实事件的检索。

---

## 正确做法

`_format_project()` 的状态判定简化为：

```python
webhook_status = "disconnected" if not project.webhook_enabled else "connected"
```

- 心跳巡检（`check_project_webhooks`）每 5 分钟通过 GitHub API 验证 webhook 配置是否存在，据此更新 `project.webhook_enabled`
- `webhook_last_event_at` 仍保留在 API 响应中，但仅作为**展示信息**（显示最近事件时间），不参与状态判定
- `webhook_events` 表回归其本职：记录外部平台事件，供审计和调试使用

### 修复后的状态判定流程

```
用户点击"测试连接"
  └→ test_webhook_connection() → GitHub API → 找到 webhook
      ├→ 设置 project.webhook_enabled = True
      └→ 返回 {status: "connected"}
          用户立即看到"已连接"

心跳巡检（每 5 分钟）
  └→ check_project_webhooks() → GitHub API
      ├→ webhook 仍存在 → project.webhook_enabled = True  → 状态保持 "connected"
      └→ webhook 已删除 → project.webhook_enabled = False → 状态变为 "disconnected"
```

---

## 三条设计原则

| # | 原则 | 一句话 |
|---|------|--------|
| 1 | 单一权威数据源 | 每个状态字段必须由一个确定的权威数据源维护 |
| 2 | 日志表不是状态表 | 被动事件日志不可用于推导系统状态 |
| 3 | 测试端点只验证 | 测试端点不应通过副作用补偿其他代码路径的缺陷 |

详见 [docs/architecture/module-boundaries.md#六状态判定与数据源规则](../architecture/module-boundaries.md#六状态判定与数据源规则)。

---

## 验证场景

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| 测试按钮成功 | 状态仍显示"连接超时" | 立即显示"已连接" |
| 项目 3 天无事件，心跳正常 | 状态超时（误报） | "已连接"（正确） |
| webhook 从 GitHub 删除 | 5 分钟后状态变"未连接" | 5 分钟后状态变"未连接" |
| 新项目未配 webhook | "未连接" | "未连接" |

---

## 变更记录

| 日期 | 变更内容 |
|------|----------|
| 2026-06-14 | 初稿 |
