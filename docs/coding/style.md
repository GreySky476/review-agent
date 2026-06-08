# 代码风格规范

> 文档版本：v1.0 | 更新日期：2026-06-08 | 关联文档：[模块边界](../architecture/module-boundaries.md)、[API 规范](../api/conventions.md)

---

## 一、通用原则

- 所有代码如同**写给同事阅读**：清晰 > 巧妙
- 遵循各语言的社区标准风格
- 自动化格式化优先，人工审查只关注语义

---

## 二、后端 Python 规范

### 2.1 格式化与检查

| 工具 | 用途 | 配置 |
|------|------|------|
| `black` | 格式化 | 行宽 100 |
| `ruff` | lint | 启用所有推荐规则 |
| `mypy` | 类型检查 | `--strict` 模式 |

### 2.2 类型注解

**所有公共函数/方法必须包含：**

```python
from collections.abc import Sequence

def calculate_complexity(node: ast.AST, max_depth: int = 10) -> float:
    """计算 AST 节点的圈复杂度。

    Args:
        node: AST 根节点。
        max_depth: 递归最大深度，超过则停止计算。

    Returns:
        计算得出的圈复杂度值。

    Raises:
        ValueError: 当 max_depth 小于 1 时抛出。
    """
    ...
```

### 2.3 文档字符串 (docstring)

- 使用 Google 风格
- 公共函数必须有 `Args`、`Returns`、`Raises`（如有异常）
- 内部函数/私有方法可使用单行注释

### 2.4 命名约定

| 类型 | 约定 | 示例 |
|------|------|------|
| 模块/文件名 | snake_case | `review_orchestrator.py` |
| 类名 | PascalCase | `ReviewOrchestrator` |
| 函数/方法 | snake_case | `run_review()` |
| 变量 | snake_case | `review_result` |
| 私有属性/方法 | `_` 前缀 | `_internal_state` |
| 常量 | UPPER_SNAKE_CASE | `MAX_TOKEN_LIMIT` |

### 2.5 异常处理

- **禁止裸 `except`**：必须指定异常类型
- 定义自定义异常层次（继承自 `ReviewAgentError`）
- 所有外部调用（HTTP、DB、AI）捕获并转换为领域异常

```python
class ReviewAgentError(Exception):
    """项目基础异常。"""

class ConfigError(ReviewAgentError):
    """配置加载错误。"""

class AIProviderError(ReviewAgentError):
    """AI 服务调用错误。"""
```

### 2.6 异步与同步分离

- Web 处理（FastAPI handler）使用 `async/await`
- AI 模型调用在后台线程池或任务队列执行
- CPU 密集型任务（AST 分析）使用 `asyncio.to_thread` 或 `ProcessPoolExecutor`

### 2.7 配置管理

- 使用 Pydantic Settings 加载配置
- 配置项必须在环境变量 / `.env` 文件中声明
- 所有配置有默认值或验证规则

```python
from pydantic_settings import BaseSettings

class AppSettings(BaseSettings):
    model_config = {"env_prefix": "REVIEW_AGENT_"}

    database_url: str
    redis_url: str
    max_token_limit: int = 15_000
```

### 2.8 依赖注入

关键组件通过构造函数注入，不直接在函数内实例化依赖：

```python
# ✅ 正确
class ReviewService:
    def __init__(self, db: AsyncSession, ai_client: AIProvider):
        self._db = db
        self._ai = ai_client

# ❌ 错误
class ReviewService:
    def __init__(self):
        self._db = AsyncSession()  # 硬编码依赖
```

---

## 三、前端 React 规范

### 3.1 组件设计

- **容器组件与展示组件分离**
- 单一职责：每个组件只做一件事
- 页面组件放在 `pages/`，通用组件放在 `components/`

### 3.2 命名

| 类型 | 约定 | 示例 |
|------|------|------|
| 组件 | PascalCase | `ReviewCard` |
| Hook | `use` 前缀 | `useReviewData` |
| 事件处理 | `handle` 前缀 | `handleSubmit` |
| Props 接口 | 组件名 + `Props` | `ReviewCardProps` |

### 3.3 状态管理

| 状态类型 | 工具 |
|---------|------|
| 服务端状态（API 数据） | TanStack Query |
| 客户端临时状态 | Zustand |
| prop drilling 深度 ≤ 3 | 直接传 props |
| prop drilling 深度 > 3 | 用 Context 或 Zustand |

### 3.4 样式

- 优先 Tailwind utility class
- shadcn/ui 组件保持默认 variant
- 不随意覆写 shadcn/ui 核心样式

### 3.5 可访问性

- 所有交互元素必须有 ARIA 标签
- 满足 WCAG AA 对比度标准
- 表单输入有对应的 `<label>`

### 3.6 性能

- 长列表使用虚拟化（react-window / @tanstack/virtual）
- 图片懒加载
- 路由级 Code Split（`React.lazy` + `Suspense`）

---

## 四、Git 工作流

| 规范 | 要求 |
|------|------|
| 主分支 | `main` 保护，禁止直接推送 |
| 分支命名 | `feature/xxx`、`fix/xxx`、`chore/xxx` |
| Commit 格式 | [Conventional Commits](https://www.conventionalcommits.org/) |
| 合并条件 | CI 通过 + 至少 1 人 Review |

### Commit 示例

```
feat(engine): add chunking strategy for oversized functions

Implement code chunking that splits functions >2000 tokens into
structural review path while normal blocks get detailed review.

Closes #42
```

---

## 五、文档要求

- `README.md` 说明项目定位、快速开始、架构图链接
- `docs/` 目录存放架构设计、接口文档、部署手册
- 重要设计决策添加 ADR 记录（放入 `docs/adr/`）
