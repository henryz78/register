#!/bin/bash
# 初始化入口:自动装依赖 → 下载浏览器 → 生成 .env
# 用法:
#   bash start.sh              # 首次初始化；已有 .env 时保留
#   bash start.sh --init       # 重新初始化 .env
#   bash start.sh --reconfig   # 兼容旧命令，等同 --init
set -e
cd "$(dirname "$0")"

force_init=0
if [ "${1:-}" = "--init" ] || [ "${1:-}" = "--reconfig" ]; then
    force_init=1
    shift
fi

if [ $# -gt 0 ]; then
    echo "start.sh 只负责初始化。运行注册服务请使用: bash run.sh $*"
    exit 2
fi

echo "=== grok-free-register 初始化 ==="

# 1) 依赖:没有 venv 就自动安装
if [ ! -d .venv ]; then
    echo "[1/3] 首次运行，安装依赖和浏览器..."
    bash setup.sh
else
    echo "[1/3] Python 环境已存在，跳过依赖安装。"
fi

# 2) 浏览器:已有 venv 时也检查 CloakBrowser Chromium
echo "[2/3] 检查 CloakBrowser Chromium..."
if ! .venv/bin/python -m cloakbrowser info >/dev/null 2>&1; then
    echo "[*] 未找到 CloakBrowser Chromium，开始下载..."
    .venv/bin/python -m cloakbrowser install
fi

# 3) 配置:.env 缺失或显式 --init 时进入初始化
echo "[3/3] 初始化 .env 配置..."
if [ ! -f .env ] || [ "$force_init" = "1" ]; then
    if [ "$force_init" = "1" ]; then
        .venv/bin/python init_env.py --force
    else
        .venv/bin/python init_env.py
    fi
else
    echo "[*] 已存在 .env，保留当前配置。需要重置请执行: bash start.sh --init"
fi

echo ""
echo "[*] 初始化完成。"
echo "下一步运行: bash run.sh"
