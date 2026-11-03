#!/bin/bash
cd "$(dirname "$0")" || exit 1
export PYTHONUTF8=1
if ! command -v python3 >/dev/null 2>&1; then
  echo "请先安装 Python 3.11 或更新版本：https://www.python.org/downloads/"
  read -r -p "按回车退出"
  exit 1
fi
python3 -c 'import sys; assert sys.version_info >= (3,11), "需要 Python 3.11 或更新版本"' || exit 1
python3 tide.py web
read -r -p "潮汐已停止。按回车关闭窗口。"
