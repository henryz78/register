#!/bin/bash
# Grok Free Register — 一键安装脚本
# 用法: bash setup.sh

set -e

install_log="${TMPDIR:-/tmp}/grok-free-register-install.log"
rm -f "$install_log"

run_quiet() {
    if ! "$@" >>"$install_log" 2>&1; then
        echo "[!] 命令执行失败，详细日志: $install_log"
        return 1
    fi
}

run_optional_quiet() {
    "$@" >>"$install_log" 2>&1 || true
}

echo "=== Grok Free Register 安装 ==="

# 检测系统
if [ -f /etc/debian_version ]; then
    echo "[setup] 安装系统依赖 (Debian/Ubuntu)..."
    sudo env DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none apt update -qq >/dev/null 2>&1
    sudo env DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none apt install -y -qq \
        python3 python3-pip python3-venv \
        libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
        libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
        libcairo2 libasound2t64 libnspr4 libnss3 libxshmfence1 \
        >/dev/null 2>&1 || true
    # 兼容旧版 Ubuntu
    sudo env DEBIAN_FRONTEND=noninteractive APT_LISTCHANGES_FRONTEND=none apt install -y -qq \
        libatk1.0-0 libatk-bridge2.0-0 libcups2 libasound2 \
        >/dev/null 2>&1 || true
elif [ -f /etc/redhat-release ]; then
    echo "[setup] 安装系统依赖 (RHEL/CentOS)..."
    run_optional_quiet sudo yum install -y -q \
        python3 python3-pip \
        atk cups-libs libdrm libXcomposite libXdamage libXfixes libXrandr \
        mesa-libgbm pango cairo alsa-lib nspr nss libxshmfence
else
    echo "[setup] 未识别系统，跳过系统依赖。"
fi

echo "[setup] 创建 Python 环境..."
run_quiet python3 -m venv .venv
run_quiet .venv/bin/pip install -q --upgrade pip
run_quiet .venv/bin/pip install -q -r requirements.txt

echo "[setup] 安装 CloakBrowser Chromium..."
run_quiet .venv/bin/python -m cloakbrowser install

mkdir -p keys

echo "[setup] 安装完成。"
echo "运行注册服务: bash run.sh"
