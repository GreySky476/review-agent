---
name: schema-change-migration-rule
description: 数据模型变更后必须立即执行迁移
metadata:
  type: feedback
---

**规则**：修改 ORM 模型（新增/修改字段、表等）后，必须立即执行 `uv run alembic upgrade head` 应用迁移，确保数据库模式与代码一致。

**Why**：多次出现代码已修改但迁移未执行，导致 API 请求时报 `UndefinedColumnError`（列不存在）。

**How to apply**：
1. 修改 `types/orm.py` 后
2. 生成迁移：`uv run alembic revision --autogenerate -m "描述"`
3. **立即执行**：`uv run alembic upgrade head`
4. 验证：请求受影响的 API 端点，确认无列不存在错误

**相关项目**：[[review-agent]]
