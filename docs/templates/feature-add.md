# 功能添加提示词模板

> 用于 `/add-feature` skill | 关联文档：[模块边界](../architecture/module-boundaries.md)、[任务执行协议](../CLAUDE.md#二任务执行协议)

---

## 模板

```markdown
## 功能描述

{feature_description}

## 涉及模块

根据功能描述识别涉及哪些模块：

- [ ] types/ — 数据模型变更
- [ ] config/ — 配置项变更
- [ ] repo/ — 数据访问层变更
- [ ] service/ — 业务逻辑层变更
- [ ] api/ — API 路由变更
- [ ] ui/ — 前端界面变更

## 约束检查

- [ ] 依赖方向：`types → config → repo → service → api → ui`
- [ ] 单文件不超过 300 行
- [ ] 新增代码有对应测试
- [ ] 无硬编码密钥、console.log、TODO

## 执行步骤

1. **理解任务**：阅读相关文档，理解模块边界
2. **制定计划**：拆分为 2-5 分钟小任务，写入 `docs/plans/current.md`
   - 每个任务标注 `[delegatable]` 或 `[no-delegate]`
   - 标注 `dependency`（阻塞依赖）和 `parallelizable-with`（可并行）
3. **委派调度**：`[delegatable]` 的任务交子 Agent 隔离执行
   - 同层不同文件 → 可并行启动子 Agent
   - 下层完成后跨层 → 可与当前层并行
   - 依赖链强制串行：`types → config → repo → service → api → ui`
   - 每完成一个子任务，将摘要更新到 current.md
4. **实现**：按 `types → config → repo → service → api → ui` 顺序实现，`[no-delegate]` 的任务主会话直接执行
5. **测试**：每个模块实现后立即编写测试（可与实现并行执行）
6. **集成验证**：运行 `ruff check . && mypy src/ && pytest`
7. **归档**：将 `current.md` 移至 `docs/plans/archive/YYYY-MM/`

### 委派标记说明

| 标记 | 含义 | 执行者 |
|------|------|--------|
| `[delegatable]` | 文件读写+代码生成，可交子 Agent | 子 Agent |
| `[no-delegate]` | 架构决策/计划更新/版本控制 | 主 Agent |
| `dependency: P1` | 阻塞依赖，P1 完成后才启动 | 调度参考 |
| `parallelizable-with: P2` | 可与 P2 同时启动 | 调度参考 |

委派协议完整文档见 `docs/architecture/agent-execution-mode.md`。

## 代码生成规范

### 数据模型 (types/)

```python
from pydantic import BaseModel

class MyModel(BaseModel):
    """模型描述。"""
    id: str
    name: str
```

### 配置 (config/)

```python
from pydantic_settings import BaseSettings

class MyConfig(BaseSettings):
    """配置描述。"""
    model_config = {"env_prefix": "REVIEW_AGENT_"}
    my_setting: str = "default"
```

### 数据访问 (repo/)

```python
from sqlalchemy.ext.asyncio import AsyncSession

class MyRepo:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def get(self, id: str) -> MyModel | None:
        ...
```

### 业务逻辑 (service/)

```python
class MyService:
    def __init__(self, repo: MyRepo, config: MyConfig):
        self._repo = repo
        self._config = config

    async def execute(self) -> Result:
        ...
```

### API 路由 (api/)

```python
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/my")

@router.get("/")
async def list_items():
    ...
```

## 完成清单

- [ ] 所有代码实现完成
- [ ] 单元测试通过（覆盖率 ≥ 80%）
- [ ] 集成测试通过
- [ ] Lint 无错误
- [ ] 类型检查通过
- [ ] 功能文档已补充（docs/features/{feature-name}/design.md）
- [ ] plan 已归档
```
