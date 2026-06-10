#!/bin/bash
# 启动悬浮单词便签。先确保已建 .venv 并 pip install -r requirements.txt、跑过 build_data.py。
cd "$(dirname "$0")" || exit 1
PY=".venv/bin/python"
[ -x "$PY" ] || PY="python3"
pkill -f "widget.py" 2>/dev/null
sleep 1
nohup "$PY" widget.py > widget.log 2>&1 &
disown
echo "✅ 已启动（右键便签可暂停/标记会了/退出）"
