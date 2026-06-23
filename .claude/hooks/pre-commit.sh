#!/bin/bash
# 验证提交前检查：确保变更符合项目规范
# 包含：硬编码密钥检查、TODO 检测、委托协议违规检查

echo "🔍 运行 pre-commit 检查..."

# 检查是否在 git 仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "⚠️  不是 git 仓库，跳过 git 检查"
  exit 0
fi

# ── 检查 1：硬编码密钥 ──
if git diff --cached -G'(sk-[a-zA-Z0-9]{20,}|api[_-]?key[a-zA-Z0-9_\-]{16,}|secret[a-zA-Z0-9_\-]{16,})' --quiet 2>/dev/null; then
  echo "❌ 发现可能的硬编码密钥！请移除后再提交。"
  exit 1
fi

# ── 检查 2：TODO 注释（仅警告不阻拦） ──
if ! git diff --cached -G'//\s*TODO' --quiet 2>/dev/null; then
  echo "⚠️  检测到 TODO 注释，确认是否需要保留。"
fi

# ── 检查 3：委托协议违规检查（[delegatable] 任务不得由主 Agent 执行） ──
PLAN_FILE="docs/plans/current.md"
if [ -f "$PLAN_FILE" ]; then
  # 读取 current.md 中所有标记为 [delegatable] 的任务
  # 格式示例：
  #   - [ ] T1. `path` — description [delegatable]
  #     - assigned: subagent
  #   - [x] T2. `path` — description [delegatable]  <- 已完成
  #     - assigned: main  <- 违规

  VIOLATIONS=$(awk '
    BEGIN { in_delegatable = 0; task_line = ""; assigned = ""; }
    /^\s*- \[[\sx]\]/ {
      # 上一个 delegatable 任务检查：必须 assigned: subagent
      if (in_delegatable && assigned != "subagent") {
        printf "  - %s (assigned: %s)\n", task_line, assigned ? assigned : "MISSING";
      }
      # 重置状态
      in_delegatable = 0; assigned = ""; task_line = "";
      if (/\[delegatable\]/) {
        in_delegatable = 1;
        task_line = $0;
        assigned = "";  # 默认无 assigned → 违规
      }
      next;
    }
    in_delegatable && /assigned:/ { assigned = $NF; }
    END {
      if (in_delegatable && assigned != "subagent") {
        printf "  - %s (assigned: %s)\n", task_line, assigned ? assigned : "MISSING";
      }
    }
  ' "$PLAN_FILE")

  if [ -n "$VIOLATIONS" ]; then
    echo ""
    echo "❌ 委托协议违规：以下 [delegatable] 任务由主 Agent 直接执行"
    echo "   规则：标记 [delegatable] 的任务必须通过子 Agent 隔离执行"
    echo "   修正：在 current.md 中修改 assigned 为 subagent，或改标记为 [no-delegate]"
    echo ""
    echo "$VIOLATIONS"
    echo ""
    echo "如需绕过此检查，在 current.md 中设置 assigned: subagent 后重试"
    exit 1
  fi
fi

echo "✅ pre-commit 检查通过"
exit 0
