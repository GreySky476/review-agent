# 模块边界定义

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联文档：[架构总览](overview.md)、[API 规范](../api/conventions.md)

---

## 一、模块分层与依赖规则

```text
types/ ──→ config/ ──→ repo/ ──→ service/ ──→ api/ ──→ ui/
  │           │           │           │           │
  ▼           ▼           ▼           ▼           ▼
 纯数据类型  配置加载   数据访问    业务逻辑    HTTP 路由
```

### 核心规则

1. **依赖方向不可逆**：上层模块可以依赖下层，下层绝对不能依赖上层
2. **同层可调用**：同层模块之间可以通过接口互相调用
3. **依赖注入**：关键组件通过构造函数注入，便于测试替换

---

## 二、各层职责

### 2.1 types/ — 数据模型层

- 定义 Pydantic BaseModel / dataclass
- 定义枚举常量
- 定义类型别名
- **禁止**：导入任何业务模块

### 2.2 config/ — 配置层

- 定义 Pydantic Settings 模型
- 加载环境变量并验证
- **禁止**：运行时可变状态

### 2.3 repo/ — 数据访问层

- SQLAlchemy async repository 模式
- CRUD 操作封装
- 查询构建
- **禁止**：业务逻辑判断

### 2.4 service/ — 业务逻辑层

- 评审流水线编排
- 结果聚合与发布策略
- 调用外部 API（Git 平台、AI 模型）
- **禁止**：直接暴露 HTTP 端点

### 2.5 api/ — API 路由层

- FastAPI router 定义
- 请求/响应序列化
- 认证与权限校验
- **禁止**：业务逻辑实现

### 2.6 ui/ — 前端展示层

- React 组件
- 状态管理（TanStack Query / Zustand）
- **禁止**：直接访问数据库

---

## 三、模块目录约定

```
src/
├── types/                     # 数据模型
│   ├── __init__.py
│   ├── review.py              # 评审相关模型
│   └── project.py             # 项目相关模型
├── config/
│   ├── __init__.py
│   └── settings.py            # Pydantic Settings
├── repo/
│   ├── __init__.py
│   ├── project.py             # 项目 CRUD
│   ├── review.py              # 评审记录 CRUD
│   └── finding.py             # Finding CRUD
├── service/
│   ├── __init__.py
│   ├── review_orchestrator.py # 评审编排
│   ├── chunking.py            # 代码分块
│   ├── dimensions/            # 各维度评审
│   │   ├── __init__.py
│   │   ├── security.py
│   │   ├── bug.py
│   │   ├── performance.py
│   │   ├── style.py
│   │   └── dependency.py
│   └── publisher.py           # 结果发布
├── api/
│   ├── __init__.py
│   ├── webhook.py             # Webhook 接收
│   ├── reviews.py             # 评审 API
│   └── admin.py               # 管理后台 API
└── ui/                        # 前端代码（另行管理）
    ├── src/
    ├── package.json
    └── vite.config.ts
```

---

## 四、模块间通信规范

| 通信方向 | 方式 | 示例 |
|---------|------|------|
| Webhook → Queue | 消息队列 | Redis Stream / RabbitMQ |
| Queue → Worker | 消费者组 | Celery task / ARQ |
| Worker → AI | gRPC / HTTP | LangChain call |
| Worker → Git | HTTP | GitHub API / GitLab API |
| API → DB | ORM | SQLAlchemy async |
| API → Cache | SDK | Redis async client |

---

## 五、边界违规处理

CI 中通过 `import-lint` 工具验证依赖方向：

```bash
# 验证 types/ 不依赖 config/
grep -r "from src\.config" src/types/ && exit 1

# 验证 api/ 不直接操作 repo/
grep -r "from src\.repo" src/api/ && exit 1
```

违反依赖方向规则的提交**不予合并**。
