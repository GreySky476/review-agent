#!/bin/bash
# 验证提交前检查：确保变更符合项目规范

echo "🔍 运行 pre-commit 检查..."

# 检查是否在 git 仓库中
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "⚠️  不是 git 仓库，跳过 git 检查"
  exit 0
fi

# 检查是否有硬编码密钥
if git diff --cached -G'(sk-[a-zA-Z0-9]{20,}|api[_-]?key[a-zA-Z0-9_\-]{16,}|secret[a-zA-Z0-9_\-]{16,})' --quiet 2>/dev/null; then
  echo "❌ 发现可能的硬编码密钥！请移除后再提交。"
  exit 1
fi

# 检查 TODO 注释
if ! git diff --cached -G'//\s*TODO' --quiet 2>/dev/null; then
  echo "⚠️  检测到 TODO 注释，确认是否需要保留。"
fi

echo "✅ pre-commit 检查通过"
exit 0
