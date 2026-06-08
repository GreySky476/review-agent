# CI/CD 与部署运维

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联文档：[架构总览](../architecture/overview.md)、[安全规范](../security/guidelines.md)

---

## 一、CI/CD 流程

### 1.1 分支策略

```text
main  ←─── feature/xxx (Squash Merge)
  │             ↑
  │        fix/xxx (Squash Merge)
  │
  └─── hotfix/xxx (Squash Merge，直接合入 main + 向后合并)
```

- `main` 分支保护，禁止直接推送
- CI 必须全部通过 + 至少 1 人 Review 方可合并

### 1.2 CI 流水线（GitHub Actions / GitLab CI）

| 阶段 | 步骤 | 触发条件 |
|------|------|---------|
| Lint | `ruff check .` | 每次提交 |
| TypeCheck | `mypy src/` | 每次提交 |
| Test | `pytest` | 每次提交 |
| 安全扫描 | `bandit -r src/` + `pip-audit` | 每次提交 |
| 覆盖率 | `pytest --cov-fail-under=80` | 每次提交 |
| 构建 | `docker build` | 合并到 `main` |
| E2E | docker-compose 启动完整环境 | 合并到 `main` |

### 1.3 验证门禁

```yaml
# .github/workflows/verify.yml (示例)
name: Verify
on: [push, pull_request]
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[dev]"
      - run: make lint
      - run: make typecheck
      - run: make test
      - run: make security-scan
```

---

## 二、环境配置

### 2.1 环境层级

| 环境 | 用途 | 数据库 | 部署方式 |
|------|------|--------|---------|
| dev | 本地开发 | 开发用 PG + Redis | Docker Compose |
| staging | 预发布验证 | 独立 PG + Redis | Docker Compose / K8s |
| production | 生产 | 主从 PG + 集群 Redis | Kubernetes |

### 2.2 Docker Compose

```yaml
# compose.yml (示例)
services:
  api:
    build: .
    ports: ["8000:8000"]
    depends_on: [postgres, redis]
  worker:
    build: .
    command: celery -A src.queue worker
    depends_on: [redis, postgres]
  postgres:
    image: postgres:15
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7
```

### 2.3 环境变量

```bash
# .env.example — 复制为 .env 并填入实际值
REVIEW_AGENT_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/review_agent
REVIEW_AGENT_REDIS_URL=redis://localhost:6379/0
REVIEW_AGENT_S3_ENDPOINT=http://localhost:9000
REVIEW_AGENT_MODEL_NAME=deepseek-v4-flash
REVIEW_AGENT_LOG_LEVEL=INFO
```

---

## 三、可观测性

### 3.1 日志

- 结构化 JSON 日志，每行包含 `trace_id`
- 日志级别：`DEBUG`/`INFO`/`WARNING`/`ERROR`

```json
{"timestamp": "2026-06-08T10:00:00Z", "level": "INFO", "trace_id": "abc123", "event": "review.completed", "duration_ms": 45000}
```

### 3.2 指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `webhook_requests_total` | Counter | Webhook 请求总数 |
| `webhook_signature_failures` | Counter | 签名验证失败数 |
| `queue_depth` | Gauge | 消息队列深度 |
| `task_duration_seconds` | Histogram | 任务处理时长 |
| `llm_call_success_rate` | Gauge | LLM 调用成功率 |
| `comment_publish_total` | Counter | 评论发布总数 |

### 3.3 告警

| 条件 | 通知对象 |
|------|---------|
| 队列积压 > 1000 持续 5 分钟 | 运维 |
| LLM 失败率 > 10% | AI 服务管理员 |
| 某仓库连续 3 次签名验证失败 | 项目管理员 |
| 任务处理时间 P99 > 5 分钟 | 开发团队 |

### 3.4 全链路追踪

```text
Webhook 接收 ─→ 消息队列 ─→ Worker ─→ LLM 调用 ─→ Git API 调用
     │             │            │          │            │
     └─────────────┴────────────┴──────────┴────────────┘
                           OpenTelemetry
```

---

## 四、Kubernetes 部署参考

### 4.1 组件

| 组件 | 副本数 | 资源 (requests/limits) |
|------|--------|----------------------|
| Webhook API | 2-4 | 500m/1c, 512Mi/1Gi |
| Worker | 2-8 | 1c/2c, 1Gi/2Gi |
| Redis | 3 (集群) | 1c/2c, 2Gi/4Gi |
| PostgreSQL | 主 + 2 从 | 2c/4c, 4Gi/8Gi |

### 4.2 健康检查

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
```

---

## 五、成本控制

- 单次评审 Token 上限 15,000（输入 + 输出）
- 每项目可配每日/每月 Token 预算，超额暂停并通知
- 模型分级：安全/Bug 用高质量模型，规范/风格用性价比模型
- 相同 `head_sha` 缓存 7 天
- 仅有 `.md`、文档字符串变更的 PR 可配置跳过
