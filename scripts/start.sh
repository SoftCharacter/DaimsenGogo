#!/usr/bin/env bash
set -e

# 股票供应链大屏 - Unix 一键启动脚本

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND_DIR="$ROOT/backend"
FRONTEND_DIR="$ROOT/frontend"
VENV_DIR="$ROOT/.venv"
PYTHON_BIN=""
USE_CONDA="0"
NEED_BACKEND_DEPS_INSTALL="0"
CONDA_ENV_NAME="env_reactAgent"

echo "========================================"
echo "  股票供应链大屏 - 一键启动"
echo "========================================"
echo ""
echo "[准备] 正在检查运行环境..."
echo ""

ensure_python() {
    if command -v conda >/dev/null 2>&1; then
        if ! conda run --no-capture-output -n "$CONDA_ENV_NAME" python -V >/dev/null 2>&1; then
            echo "[环境] 未找到 conda 环境 $CONDA_ENV_NAME，正在创建..."
            conda create -n "$CONDA_ENV_NAME" python=3.11 -y
            NEED_BACKEND_DEPS_INSTALL="1"
        fi
        USE_CONDA="1"
        return 0
    fi

    if [ -x "$VENV_DIR/bin/python" ]; then
        PYTHON_BIN="$VENV_DIR/bin/python"
        return 0
    fi

    if command -v python3 >/dev/null 2>&1; then
        echo "[环境] 正在创建本地 Python 虚拟环境 .venv ..."
        python3 -m venv "$VENV_DIR"
        NEED_BACKEND_DEPS_INSTALL="1"
        PYTHON_BIN="$VENV_DIR/bin/python"
        return 0
    fi

    if command -v python >/dev/null 2>&1; then
        echo "[环境] 正在创建本地 Python 虚拟环境 .venv ..."
        python -m venv "$VENV_DIR"
        NEED_BACKEND_DEPS_INSTALL="1"
        PYTHON_BIN="$VENV_DIR/bin/python"
        return 0
    fi

    echo "[错误] 找不到 conda、python3 或 python，请先安装 Python 或 Anaconda。"
    return 1
}

install_backend_deps() {
    if [ "$NEED_BACKEND_DEPS_INSTALL" != "1" ]; then
        echo "[依赖] 已找到现有 Python 环境，跳过后端依赖安装。"
        return 0
    fi

    echo "[依赖] 安装后端 Python 依赖..."
    if [ "$USE_CONDA" = "1" ]; then
        conda run --no-capture-output -n "$CONDA_ENV_NAME" python -m pip install -r "$BACKEND_DIR/requirements.txt"
    else
        "$PYTHON_BIN" -m pip install -r "$BACKEND_DIR/requirements.txt"
    fi
}

install_frontend_deps() {
    if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
        if ! command -v npm >/dev/null 2>&1; then
            echo "[错误] 找不到 npm，请先安装 Node.js。"
            return 1
        fi

        echo "[依赖] 安装前端依赖..."
        cd "$FRONTEND_DIR"
        if [ -f package-lock.json ]; then
            npm ci
        else
            npm install
        fi
    fi
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
if [ "$USE_CONDA" = "1" ]; then
    conda run --no-capture-output -n "$CONDA_ENV_NAME" python scripts/launcher.py
else
    "$PYTHON_BIN" scripts/launcher.py
fi
