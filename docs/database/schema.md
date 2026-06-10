# 数据库表结构

> 版本: 1.0 | 最后更新: 2026-06-10  
> 共有 21 张表，覆盖组织管理、业务核心、监控运维、通知四大域

---

## 一、ER 关系全景

```
组织管理层                         业务核心层                        监控运维层
┌──────────────┐                ┌──────────────┐                ┌──────────────┐
│    users     │                │   projects   │                │ webhook_event│
│  (11 fields) │◄──team_id──┐   │  (13 fields) │                │  (11 fields) │
└──────┬───────┘            │   └──────┬───────┘                └──────────────┘
       │                    │          │                              │
       │ user_sessions      │          ├─ reviews (15 fields)         │
       │ (7 fields)         │          │  ├─ findings (14 fields)     │
       │                    │          │  └─ comments (8 fields)      │
┌──────────────┐            │          │                              │
│    teams     │────────────┘          ├─ pull_requests (9 fields)    │
│  (5 fields)  │                       │                              │
└──────┬───────┘                       ├─ commits (12 fields)         │
       │                              │                              │
       │ team_members                 │                              │
       │ (4 fields)                   ├─ review_errors (7 fields)    │
                                      │                              │
独立表：                              │                              │
┌──────────────┐  ┌──────────────┐    ├─ quality_snapshots (9 flds)  │
│    rules     │  │ audit_logs   │    │                              │
│  (8 fields)  │  │  (7 fields)  │    └──────────────────────────────┘
└──────────────┘  └──────────────┘
┌──────────────────────────────┐
│  notification_rules (7 flds) │
│  notification_logs  (7 flds) │
└──────────────────────────────┘
┌──────────────────────────────┐
│  platform_health (5 fields)  │
└──────────────────────────────┘
```

---

## 二、组织管理层

### 2.1 users — 管理后台用户

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| username | String(128) | UNIQUE, NOT NULL | 登录名 |
| email | String(255) | UNIQUE, NOT NULL | 邮箱 |
| password_hash | String(255) | NOT NULL | bcrypt 哈希 |
| display_name | String(255) | NOT NULL | 显示名 |
| avatar_url | String(1024) | NULL | 头像 URL |
| role | String(32) | NOT NULL | viewer / project_admin / super_admin |
| is_active | Boolean | NOT NULL | 是否启用 |
| last_login_at | DateTime(tz) | NULL | 最后登录时间 |
| team_id | String(36) | FK→teams.id, NULL | 所属团队 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

### 2.2 user_sessions — 登录会话

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| user_id | String(36) | FK→users.id, INDEX | 用户 |
| token_hash | String(255) | NOT NULL | JWT 哈希 |
| ip_address | String(64) | NULL | 登录 IP |
| user_agent | String(512) | NULL | 客户端 UA |
| expires_at | DateTime(tz) | NOT NULL | 过期时间 |
| is_revoked | Boolean | NOT NULL | 是否吊销 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

### 2.3 teams — 团队/组织分组

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| name | String(255) | NOT NULL | 团队名 |
| description | Text | NULL | 描述 |
| created_by | String(36) | FK→users.id, NULL | 创建人 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

### 2.4 team_members — 团队成员关系

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| team_id | String(36) | FK→teams.id, INDEX | 团队 |
| user_id | String(36) | FK→users.id, INDEX | 用户 |
| role | String(32) | NOT NULL | admin / member |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

---

## 三、业务核心层

### 3.1 projects — 代码仓库注册

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| name | String(255) | NOT NULL | 仓库名 |
| platform | String(32) | NOT NULL | github / gitlab / gitee / github_enterprise / gitlab_self_hosted / gitea_self_hosted |
| repo_url | String(1024) | NOT NULL | 仓库 URL |
| description | Text | NULL | 项目描述 |
| default_branch | String(255) | NOT NULL | 默认分支 |
| owner_id | String(36) | FK→users.id, NULL | 项目负责人 |
| webhook_secret | String(255) | NULL | Webhook 签名密钥 |
| webhook_enabled | Boolean | NOT NULL | Webhook 是否启用 |
| is_archived | Boolean | NOT NULL | 是否归档（与删除分离） |
| last_activity_at | DateTime(tz) | NULL | 最后活跃时间 |
| settings | Text | NOT NULL | JSON 配置 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

#### Webhook 状态机

```
webhook_enabled=false → disconnected（未配置）
webhook_enabled=true 且 无事件 → connected（心跳已验证）
webhook_enabled=true 且 24h 无事件 → inactive（超时预警）
webhook_enabled=true 且有近期事件 → connected
```

### 3.2 reviews — AI 评审记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id | 所属项目 |
| pr_number | Integer | NULL | PR 号（commit 评审为 null） |
| pr_title | String(512) | NOT NULL | PR 标题或 commit 描述 |
| head_sha | String(64) | NOT NULL | 评审的 SHA |
| status | String(32) | NOT NULL | pending / running / completed / failed |
| score | Integer | NULL | 评分 0-100 |
| findings_count | Integer | NOT NULL | 发现数 |
| task_id | String(255) | NULL | ARQ 任务 ID |
| report_url | String(1024) | NULL | 报告链接 |
| trigger_type | String(32) | NOT NULL | manual / webhook / scheduled |
| author | String(255) | NULL | 触发人 |
| files_count | Integer | NOT NULL | 涉及文件数 |
| commits_count | Integer | NOT NULL | 涉及 commit 数 |
| branch | String(255) | NULL | 分支名 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

### 3.3 findings — 评审发现的问题

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| review_id | String(36) | FK→reviews.id | 所属评审 |
| file_path | String(1024) | NOT NULL | 文件路径 |
| line_start | Integer | NULL | 起始行 |
| line_end | Integer | NULL | 结束行 |
| category | String(32) | NOT NULL | security / bug / performance / style / dependency / structure |
| severity | String(32) | NOT NULL | critical / warning / info |
| title | String(255) | NOT NULL | 问题标题 |
| description | Text | NOT NULL | 详细描述 |
| suggestion | Text | NOT NULL | 修改建议 |
| rule_id | String(36) | NULL | 触发的规则 ID |
| detected_by | String(32) | NOT NULL | rule / ai / structural |
| is_valid | Boolean | NOT NULL | 是否有效（非误报） |
| is_fixed | Boolean | NOT NULL | 是否已修复 |
| fixed_at | DateTime(tz) | NULL | 修复时间 |
| fixed_by | String(255) | NULL | 修复人 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

### 3.4 comments — 评审讨论

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| review_id | String(36) | FK→reviews.id, INDEX | 所属评审 |
| finding_id | String(36) | FK→findings.id, NULL | 关联 finding |
| author | String(255) | NOT NULL | 评论者 |
| content | Text | NOT NULL | 评论内容 |
| action | String(32) | NULL | accepted / invalid |
| is_resolved | Boolean | NOT NULL | 是否已解决 |
| resolved_at | DateTime(tz) | NULL | 解决时间 |
| resolved_by | String(255) | NULL | 解决人 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

### 3.5 pull_requests — PR/MR 跟踪

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id, INDEX | 所属项目 |
| pr_number | Integer | NOT NULL | PR 号 |
| title | String(512) | NOT NULL | 标题 |
| author | String(255) | NULL | 作者 |
| source_branch | String(255) | NULL | 源分支 |
| target_branch | String(255) | NULL | 目标分支 |
| state | String(32) | NOT NULL | open / merged / closed |
| merge_sha | String(64) | NULL | 合并 SHA |
| is_merged | Boolean | NOT NULL | 是否已合并 |
| merged_at | DateTime(tz) | NULL | 合并时间 |
| platform | String(32) | NOT NULL | 平台 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

**唯一约束：** `(project_id, pr_number)`

### 3.6 commits — 提交记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id, INDEX | 所属项目 |
| sha | String(64) | INDEX | 提交哈希 |
| author | String(255) | NULL | 作者 |
| message | Text | NULL | 提交信息 |
| branch | String(255) | NULL | 分支 |
| pr_number | Integer | NULL | 关联 PR |
| is_reviewed | Boolean | NOT NULL | 是否已评审 |
| additions | Integer | NOT NULL | 新增行数 |
| deletions | Integer | NOT NULL | 删除行数 |
| files_changed | Integer | NOT NULL | 变更文件数 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

**唯一约束：** `(project_id, sha)`

### 3.7 rules — 自定义评审规则

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| name | String(255) | NOT NULL | 规则名 |
| content | Text | NOT NULL | 规则内容 |
| category | String(32) | NOT NULL | 类别 |
| severity | String(32) | NOT NULL | 严重性 |
| languages | Text | NOT NULL | JSON 数组 |
| tags | Text | NOT NULL | JSON 数组 |
| version | Integer | NOT NULL | 版本号 |
| is_active | Boolean | NOT NULL | 是否启用 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

---

## 四、监控运维层

### 4.1 webhook_events — Webhook 入站事件日志

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id | 所属项目 |
| platform | String(32) | NOT NULL | 平台 |
| event_id | String(128) | INDEX | GitHub delivery ID |
| action | String(32) | NOT NULL | opened / synchronize / reopened |
| pr_number | Integer | NOT NULL | PR 号 |
| repo_full_name | String(512) | NOT NULL | org/repo 格式 |
| raw_payload | Text | NOT NULL | 原始事件体 |
| is_processed | Boolean | NOT NULL | 是否已处理 |
| response_status | Integer | NULL | 处理 HTTP 状态 |
| response_time_ms | Integer | NULL | 处理耗时 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

### 4.2 review_errors — 评审流水线错误

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id, NULL | 项目 |
| review_id | String(36) | FK→reviews.id, NULL | 评审 |
| error_type | String(64) | INDEX | ai_call_failed / git_api_failed / parse_failed / timeout |
| error_message | Text | NOT NULL | 错误消息 |
| error_detail | Text | NULL | 详细堆栈 |
| recovered | Boolean | NOT NULL | 是否已恢复 |
| frequency | Integer | NOT NULL | 出现次数 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

### 4.3 quality_snapshots — 质量快照（预聚合）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id, INDEX | 项目 |
| snapshot_date | Date | NOT NULL | 快照日期 |
| period | String(16) | NOT NULL | daily / weekly / monthly |
| avg_score | Float | NOT NULL | 平均分 |
| total_reviews | Integer | NOT NULL | 评审总数 |
| total_findings | Integer | NOT NULL | 发现总数 |
| critical_count | Integer | NOT NULL | Critical 数 |
| warning_count | Integer | NOT NULL | Warning 数 |
| info_count | Integer | NOT NULL | Info 数 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

### 4.4 platform_health — 平台连通性

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| platform | String(32) | UNIQUE, NOT NULL | github / gitlab / gitee |
| status | String(32) | NOT NULL | pending / connected / error |
| latency_ms | Integer | NOT NULL | 响应延迟 |
| error_message | Text | NULL | 错误信息 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

### 4.5 audit_logs — 操作审计日志

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| actor_id | String(36) | FK→users.id, INDEX | 操作人 |
| action | String(64) | INDEX | create / update / delete / trigger_review / login |
| resource_type | String(64) | NOT NULL | project / review / rule / user |
| resource_id | String(36) | NULL | 资源 ID |
| detail | Text | NOT NULL | JSON 详情 |
| ip_address | String(64) | NULL | 操作 IP |
| user_agent | String(512) | NULL | 客户端 UA |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |

---

## 五、通知系统

### 5.1 notification_rules — 通知规则

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| project_id | String(36) | FK→projects.id, NULL | 项目（空=全局规则） |
| user_id | String(36) | FK→users.id | 用户 |
| event_type | String(64) | NOT NULL | review_completed / review_failed / critical_finding / webhook_down |
| channel | String(32) | NOT NULL | email / webhook / slack |
| config | Text | NOT NULL | JSON 渠道配置 |
| is_active | Boolean | NOT NULL | 是否启用 |
| create_time | DateTime(tz) | NOT NULL | |
| update_time | DateTime(tz) | NOT NULL | |
| is_deleted | Boolean | NOT NULL | 软删除 |

### 5.2 notification_logs — 通知发送记录

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | String(36) | PK | UUID |
| rule_id | String(36) | FK→notification_rules.id, NULL | 触发规则 |
| event_type | String(64) | NOT NULL | 事件类型 |
| recipient | String(255) | NOT NULL | 接收方 |
| channel | String(32) | NOT NULL | 渠道 |
| status | String(32) | NOT NULL | pending / sent / failed |
| error_message | Text | NULL | 发送错误 |
| create_time | DateTime(tz) | NOT NULL | |

---

## 六、关键设计决策

### 6.1 软删除 vs 归档

- **`is_deleted`（SoftDeleteMixin）**：用户主动删除，数据逻辑不可见
- **`is_archived`（ProjectModel）**：合规保留，项目不再活跃但数据可查

两者互斥：归档 ≠ 删除，删除 = 不可见。

### 6.2 Webhook 状态计算

```python
if not webhook_enabled:                    # 未配置
    status = "disconnected"
elif webhook_last_event_at is None:         # 心跳已验证
    status = "connected"
elif > 24h 无事件:                          # 长时间无活动
    status = "inactive"
else:
    status = "connected"                    # 正常接收事件
```

### 6.3 唯一约束

| 表 | 约束 | 目的 |
|------|------|------|
| commits(project_id, sha) | UNIQUE | 同项目同次提交不重复 |
| pull_requests(project_id, pr_number) | UNIQUE | 同项目同个 PR 不重复 |

### 6.4 枚举值存储

所有枚举字段（Platform、ReviewStatus、FindingCategory、UserRole 等）均存储为**字符串**，不依赖数据库原生枚举类型。便于迁移和跨数据库兼容。

---

## 七、迁移历史

| 迁移 ID | 说明 | 日期 |
|---------|------|------|
| 89f44ed99960 | 初始表结构 | - |
| 9163769ca971 | 增加 platform_health 表 | - |
| 6590591ee57c | reviews.pr_number 可空 | 2026-06-10 |
| 22bdfcb83974 | 企业级字段完善 + teams + audit_logs | 2026-06-10 |
| 2b5bd5b1ab2c | user_sessions + notification 表 | 2026-06-10 |
| 87a19216a4d2 | finding 追踪 + 归档 + 唯一约束 | 2026-06-10 |
