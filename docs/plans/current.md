# Plan: AI 评审规范文档 + 输出排序优化

> 状态：已完成 | 2026-06-10

---

## Context

当前系统使用通用 prompt 调用 AI 进行代码评审，没有注入语言特定的编码规范，AI 判定标准过于自由。评审结果按类别分组，需要改为按重要性排列。

## 完成工作

### 语言特定代码规范文档
- 创建 6 个语言规范文档：`docs/coding/language-standards/python.md`（具体规范）+ `generic.md`（兜底）
- 规范按重要性分节：资源管理 > 并发安全 > 正确性 > 安全 > 性能 > 代码规范
- 新建 `src/review_agent/service/standards.py` — 扩展名→语言映射、`detect_language()`、`load_standards()`（带缓存和 fallback）

### AI Prompt 注入
- `commit_review.py` — `_ai_review_chunk()` 中注入 `load_standards(chunk.file_path)` 到 system prompt
- `review_graph/evaluation.py` — 拆分 `_AI_REVIEW_SYSTEM_PROMPT` 为 `_AI_REVIEW_BASE_PROMPT`，在 `_ai_review()` 中动态拼接语言规范

### 输出排序优化
- `publisher.py` — `generate_summary()` 改为按严重性降序（CRITICAL > WARNING > INFO）+ 类别优先级（BUG > SECURITY > PERFORMANCE > STRUCTURE > STYLE > DEPENDENCY）排序
- 输出格式从按类别分组的列表改为 Markdown 表格（| 严重性 | 类别 | 位置 | 问题 | 建议 |）

### 测试
- `tests/unit/test_standards.py` — 15 个测试覆盖语言检测、规范加载、缓存、fallback
- `tests/unit/test_publisher.py` — 新增 `test_summary_sorted_by_severity` 验证排序

## 验证结果

```text
ruff check .    → 通过（仅预存 issue）
mypy src/       → 通过（预存 Python 3.12 语法标记，非本次改动）
pytest          → 223 passed ✓
```

## 修改文件清单

| 文件 | 操作 |
|------|------|
| `docs/coding/language-standards/python.md` | NEW |
| `docs/coding/language-standards/generic.md` | NEW |
| `src/review_agent/service/standards.py` | NEW |
| `src/review_agent/service/commit_review.py` | MODIFY |
| `src/review_agent/service/review_graph/evaluation.py` | MODIFY |
| `src/review_agent/service/publisher.py` | MODIFY |
| `tests/unit/test_standards.py` | NEW |
| `tests/unit/test_publisher.py` | MODIFY |
| `docs/plans/current.md` | MODIFY |

## 后续规划

1. 增加更多语言规范文档（JavaScript/TypeScript、Go、Rust、Java）
2. 规则检查维度 `dimensions/base.py` 增加跨语言模式识别
3. 考虑支持用户自定义规范注入（企业级规则）
