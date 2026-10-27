#!/bin/zsh
set -e
cd "$(dirname "$0")"
if [[ ! -x .venv/bin/python ]]; then
    printf '请先按 README.md 安装到 .venv 环境，再运行此文件。\n'
    exit 1
fi
printf '打开 http://127.0.0.1:8080 使用；按 Control+C 停止服务。\n'
exec .venv/bin/python web.py
