#!/bin/bash
cd "$(dirname "$0")" || exit 1
python3 scripts/install_hermes.py
read -r -p "按回车关闭窗口"
