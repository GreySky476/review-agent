#!/bin/bash
# 检查修改的 Python 文件是否超过 300 行限制
# 在文件读取后调用

MAX_LINES=300
FILE="$1"

if [ -z "$FILE" ]; then
  exit 0
fi

# 只检查 .py 文件
if [[ "$FILE" != *.py ]]; then
  exit 0
fi

if [ ! -f "$FILE" ]; then
  exit 0
fi

LINES=$(wc -l < "$FILE")
if [ "$LINES" -gt "$MAX_LINES" ]; then
  echo "⚠️  $FILE: ${LINES} 行（超出 ${MAX_LINES} 行限制）"
  echo "   请考虑拆分此文件"
fi

exit 0
