"""
统一启动器 - 单窗口管理前后端进程
在一个终端窗口中启动FastAPI后端和Vite前端开发服务器，
Ctrl+C或终端关闭时自动终止所有子进程并释放端口。
"""
import os
import sys
import signal
import subprocess
import time
import urllib.request

# 项目根目录（launcher.py所在的scripts/的上级目录）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 前端目录
FRONTEND_DIR = os.path.join(ROOT, "frontend")

# 子进程列表
_processes: list[subprocess.Popen] = []


def _kill_all():
    """终止所有子进程并释放资源"""
    for proc in _processes:
        if proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
            except Exception:
                pass
    _processes.clear()


def _signal_handler(_sig, _frame):
    """信号处理器 - Ctrl+C时优雅退出"""
    print("\n[launcher] Shutting down...")
    _kill_all()
    sys.exit(0)


def _wait_backend_ready(proc: subprocess.Popen, timeout: float = 30.0) -> bool:
    """等待后端端口可用，避免前端先启动导致代理报错。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/docs", timeout=1):
                return True
        except Exception:
            time.sleep(0.5)
    return False


def main():
    """主函数 - 启动前后端服务并监控运行状态"""
    # 注册信号处理
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)

    # 设置子进程环境变量
    env = os.environ.copy()
    env["STOCK_LAUNCHER"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    print("========================================")
    print("  Stock Supply Chain Dashboard")
    print("========================================")
    print()

    # 启动后端（FastAPI + uvicorn）
    print("[1/2] Starting backend (port 8000)...")
    backend = subprocess.Popen(
        [
            sys.executable, "-m", "uvicorn",
            "backend.main:app",
            "--port", "8000", "--host", "0.0.0.0",
        ],
        cwd=ROOT,
        env=env,
    )
    _processes.append(backend)

    # 等待后端真正就绪
    if not _wait_backend_ready(backend):
        print("[launcher] Backend failed to become ready, shutting down...")
        _kill_all()
        sys.exit(1)

    # 启动前端（Vite dev server）
    print("[2/2] Starting frontend (port 5173)...")
    # Windows下需要通过npm.cmd调用
    npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    frontend = subprocess.Popen(
        [npm_cmd, "run", "dev"],
        cwd=FRONTEND_DIR,
        env=env,
    )
    _processes.append(frontend)

    print()
    print("========================================")
    print("  All started!")
    print("  Frontend: http://localhost:5173")
    print("  Backend:  http://localhost:8000/docs")
    print("  Press Ctrl+C to stop all services")
    print("========================================")
    print()

    # 主循环：监控子进程状态
    try:
        while True:
            # 检查后端是否意外退出
            if backend.poll() is not None:
                print("[launcher] Backend exited, shutting down...")
                break
            # 检查前端是否意外退出
            if frontend.poll() is not None:
                print("[launcher] Frontend exited, shutting down...")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[launcher] Ctrl+C received, shutting down...")
    finally:
        _kill_all()
        print("[launcher] All services stopped.")


if __name__ == "__main__":
    main()
