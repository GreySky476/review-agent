#!/bin/bash
# 在所有命令执行前运行
# 用途：检查是否在正确的目录中，加载环境变量等

# 确保我们在项目根目录
PROJECT_ROOT="/Users/qiliangshi/Downloads/program/project/python/review-agent"
if [ "$PWD" != "$PROJECT_ROOT" ]; then
  echo "⚠️  当前目录: $PWD"
  echo "   项目目录: $PROJECT_ROOT"
fi
