# 常见错误排查手册

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联文档：[CI/CD](../deployment/ci-cd.md)、[安全规范](../security/guidelines.md)

---

## 一、Webhook 相关

### 1.1 Webhook 返回 403

**可能原因：**

| 原因 | 检查方式 | 修复 |
|------|---------|------|
| Webhook Secret 不匹配 | 对比平台配置与数据库中的 Secret | 重置 Secret 并更新平台配置 |
| IP 白名单限制 | 检查平台是否发送了正确的源 IP | 添加平台 IP 到白名单 |
| 签名算法不一致 | 检查请求头中的签名算法 | 确认使用正确的 HMAC 算法 |

### 1.2 Webhook 返回 200 但未触发评审

**排查步骤：**

1. 检查事件类型是否为支持的动作（opened / synchronize / reopened）
2. 确认 60 秒内未收到相同事件 ID（去重机制）
3. 检查消息队列是否正常运行
4. 查看 Worker 日志确认任务是否被消费

### 1.3 签名验证失败

```bash
# 本地测试签名验证
echo -n "payload" | openssl dgst -sha256 -hmac "your_secret"
# 对比请求头 X-Hub-Signature-256 的值
```

---

## 二、评审执行异常

### 2.1 LLM 调用超时

| 排查项 | 操作 |
|--------|------|
| 模型服务状态 | `curl <model_endpoint>/health` |
| 网络延迟 | `ping <model_host>` |
| Token 超限 | 检查输入是否超过模型上下文窗口 |
| 熔断状态 | 查看 Redis 中 `circuit_breaker:*` 键 |

### 2.2 Worker 不停重启

```bash
# 查看 Worker 日志
docker logs <worker_container> --tail 100

# 检查资源限制
docker stats <worker_container>

# 常见原因：
# - OOM Kill: 增加内存限制
# - 数据库连接池耗尽: 检查 DB_CONNECTION_POOL_SIZE
# - Redis 连接失败: 检查 REDIS_URL 配置
```

### 2.3 评审结果不完整

| 原因 | 解决方案 |
|------|---------|
| Diff 拉取失败 | 检查 Git 平台 Token 权限 |
| 部分维度超时 | 查看 LLM 调用记录，增大超时时间 |
| 超大块安全检查失败 | tree-sitter 解析错误，确认代码语言支持 |

---

## 三、数据库问题

### 3.1 连接池耗尽

```sql
-- 查看当前连接数
SELECT count(*) FROM pg_stat_activity WHERE datname = 'review_agent';

-- 查看最大连接数
SHOW max_connections;
```

**修复：**

- 调整 `SQLALCHEMY_POOL_SIZE` 和 `SQLALCHEMY_MAX_OVERFLOW`
- 检查是否有连接泄漏（长时间未归还的连接）
- 考虑使用 PgBouncer 连接池

### 3.2 慢查询

```sql
-- 查找慢查询
SELECT query, calls, total_time / calls AS avg_time_ms
FROM pg_stat_statements
ORDER BY avg_time_ms DESC
LIMIT 10;
```

---

## 四、队列与任务

### 4.1 队列积压

```bash
# Redis 队列长度
redis-cli LLEN review_queue

# RabbitMQ 队列状态
rabbitmqctl list_queues name messages
```

**处理：**

1. 临时增加 Worker 副本数：`kubectl scale deployment worker --replicas=5`
2. 检查是否有死信队列堆积
3. 确认下游服务（LLM、Git API）是否正常

### 4.2 任务卡住（一直 running）

```python
# 检查 Redis 中任务状态
redis-cli HGETALL task:rev-xxxx

# 超时强制标记为失败
# （系统自动超时时间为 30 分钟）
```

---

## 五、管理后台问题

### 5.1 仪表盘数据不更新

| 排查项 | 操作 |
|--------|------|
| 缓存过期 | 清理 Redis 缓存：`redis-cli FLUSHDB`（谨慎） |
| 统计刷新频率 | 统计数据每小时刷新，等待下次刷新 |
| 数据库写入 | 确认评审结果已写入数据库 |

### 5.2 用户无法登录

- 检查 OIDC/SAML 配置
- 确认用户状态未被禁用
- 查看审计日志中的登录失败记录

---

## 六、启动与部署

### 6.1 Docker Compose 启动失败

```bash
# 查看各服务状态
docker-compose ps

# 查看所有日志
docker-compose logs

# 重建镜像
docker-compose build --no-cache
```

### 6.2 迁移失败

```bash
# 查看迁移状态
alembic current

# 回滚一步
alembic downgrade -1

# 查看迁移历史
alembic history
```

---

## 七、排查信息收集

当需要提 Issue / 求助时，请收集以下信息：

1. **事件标识**：`trace_id`、`task_id`、`project_id`
2. **时间范围**：问题发生的起止时间
3. **日志片段**：相关日志的 JSON 行（脱敏后）
4. **环境信息**：部署环境（dev / staging / prod）、版本号
5. **复现步骤**：触发问题的操作序列
