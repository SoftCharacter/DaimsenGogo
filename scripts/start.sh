#!/usr/bin/env bash
set -e

# 股票供应链大屏 - Unix 一键启动脚本

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
CONDA_ENV_NAME="env_reactAgent"
DEPS_DIR="$ROOT/.runlogs/deps"
BACKEND_DEPS_MARKER="$DEPS_DIR/backend.requirements.sha"
FRONTEND_DEPS_MARKER="$DEPS_DIR/frontend.package.sha"

echo "========================================"
echo "  股票供应链大屏 - 一键启动"
echo "========================================"
echo ""
echo "[准备] 正在检查运行环境..."
echo ""

file_hash() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
        return 0
    fi
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
        return 0
    fi
    cksum "$1" | awk '{print $1 "-" $2}'
}

read_marker() {
    if [ -f "$1" ]; then
        cat "$1"
    fi
}

ensure_python() {
    if ! command -v conda >/dev/null 2>&1; then
        echo "[错误] 找不到 conda，请先安装 Anaconda。"
        return 1
    fi

    if ! conda run --no-capture-output -n "$CONDA_ENV_NAME" python -V >/dev/null 2>&1; then
        echo "[环境] 未找到 conda 环境 $CONDA_ENV_NAME，正在创建..."
        conda create -n "$CONDA_ENV_NAME" python=3.11 -y
    fi
}

install_backend_deps() {
    local current_hash
    current_hash="$(file_hash "$BACKEND_DIR/requirements.txt")"
    if [ "$(read_marker "$BACKEND_DEPS_MARKER")" = "$current_hash" ]; then
        echo "[依赖] 后端依赖未变化，跳过安装。"
        return 0
    fi

    echo "[依赖] 检测到后端依赖需要安装或更新..."
    conda run --no-capture-output -n "$CONDA_ENV_NAME" python -m pip install -r "$BACKEND_DIR/requirements.txt"
    mkdir -p "$DEPS_DIR"
    printf "%s" "$current_hash" > "$BACKEND_DEPS_MARKER"
}

install_frontend_deps() {
    if ! command -v npm >/dev/null 2>&1; then
        echo "[错误] 找不到 npm，请先安装 Node.js。"
        return 1
    fi

    local current_hash
    current_hash="$(file_hash "$FRONTEND_DIR/package.json")"
    if [ -f "$FRONTEND_DIR/package-lock.json" ]; then
        current_hash="$current_hash-$(file_hash "$FRONTEND_DIR/package-lock.json")"
    fi
    if [ -d "$FRONTEND_DIR/node_modules" ] && [ "$(read_marker "$FRONTEND_DEPS_MARKER")" = "$current_hash" ]; then
        echo "[依赖] 前端依赖未变化，跳过安装。"
        return 0
    fi

    echo "[依赖] 检测到前端依赖需要安装或更新..."
    cd "$FRONTEND_DIR"
    if [ -f package-lock.json ]; then
        npm ci
    else
        npm install
    fi
    mkdir -p "$DEPS_DIR"
    printf "%s" "$current_hash" > "$FRONTEND_DEPS_MARKER"
}

fail() {
    echo ""
    echo "启动失败，请检查上面的报错信息。"
    exit 1
}

ensure_python || fail
install_backend_deps || fail
install_frontend_deps || fail

echo ""
echo "[启动] 正在启动后端和前端..."
echo ""
cd "$ROOT"
conda run --no-capture-output -n "$CONDA_ENV_NAME" python scripts/launcher.py
