# 测试策略

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联文档：[架构总览](../architecture/overview.md)、[代码风格](../coding/style.md)

---

## 一、测试原则

1. **新增代码必须有对应测试** — 无测试的 PR 不合并
2. **单元测试覆盖率 ≥ 80%**（核心逻辑模块）
3. **测试不是一次性工作** — 修改代码时必须同步更新测试
4. **测试上下文独立** — 每个测试可单独运行，不依赖执行顺序

---

## 二、测试分层

```text
┌──────────────────────────────────────────┐
│         端到端测试 (E2E)                   │
│    Webhook → 评审 → 评论 全链路验证        │
├──────────────────────────────────────────┤
│          集成测试 (Integration)            │
│    Webhook 接收 / 队列投递 / 数据库读写     │
│     AI 服务调用 / Git 平台 API 调用        │
├──────────────────────────────────────────┤
│         单元测试 (Unit)                    │
│    代码分块 / Finding 聚合 / 评分计算       │
│    规范检索 / 结果去重 / 发布策略决策       │
└──────────────────────────────────────────┘
```

---

## 三、测试工具与配置

| 层 | 工具 | 说明 |
|----|------|------|
| 单元测试 | `pytest` + `pytest-asyncio` | 异步测试支持 |
| 覆盖率 | `pytest-cov` | 阈值 80% |
| Mock | `pytest-mock` | 外部服务调用 Mock |
| 数据库 | `pytest-postgresql` + `testcontainers` | 集成测试用真实 PG |
| HTTP | `httpx.AsyncClient` + `respx` | FastAPI 测试客户端 + Mock |
| 代码质量 | `pytest-xdist` | 并行执行 |

### 基准配置 (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
minversion = "7.0"
addopts = "-ra -q --strict-markers --cov=src --cov-report=term-missing --cov-fail-under=80"
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src"]
omit = ["*/tests/*", "*/migrations/*"]
```

---

## 四、测试分类与要求

### 4.1 单元测试

**覆盖范围：**

| 模块 | 测试重点 |
|------|---------|
| `service/chunking.py` | Token 估算、分块策略、边界值 |
| `service/dimensions/*.py` | 各维度 Finding 结构正确性 |
| `service/publisher.py` | 发布策略决策、聚合去重 |
| `types/*.py` | 数据模型验证、序列化/反序列化 |

**要求：**

```python
# ✅ 标准单元测试结构
async def test_chunk_oversized_function():
    """超大函数应返回结构评审路径。"""
    code = "def " + "x" * 10_000  # 超长函数
    result = await chunk_code(code)
    assert result.path == ChunkPath.STRUCTURAL_REVIEW
```

### 4.2 集成测试

**覆盖范围：**

| 场景 | 描述 |
|------|------|
| Webhook 接收 | 签名验证、事件去重、错误处理 |
| 队列投递 | 消息发布、消费者消费、死信队列 |
| 数据库操作 | Repository CRUD、事务回滚 |
| AI 服务 | Mock 返回结构化 Finding |
| Git 平台 API | GitHub / GitLab / Gitee 适配器 |

**工具：**

```python
# ✅ 集成测试使用 testcontainers
@pytest.mark.integration
async def test_webhook_github_signature():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/webhook/github",
            json=payload,
            headers={"X-Hub-Signature-256": valid_sig},
        )
        assert response.status_code == 200
```

### 4.3 E2E 测试

- 使用 Testcontainers 启动完整环境（PG + Redis + MinIO）
- 验证完整评审流水线：Webhook → 队列 → AI 评审 → 评论
- 定期在 CI 中运行（非每次提交）

---

## 五、Mock 策略

| 外部服务 | Mock 方式 |
|---------|----------|
| LLM API | `respx` 拦截 HTTP 请求，返回结构化 Finding 响应 |
| GitHub API | `respx` 返回预设 diff 和 PR 信息 |
| 数据库 | 集成测试用 testcontainers，单元测试用 `AsyncMock` |
| Redis | `fake-redis` 或 `testcontainers` |

---

## 六、测试目录结构

```
tests/
├── conftest.py                  # 全局 Fixture
├── unit/
│   ├── test_chunking.py
│   ├── test_publisher.py
│   └── dimensions/
│       ├── test_security.py
│       ├── test_bug.py
│       ├── test_performance.py
│       ├── test_style.py
│       └── test_dependency.py
├── integration/
│   ├── test_webhook.py
│   ├── test_queue.py
│   └── test_database.py
└── e2e/
    └── test_full_pipeline.py
```

---

## 七、命令

```bash
make test        # 运行所有测试
make test-unit   # 仅单元测试
make test-int    # 仅集成测试
make test-e2e    # 仅 E2E 测试
make cov         # 测试 + 覆盖率报告
```
