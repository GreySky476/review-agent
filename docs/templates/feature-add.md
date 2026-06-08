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
3. **实现**：按 `types → config → repo → service → api → ui` 顺序实现
4. **测试**：每个模块实现后立即编写测试
5. **验证**：运行 `make verify`
6. **归档**：将 `current.md` 移至 `docs/plans/archive/YYYY-MM/`

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
