# 主代理/子代理委派执行协议

> 文档版本：1.0 | 2026-06-23
> 关联文档：[CLAUDE.md（任务执行协议）](../../CLAUDE.md#二任务执行协议)、[模块边界](module-boundaries.md)

---

## 一、问题

主 Agent 直行时，每轮文件读写、命令执行、代码生成会产生 ~20k+ tokens 的消息历史留存。16 轮迭代后，消息历史膨胀至 ~640k-1.7M tokens，填满 1M 上下文窗口后必须 `/clear` 重建。

**解决**：将高 token 消耗的操作（文件读写、命令执行）交由子 Agent 隔离执行。子 Agent 只向主会话返回结构化摘要（~1k tokens），内部上下文执行完即释放。

---

## 二、职责划分

### 2.1 主 Agent（留在主会话）

| 职责 | 说明 | 预算 |
|------|------|------|
| **任务分解** | 将需求拆成可委派的子任务，写明依赖关系 | ~1k |
| **上下文准备** | 收集关键文档片段、接口签名、架构约束（不读全文） | ~3k |
| **委派调度** | 构建子 Agent prompt，调用 Agent 工具，管理执行顺序 | ~2k |
| **结果汇聚** | 读子 Agent 摘要，判断通过/失败，决定下一步 | ~2k |
| **集成验证** | 所有子任务完成后，运行 `ruff check . && mypy src/ && pytest` | 命令输出 |
| **归档提交** | git add/commit、归档 current.md | ~1k |

**主 Agent 不做**：
- 不读超过 50 行的文件内容（只 `wc -l` 和 grep 接口签名）
- 不执行涉及 >3 步操作的 Bash 命令
- 不做多文件修改

### 2.2 子 Agent（隔离执行，用完释放）

| 职责 | 说明 | 预算 |
|------|------|------|
| 读源文件 | 完整读取需要修改的文件 | ~3k-30k |
| 搜索上下文 | 搜索引用、测试、文档 | ~3k-10k |
| 生成代码 | 编写实际修改 | ~3k-15k |
| 执行 lint/mypy | 增量验证 | ~1k-5k |
| 返回结构化摘要 | 按固定格式报告结果（见下方） | ~1k-2k |
| **总计** | | **~11k-62k，全部释放** |

**子 Agent 不做**：
- 不做架构决策（涉及哪个模块、什么拆分策略）
- 不跨子任务协调
- 不改 `docs/plans/current.md`
- 不执行 `git commit`

---

## 三、委托协议

### 3.1 子 Agent Task Prompt 标准格式

```markdown
## TASK: {task_id}/{task_name}

### Context（来自主 Agent）
**目标**：{一句话}

**涉及文件**：
- `{模块/文件.py}` — {作用说明}
- `tests/{test_文件.py}` — {测试说明}

**依赖**：{P1 / none}

**约束**：
- 单文件 ≤ 300 行 — {文件名} 当前 {N} 行
- 依赖方向：{类型层级}

**文档片段**：
```
{关键片段，≤ 30 行}
```

**接口签名**：
```python
{签名，≤ 15 行}
```

### Acceptance Criteria
1. [ ] {具体条件 1}
2. [ ] `ruff check .` — all passed
3. [ ] `mypy src/` — 不新增预存外错误
4. [ ] `pytest` — 关联测试通过

### Output Contract
返回两条分隔区：

---SUBAGENT_RESULT---
status: passed|failed|partial
changed_files:
  - {path}: {一句话摘要（≤1行）}
  - {path}: {一句话摘要}
verification:
  ruff: {N errors / passed}（仅扫描改动的文件：`ruff check <file1> <file2>`）
changes_summary: |
  {3-5 行说明}
next_steps: {建议 / none}
---SUBAGENT_DETAIL---
{失败原因 / 关键决策说明，≤10 行}
```

> **注意**：子 Agent 不做 `mypy` 和 `pytest`。全量验证由主 Agent 在集成阶段执行一次。详见 §8 验证策略。

### 3.2 主 Agent 调用方式

```markdown
启动子代理执行任务 {task_id}，任务描述见当前 context。
```

主 Agent 在委派前需准备（不读全文）：

1. `wc -l {target_file}` → 检查 300 行限制
2. `grep -n "def\|async def\|class " {target_file}` → 提取接口签名
3. 从 `docs/` 中摘取关键设计语句

---

## 四、结果契约

### 4.1 子 Agent **必须**返回

- `status`: passed / failed / partial
- `changed_files`: 清单
- `test_results`: 三项退出码 + 错误数
- `new_test_count`: 新增测试数量
- `changes_summary`: 3-5 行
- `next_steps`: 下一步建议

### 4.2 子 Agent **严禁**返回

- 完整文件内容（"以下是我修改后的完整文件 xxx.py："）
- 超过 20 行的 diff 原文
- 超过 10 行的测试输出日志
- 中间推理过程

---

## 五、上下文预算

### 5.1 主会话预算分配

| 类别 | 预算/轮 |
|------|---------|
| 固定开销（System + Tools + Skills） | ~19.7k |
| CLAUDE.md 约束引用 | ~2k |
| 子任务委派 prompt | ~5k |
| 子结果摘要（每个子任务保留最终版） | ~1k |
| current.md 进度 | ~2k |
| **合计** | **~30k** |

### 5.2 规则

1. **只留最终版**：子任务重试多次只保留最后一次结果摘要
2. **完成即压缩**：任务完成后，主会话只保留 `[x] {name} — {2行摘要}`
3. **current.md 只保留活跃条目**：已完成的 `[x]` 条目可删除细节，只留标题
4. **每 5-6 个子任务后评估**：如果主会话接近 100k+ tokens，执行 `/clear` 后从 `current.md` 恢复

---

## 六、并行执行规则

| 场景 | 可并行？ | 示例 |
|------|---------|------|
| 同层不同文件 | ✅ | `repo/commit.py` + `repo/project.py` |
| 同文件不同子任务 | ❌ 串行 | 两个子任务都改 `api/prs.py` |
| 下层已完成 → 跨层 | ✅ | `repo/` 完成后 `repo/` + `service/` 并行 |
| 独立层级 | ✅ | `api/dashboard.py` + `ui/dashboard.tsx` |
| 测试 + 实现 | ✅ | 测试文件 + 被测试文件 |

**依赖链强制串行**：
```
types/ → config/ → repo/ → service/ → api/ → ui/
```

---

## 七、错误恢复

```
子 Agent status: failed
       │
       ▼
主 Agent 判断类型：
       │
  ┌────┼─────────┐
  ▼    ▼         ▼
lint  测试      其他（依赖缺失）
失败  失败
  │    │         │
  ▼    ▼         ▼
修复  检查是否   提交 Issue
重试  pre-existing  help-needed
  │    │
  │    └── 全是 pre-existing → 标记通过
  │
  └── 连续 2 次 → 降低粒度重新拆分
```

---

	## 八、验证策略（优化版）

	### 8.1 原则

	验证分两层，各有明确边界，避免不必要的全量扫描：

	| 层级 | 执行者 | 范围 | 命令 |
	|------|--------|------|------|
	| **文件级验证** | 子 Agent | 仅本次修改的文件 | `ruff check <file1> <file2>` |
	| **集成验证** | 主 Agent | 全项目 | `ruff check . && pytest` |

	### 8.2 文件级验证（子 Agent 执行）

	子 Agent 修改完代码后，只验证自己改的文件：

	1. `ruff check <file1> <file2>` — 检查修改文件的 lint（不跑全项目）
	2. `python -c "import ast; ast.parse(open('file.py').read())"` — 快速语法检查（可选）
	3. **不做** `mypy src/`（全项目扫描慢，预存错误阻碍后续检查）
	4. **不做** `pytest`（全量测试由主 Agent 在最终阶段执行）

	### 8.3 集成验证（主 Agent 执行）

	所有子任务完成后，主会话执行一次：

	1. `ruff check .` — 全项目 lint
	2. `pytest` — 全量测试

	`mypy src/` 仅在项目基础兼容时执行（当前因 `base.py` 的 Python 3.12 语法被预存阻塞）。

	### 8.4 节约估算

	对比优化前后，一次 3 子任务的 Phase 的 token 消耗：

	| 环节 | 优化前 | 优化后 | 节约 |
	|------|--------|--------|------|
	| 子 Agent × 3 | `ruff check .` + `mypy` + `pytest`（每个~20000 tokens输出） | `ruff check <file>`（~500 tokens） | ~58k |
	| 主 Agent 终验 | — | `ruff check .` + `pytest`（一次） | — |
	| **合计** | ~60k (子 Agent) + 10k (主) | ~1.5k (子Agent) + 10k (主) | **~58k (83%)** |

---

## 九、Plan 格式规范

每一项包含可委派标记、执行者分配和依赖信息。

**`[delegatable]` 任务必须指定 `assigned: subagent`，缺失此字段 pre-commit 会拦截提交。**

```markdown
### 第 N 阶段：{阶段名} [no-delegate]

- [ ] P1. `{路径}` — {动作}  [delegatable]
  - dependency: none
  - assigned: subagent    ← 必须填写（pre-commit 强制验证）
  - parallelizable-with: P2
```

| 标记 | 含义 | 执行者 |
|------|------|--------|
| `[delegatable]` | 可委派给子 Agent | **必须** assigned: subagent |
| `[no-delegate]` | 必须在主会话执行 | 主 Agent，不需要 assigned 字段 |
| `assigned: main` | 主 Agent 直接执行 | 仅能与 `[no-delegate]` 搭配 |
| `assigned: subagent` | 子 Agent 隔离执行 | 必须与 `[delegatable]` 搭配 |
| `dependency: {ID}` | 阻塞依赖 | 调度参考 |
| `parallelizable-with: {ID}` | 可与指定任务并行 | 调度参考 |

**强制规则**（由 `.claude/hooks/pre-commit.sh` 强制执行）：

| 场景 | 是否允许 | 原因 |
|------|----------|------|
| `[delegatable]` + **无** `assigned` 字段 | ❌ 提交被拦截 | 默认违规，防误判 |
| `[delegatable]` + `assigned: subagent` | ✅ 通过 | 正确委派 |
| `[delegatable]` + `assigned: main` | ❌ 提交被拦截 | 主 Agent 不应处理委派任务 |
| `[no-delegate]` + 无 `assigned` 字段 | ✅ 通过 | 主 Agent 任务无需分配 |
| `[no-delegate]` + `assigned: main` | ✅ 通过 | 显式声明也可接受 |

`[delegatable]` 的典型场景：单文件修改 + 测试、纯测试新增、跨层但独立的文件。

`[no-delegate]` 的典型场景：计划制定、current.md 更新、git commit、架构决策、跨层接口契约验证。

---

## 十、使用建议

1. **前 3 个子任务手写 prompt**：熟悉格式后可以复用自己的 prompt 片段
2. **简单任务直接执行**：单文件简单修改（≤20 行变更）无需使用子 Agent，直接主会话修改
3. **复杂任务拆分原则**：每个子任务应该能在 2-5 分钟内完成；如果预估超过 10 分钟，说明粒度太粗
