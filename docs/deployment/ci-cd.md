# CI/CD 与部署运维

> 文档版本：v1.2 | 更新日期：2026-06-09 | 关联文档：[架构总览](../architecture/overview.md)、[安全规范](../security/guidelines.md)

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

### 1.2 CI 流水线（GitHub Actions）

流水线定义：`.github/workflows/verify.yml`

| 任务 | 命令 | 触发条件 |
|------|------|---------|
| **Lint** | `ruff check src/` + `ruff format src/ --check` | push/PR → main |
| **TypeCheck** | `mypy src/` | push/PR → main |
| **Test** | `pytest` (单元测试 + 集成测试) | push/PR → main |
| **Result** | 汇总结果（lint + typecheck + test 全部通过 ✔） | push/PR → main |

CI 环境服务依赖：
- PostgreSQL 16（`pg_isready` 健康检查）
- Redis 7（`redis-cli ping` 健康检查）

### 1.3 验证门禁

```yaml
# 合并到 main 的硬性条件：
# 1. lint ✅  — ruff check 无错误
# 2. format ✅ — ruff format 格式正确
# 3. typecheck ✅ — mypy 通过
# 4. test ✅ — pytest 全部通过，覆盖率 ≥ 70%
```

---

## 二、环境配置

### 2.1 环境层级

| 环境 | 用途 | 数据库 | 部署方式 |
|------|------|--------|---------|
| dev | 本地开发 | 开发用 PG + Redis | `docker compose up` |
| staging | 预发布验证 | 独立 PG + Redis | Docker Compose / K8s |
| production | 生产 | 主从 PG + 集群 Redis | Kubernetes |

### 2.2 Docker Compose

实际 `compose.yml` 中包含四个服务：

| 服务 | 容器名 | 端口 | 依赖 |
|------|--------|------|------|
| **api** | `review-agent-api` | 8000 | postgres (healthy), redis |
| **worker** | `review-agent-worker` | - | postgres (healthy), redis |
| **postgres** | `review-agent-db` | 5432 | - |
| **redis** | `review-agent-redis` | 6379 | - |

```bash
# 启动全部服务
docker compose up -d

# 仅启动后端依赖（开发时本地运行 API）
docker compose up -d postgres redis

# 查看 API 日志
docker compose logs -f api

# 停止并清理数据卷
docker compose down -v
```

### 2.3 环境变量

```bash
# .env — 参考 .env.example
REVIEW_AGENT_DATABASE_URL=postgresql+asyncpg://review:review@localhost:5432/review_agent
REVIEW_AGENT_REDIS_URL=redis://localhost:6379/0
REVIEW_AGENT_ARQ_REDIS_URL=redis://localhost:6379/1
REVIEW_AGENT_AI_API_KEY=sk-xxx             # DeepSeek 密钥
REVIEW_AGENT_AI_MODEL_NAME=deepseek-v4-flash
REVIEW_AGENT_GITHUB_TOKEN=ghp_xxx           # GitHub API 令牌
REVIEW_AGENT_LOG_LEVEL=INFO

# 可选调优
REVIEW_AGENT_REVIEW_MAX_CONCURRENCY=3       # 文件级并发上限
REVIEW_AGENT_REVIEW_SKIP_EXTENSIONS=.md,.rst,.txt
```

---

## 三、Docker 构建

### 3.1 多阶段构建

```dockerfile
FROM python:3.12-slim AS builder     # 依赖安装阶段
FROM python:3.12-slim AS development   # 开发阶段（含 dev 依赖）
FROM python:3.12-slim AS production    # 生产阶段（最小镜像）
```

```bash
# 构建开发镜像
docker build -t review-agent:dev --target development .

# 构建生产镜像
docker build -t review-agent:latest --target production .

# 运行 API
docker run -p 8000:8000 --env-file .env review-agent:dev

# 运行 Worker
docker run --env-file .env review-agent:dev uv run arq review_agent.service.queue.WorkerSettings
```

### 3.2 健康检查

```yaml
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; c=http.client.HTTPConnection('localhost:8000'); c.request('GET','/healthz'); assert c.getresponse().status==200"
```

---

## 四、可观测性

### 4.1 日志

- 结构化 JSON 日志，每行包含 `trace_id`
- 日志级别：`DEBUG`/`INFO`/`WARNING`/`ERROR`

```json
{"timestamp": "2026-06-08T10:00:00Z", "level": "INFO", "trace_id": "abc123", "event": "review.completed", "duration_ms": 45000}
```

### 4.2 指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `webhook_requests_total` | Counter | Webhook 请求总数 |
| `webhook_signature_failures` | Counter | 签名验证失败数 |
| `queue_depth` | Gauge | 消息队列深度 |
| `task_duration_seconds` | Histogram | 任务处理时长 |
| `llm_call_success_rate` | Gauge | LLM 调用成功率 |
| `comment_publish_total` | Counter | 评论发布总数 |

### 4.3 告警阈值

| 条件 | 通知对象 |
|------|---------|
| 队列积压 > 1000 持续 5 分钟 | 运维 |
| LLM 失败率 > 10% | AI 服务管理员 |
| 某仓库连续 3 次签名验证失败 | 项目管理员 |
| 任务处理时间 P99 > 5 分钟 | 开发团队 |

### 4.4 全链路追踪

```text
Webhook 接收 ─→ 消息队列 ─→ Worker ─→ LLM 调用 ─→ Git API 调用
     │             │            │          │            │
     └─────────────┴────────────┴──────────┴────────────┘
                           OpenTelemetry
```

---

## 五、Kubernetes 部署参考

### 5.1 组件规格

| 组件 | 副本数 | 资源 (requests/limits) |
|------|--------|----------------------|
| Webhook API | 2-4 | 500m/1c, 512Mi/1Gi |
| Worker | 2-8 | 1c/2c, 1Gi/2Gi |
| Redis | 3 (集群) | 1c/2c, 2Gi/4Gi |
| PostgreSQL | 主 + 2 从 | 2c/4c, 4Gi/8Gi |

### 5.2 健康检查

```yaml
readinessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 5
  periodSeconds: 10
livenessProbe:
  httpGet:
    path: /healthz
    port: 8000
  initialDelaySeconds: 15
  periodSeconds: 20
```

---

## 六、成本控制

- 单次评审 Token 上限 15,000（输入 + 输出）
- 每项目可配每日/每月 Token 预算，超额暂停并通知
- 模型分级：安全/Bug 用高质量模型，规范/风格用性价比模型
- 相同 `head_sha` 缓存 7 天
- 仅有 `.md`、文档字符串变更的 PR 可配置跳过
