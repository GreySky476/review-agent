# Database Query Template

使用 ORM 直接操作数据库。

## 连接

```python
from review_agent.config.database import async_session_factory
```

## 示例：查询

```python
import asyncio
from sqlalchemy import select
from review_agent.config.database import async_session_factory
from review_agent.types.orm import ProjectModel

async def main():
    async with async_session_factory() as db:
        result = await db.execute(select(ProjectModel).limit(5))
        for row in result.scalars().all():
            print(row.id, row.name)
    # session 自动关闭

asyncio.run(main())
```

## 示例：修改

```python
import asyncio
from sqlalchemy import select, text
from review_agent.config.database import async_session_factory

async def main():
    async with async_session_factory() as db:
        # 查询
        result = await db.execute(text("SELECT * FROM projects LIMIT 5"))
        for row in result.all():
            print(row)
        # 修改后需要 commit
        await db.commit()

asyncio.run(main())
```

## 注意事项

- 查询不用 commit，修改（INSERT/UPDATE/DELETE）需要 `await db.commit()`
- async with 自动管理 session 生命周期，无需手动 dispose
- 表名和字段名与 ORM 模型定义一致
