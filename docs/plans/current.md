# Add dead letter replay API endpoint — 完成

> 创建日期: 2026-06-29 | 完成日期: 2026-06-29

## 完成清单

### [x] T1: Fix `_on_job_failure` to populate project_id and review_id in error log
- **文件**: `src/review_agent/service/queue.py`
- **描述**: 从 ARQ ctx['args'] 中提取 project_id (args[0]) 和 review_id，传递给 `log_error()`。
- **变更**: +13 行

### [x] T2: Add POST /errors/{error_id}/replay endpoint
- **文件**: `src/review_agent/api/errors.py`
- **描述**: 新增 replay 端点：查找 error → 验证 arq_job_failed → 查 Review/Project → 通过 GitHubProvider 重新获取文件 → 调用 enqueue → 标记 recovered=True → 返回 202。
- **变更**: +158 行（文件从 127 行增至 285 行）

### [x] T3: 验证
- **ruff check src/review_agent/api/errors.py src/review_agent/service/queue.py**: ✅ All passed
- **mypy src/review_agent/api/errors.py src/review_agent/service/queue.py**: ✅ No issues
- **pytest**: ✅ 496 passed, 0 failures

## 最终验证

| 检查项 | 结果 |
|--------|------|
| ruff (changed files) | ✅ All passed |
| mypy (changed files) | ✅ No issues |
| pytest | ✅ 496 passed |
