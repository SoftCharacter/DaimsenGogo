#!/bin/bash
# 股票供应链大屏 - Unix启动脚本

echo "========================================"
echo "  股票供应链大屏 - 一键启动"
echo "========================================"
echo ""

# 获取项目根目录
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON_BIN="$ROOT/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

# 启动后端
echo "[1/2] 正在启动后端服务 (端口 8000)..."
cd "$ROOT" && "$PYTHON_BIN" -m uvicorn backend.main:app --reload --port 8000 --host 0.0.0.0 &
BACKEND_PID=$!

# 等待后端启动
sleep 3

# 启动前端
echo "[2/2] 正在启动前端服务 (端口 5173)..."
cd "$ROOT/frontend" && npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================"
echo "  启动完成！"
echo "  前端: http://localhost:5173"
echo "  后端: http://localhost:8000/docs"
echo "========================================"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 捕获退出信号，清理子进程
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM

# 等待子进程
wait
