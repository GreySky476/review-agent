# API 设计规范

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联文档：[架构总览](../architecture/overview.md)、[安全规范](../security/guidelines.md)

---

## 一、通用规范

### 1.1 风格

- RESTful 风格
- URL 使用小写字母和连字符（`-`）
- 请求/响应格式：JSON
- 时间字段格式：ISO 8601

### 1.2 错误格式

所有错误响应使用统一格式：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "PR number is required",
    "details": [
      {
        "field": "pr_number",
        "message": "must be a positive integer"
      }
    ]
  }
}
```

### 1.3 分页

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `page` | int | 1 | 页码，从 1 开始 |
| `page_size` | int | 20 | 每页数量，最大 100 |

响应格式：

```json
{
  "items": [],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

## 二、认证与鉴权

| 端点 | 认证方式 |
|------|---------|
| Webhook | 签名验证（各平台独立机制） |
| 管理后台 API | JWT / API Key |
| 报告访问 | 临时 Token（有效期 7 天） |

认证失败统一返回 `401 Unauthorized`，鉴权失败返回 `403 Forbidden`。

---

## 三、Webhook 接口

### 3.1 GitHub

- 签名验证：`X-Hub-Signature-256`（HMAC-SHA256）
- 事件头：`X-GitHub-Event: pull_request`
- 支持动作：`opened`、`synchronize`、`reopened`

### 3.2 GitLab

- Token 验证：`X-Gitlab-Token`
- 事件头：`X-Gitlab-Event: Merge Request Hook`
- 支持动作：`open`、`update`、`reopen`

### 3.3 Gitee

- Token 验证：`X-Gitee-Token`
- 事件体 `action` 字段
- 支持动作：`open`、`update`、`reopen`

---

## 四、REST API 端点

### 4.1 评审管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/projects/{project_id}/reviews` | 手动触发评审 |
| GET | `/api/v1/projects/{project_id}/reviews/{task_id}` | 查询评审状态 |
| GET | `/api/v1/projects/{project_id}/reviews` | 评审列表（分页） |
| GET | `/api/v1/reviews/{task_id}/report` | 获取评审报告 |

### 4.2 项目管理

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/projects` | 注册项目 |
| GET | `/api/v1/projects` | 项目列表 |
| GET | `/api/v1/projects/{project_id}` | 项目详情 |
| PATCH | `/api/v1/projects/{project_id}` | 更新项目配置 |
| DELETE | `/api/v1/projects/{project_id}` | 删除项目（软删除） |

### 4.3 规范管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/rules` | 规范列表 |
| POST | `/api/v1/rules` | 创建规范 |
| GET | `/api/v1/rules/{rule_id}` | 规范详情 |
| PUT | `/api/v1/rules/{rule_id}` | 更新规范（新建版本） |
| GET | `/api/v1/rules/{rule_id}/versions` | 规范版本历史 |

---

## 五、请求/响应示例

### 手动触发评审

```http
POST /api/v1/projects/pj-abc123/reviews
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "pr_number": 42
}
```

成功响应：

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "task_id": "rev-9f8e7d6c-5b4a-3c2d-1e0f-a9b8c7d6e5f4",
  "status": "pending",
  "result_url": null
}
```

### 查询评审状态

```http
GET /api/v1/projects/pj-abc123/reviews/rev-9f8e7d6c-5b4a-3c2d-1e0f-a9b8c7d6e5f4
Authorization: Bearer <jwt_token>
```

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "task_id": "rev-9f8e7d6c-5b4a-3c2d-1e0f-a9b8c7d6e5f4",
  "status": "completed",
  "score": 78,
  "findings_count": 12,
  "result_url": "https://api.example.com/v1/reports/rep-xxx?token=<temp_token>"
}
```

---

## 六、HTTP 状态码使用规范

| 状态码 | 场景 |
|--------|------|
| 200 | 请求成功（GET、PATCH） |
| 201 | 创建成功（POST） |
| 202 | 任务已接受（异步操作） |
| 400 | 请求参数错误 |
| 401 | 未认证 |
| 403 | 无权限 |
| 404 | 资源不存在 |
| 409 | 冲突（如重复注册） |
| 422 | 请求体校验失败 |
| 429 | 请求频率超限 |
| 500 | 服务器内部错误 |
| 502 | 上游服务不可用 |
| 503 | 服务暂不可用（降级状态） |

---

## 七、幂等性与重试

- Webhook 事件以事件 ID 为幂等键，60 秒内去重
- 评审任务以 PR `head_sha` 为幂等键，7 天内返回缓存结果
- 客户端重试建议使用指数退避（1s → 2s → 4s → 8s）

---

## 八、限流

- Webhook 接收层：每仓库 100 次/分钟
- 管理后台 API：每用户 1000 次/分钟
- Git 平台 API 调用：不超过官方频率上限的 70%
