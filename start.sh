#!/usr/bin/env bash
# PaperMate 一键启动（macOS / Linux）
# 用法：双击，或在终端执行  bash start.sh
set -u

cd "$(dirname "$0")" || exit 1

echo "============================================================"
echo "  PaperMate 启动"
echo "============================================================"

# ---------- 1. 找 Python 3.10+ ----------
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
      PY="$c"
      break
    fi
  fi
done

if [ -z "$PY" ]; then
  echo "[缺] 没有找到 Python 3.10 或更高版本。"
  echo ""
  echo "  macOS：brew install python@3.12    （或到 python.org 下载安装包）"
  echo "  Ubuntu/Debian：sudo apt install python3 python3-venv python3-pip"
  echo ""
  # 说明「找到了但版本太低」，避免用户以为自己没装
  if command -v python3 >/dev/null 2>&1; then
    echo "  当前 python3 版本：$(python3 -V 2>&1)"
    echo "  （系统自带的 3.9 及以下跑不了，需要另装新版）"
  fi
  exit 1
fi

echo "==> 使用 $PY（$("$PY" -V 2>&1)）"

# ---------- 2. 环境自检 + 缺依赖自动安装 ----------
if ! "$PY" env_check.py --install; then
  echo ""
  echo "上面的 [缺] 项还没解决，先把它们补上再启动。"
  echo "提示：依赖装不上多半是网络，试试"
  echo "  $PY -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple"
  exit 1
fi

# ---------- 3. 启动（浏览器会自动打开） ----------
echo ""
echo "启动中；停止服务按 Ctrl+C。"
echo ""
exec "$PY" server.py
