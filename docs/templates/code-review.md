# 代码评审提示词模板

> 用于 `/review-code` skill | 关联文档：[评审流水线](../project-design.md#42-ai-评审流水线)

---

## 模板

```markdown
## 评审目标

对以下代码变更进行 AI 评审，输出结构化 Findings。

## 变更信息

- 文件：{file_path}
- 变更类型：{added/deleted/modified}
- 变更行数：{lines_changed}

## Diff 内容

```diff
{diff_content}
```

## 评审维度

### 1. 安全漏洞
- SQL/命令注入
- XSS
- 权限绕过
- 敏感信息泄露
- 不安全反序列化

### 2. Bug 风险
- 空指针 / Null 引用
- 逻辑错误
- 资源未释放
- 竞态条件
- 类型误用

### 3. 性能与边界
- N+1 查询
- 无限循环 / 递归
- 异常未处理
- 资源泄漏

### 4. 代码规范
- 命名规范
- 函数长度 / 圈复杂度
- SOLID 原则
- 知识库规则（如已配置）

### 5. 依赖安全
- 已知 CVE
- 不推荐版本
- 许可证冲突

## 输出格式

每个 Finding 使用以下结构化格式：

| 位置 | 类别 | 严重性 | 描述 | 建议 |
|------|------|--------|------|------|
| file.py:42 | security | critical | 使用 eval 执行用户输入 | 替换为 ast.literal_eval |
| file.py:88 | performance | warning | 循环内重复查询数据库 | 使用 select_related 预加载 |

## 评分规则

- 总分 = 100 - Σ(严重性扣分)
  - critical: -15 分
  - warning: -8 分
  - info: -3 分
- 总分低于 60 分：必须生成详细报告
```

## 输出示例

```markdown
## 评审结果

**总分：72** — ❌ 存在关键问题，请修改后重新提交

### Findings

| 位置 | 类别 | 严重性 | 描述 | 建议 |
|------|------|--------|------|------|
| `app.py:42` | security | critical | `eval(request.data)` 执行不受信任的用户输入 | 替换为 `ast.literal_eval()` |
| `models.py:15` | bug | warning | `get_object_or_none` 返回 None 后未检查 | 添加 None 检查或使用 `get_object_or_404` |
| `views.py:88` | perf | warning | 循环内 `User.objects.filter(id=uid)` 导致 N+1 查询 | 使用 `select_related('user')` 预加载 |

### Summary

- **critical**: 1 — 必须修复
- **warning**: 2 — 建议修复
- **info**: 0
```
