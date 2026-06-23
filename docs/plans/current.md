# Plan: Phase 2 正确性修复

> 状态：进行中 | 2026-06-23

---

### T1. `service/queue.py` — `_run_with_langgraph` 状态硬编码  [delegatable] ✅
  - dependency: none
  - assigned: subagent  ✅ done
  - 结果：替换硬编码 `COMPLETED` 为动态判定（unreviewed_files/error_messages → COMPLETED_WITH_ERRORS）

### T2. `api/webhook_helpers.py` — `ensure_project_connected` 副作用  [delegatable] ✅
  - dependency: T1
  - assigned: subagent  ✅ done
  - 结果：移除 `ensure_project_connected()` 中的写操作，提取到新的 `mark_webhook_connected()`

### T3. `webhook_helpers.py + repo/review.py` — SHA 去重不完整  [delegatable] ✅
  - dependency: T2
  - assigned: subagent  ✅ done
  - 结果：新增 `ReviewRepo.get_by_sha()`，`trigger_pr_review()` 拦截 PENDING/RUNNING/COMPLETED

### T4. `api/projects.py` — `_format_project` 状态推导  [delegatable] ✅
  - dependency: none
  - assigned: subagent  ✅ done
  - 结果：`webhook_status` 简化为 `"disconnected" if not project.webhook_enabled else "connected"`

### T5. `service/error_logger.py` — error_logger 可靠性  [delegatable] ✅
  - dependency: none
  - assigned: subagent  ✅ done
  - 结果：增加 deque(maxlen=100) 内存缓冲 + asyncio.Lock 保护，DB 写入失败时暂存

### V1. 集成验证 [no-delegate]
  - dependency: T1, T2, T3, T4, T5
  - 全量验证：`ruff check . && mypy src/ && pytest`
  - dependency: T1, T2, T3, T4, T5
  - `ruff check . && mypy src/ && pytest`

### V2. 提交 [no-delegate]
  - dependency: V1
  - git commit + 归档
