"""
项目接口测试脚本
用于一次性检查本项目依赖的全部关键接口是否可用：
1. 本地配置文件读取
2. OpenAI兼容模型列表接口 /models
3. OpenAI兼容聊天补全接口 /chat/completions
4. Agent工具函数：股票搜索、公司信息、代码验证
5. AkShare财经数据源（通过本项目服务函数）
6. 本地FastAPI接口（如果后端正在运行）
7. SSE分析接口（如果后端正在运行）

运行方式（项目根目录）：
conda run --no-capture-output -n env_reactAgent python scripts/test_interfaces.py

说明：
- 脚本不会修改配置文件。
- API Key 不会完整打印，只打印前后少量字符用于确认是否读取到。
- 本地后端未启动时，HTTP接口测试会提示跳过/失败，但不影响其他测试继续执行。
"""
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

# 将项目根目录加入模块搜索路径，确保可直接导入 backend 包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agent.tools import get_company_info, search_stocks, verify_stock_code
from backend.services.file_service import load_config
from backend.services.llm_client import create_client, chat_complete
from backend.services.stock_service import fetch_quotes, fetch_kline

# 本地后端服务地址
LOCAL_API = "http://127.0.0.1:8000"
# 测试用股票代码，覆盖沪深两市
TEST_CODES = ["SH:601138", "SZ:002261"]


def mask_secret(value: str) -> str:
    """隐藏敏感字符串中间部分，避免在控制台泄露完整API Key"""
    if not value:
        return "<empty>"
    if len(value) <= 12:
        return value[:2] + "***"
    return value[:6] + "..." + value[-4:]


def print_title(title: str) -> None:
    """打印分组标题，提升控制台可读性"""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_result(name: str, ok: bool, detail: str = "") -> None:
    """统一打印单项测试结果"""
    status = "PASS" if ok else "FAIL"
    print(f"[{status}] {name}")
    if detail:
        print(f"       {detail}")


async def test_config() -> Any:
    """测试本地配置文件是否可读取且关键字段完整"""
    print_title("1. 配置文件测试")
    try:
        config = load_config()
        print_result("读取 data/config.json", True)
        print(f"       provider: {config.provider.name}")
        print(f"       base_url: {config.provider.base_url}")
        print(f"       api_key: {mask_secret(config.provider.api_key)}")
        print(f"       selected_model: {config.selected_model}")
        return config
    except Exception as exc:
        print_result("读取 data/config.json", False, repr(exc))
        return None


async def test_llm_models(config: Any) -> None:
    """测试供应商 /models 接口是否可访问"""
    print_title("2. 模型列表接口测试")
    if not config:
        print_result("/models", False, "配置不可用，跳过")
        return

    url = f"{config.provider.base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {config.provider.api_key}"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, headers=headers)
        detail = f"HTTP {resp.status_code}, body={resp.text[:300]}"
        print_result("GET /models", resp.status_code == 200, detail)
    except Exception as exc:
        print_result("GET /models", False, repr(exc))


async def test_llm_chat(config: Any) -> None:
    """测试聊天补全接口是否能真实生成内容"""
    print_title("3. 聊天补全接口测试")
    if not config:
        print_result("chat.completions", False, "配置不可用，跳过")
        return

    try:
        client = create_client(config)
        result = await asyncio.wait_for(
            chat_complete(
                client=client,
                model=config.selected_model,
                messages=[{"role": "user", "content": "只回复OK"}],
                temperature=0,
                max_tokens=16,
            ),
            timeout=60,
        )
        print_result("chat.completions.create", bool(result), f"返回: {result[:200]}")
    except Exception as exc:
        print_result("chat.completions.create", False, repr(exc))


async def test_agent_tools() -> None:
    """测试ReAct Agent直接调用的三个工具函数"""
    print_title("4. Agent工具函数测试")

    try:
        raw = search_stocks("工业富联")
        data = json.loads(raw)
        ok = isinstance(data.get("results"), list)
        print_result("search_stocks('工业富联')", ok, raw[:300])
    except Exception as exc:
        print_result("search_stocks('工业富联')", False, repr(exc))

    try:
        raw = get_company_info("601138")
        data = json.loads(raw)
        ok = "info" in data and bool(data["info"].get("股票简称"))
        print_result("get_company_info('601138')", ok, raw[:300])
    except Exception as exc:
        print_result("get_company_info('601138')", False, repr(exc))

    try:
        raw = verify_stock_code("SH:601138,SZ:002261")
        data = json.loads(raw)
        ok = data.get("total") == 2
        print_result("verify_stock_code(...) ", ok, raw[:300])
    except Exception as exc:
        print_result("verify_stock_code(...) ", False, repr(exc))


async def test_market_services() -> None:
    """测试AkShare财经数据源：实时行情和近一个月日K"""
    print_title("5. AkShare财经数据源测试")

    try:
        quotes = await fetch_quotes(TEST_CODES)
        ok = len(quotes) > 0
        detail = json.dumps([q.model_dump() for q in quotes[:2]], ensure_ascii=False)[:500]
        print_result("AkShare实时行情 fetch_quotes", ok, detail)
    except Exception as exc:
        print_result("AkShare实时行情 fetch_quotes", False, repr(exc))

    try:
        points = await fetch_kline("SH:601138", period="daily", count=22)
        ok = 1 <= len(points) <= 22
        detail = json.dumps([p.model_dump() for p in points], ensure_ascii=False)[:500]
        print_result("AkShare近一个月日K fetch_kline", ok, detail)
    except Exception as exc:
        print_result("AkShare近一个月日K fetch_kline", False, repr(exc))


async def check_local_backend(client: httpx.AsyncClient) -> bool:
    """
    检查本地FastAPI是否健康
    用轻量级 /openapi.json 区分“后端未启动”和“接口内部超时”。
    """
    try:
        resp = await client.get(LOCAL_API + "/openapi.json", timeout=5)
        ok = resp.status_code == 200
        print_result("本地后端健康检查", ok, f"HTTP {resp.status_code}")
        return ok
    except httpx.ConnectError as exc:
        print_result("本地后端健康检查", False, f"后端未启动或端口不可达: {exc}")
        return False
    except httpx.ReadTimeout:
        print_result("本地后端健康检查", False, "后端端口有响应但读取超时，可能事件循环被同步任务阻塞")
        return False
    except Exception as exc:
        print_result("本地后端健康检查", False, repr(exc))
        return False


async def test_local_api() -> None:
    """测试本地FastAPI HTTP接口，要求后端已启动"""
    print_title("6. 本地FastAPI接口测试（需要后端已启动）")

    async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
        if not await check_local_backend(client):
            return

        endpoints = [
            ("GET", "/api/config/", None),
            ("GET", "/api/stocks/quotes?codes=SH:601138,SZ:002261", None),
            ("GET", "/api/stocks/kline?code=SH:601138&period=daily&count=22", None),
            ("GET", "/api/themes/", None),
        ]
        for method, path, body in endpoints:
            try:
                if method == "GET":
                    resp = await client.get(LOCAL_API + path)
                else:
                    resp = await client.post(LOCAL_API + path, json=body)
                ok = 200 <= resp.status_code < 300
                print_result(f"{method} {path}", ok, f"HTTP {resp.status_code}, body={resp.text[:300]}")
            except Exception as exc:
                print_result(f"{method} {path}", False, repr(exc))


async def test_sse_analysis() -> None:
    """测试SSE分析接口是否能推送事件，要求后端已启动"""
    print_title("7. SSE分析接口测试（需要后端已启动）")
    try:
        async with httpx.AsyncClient(timeout=90, trust_env=False) as client:
            if not await check_local_backend(client):
                return

            async with client.stream(
                "POST",
                LOCAL_API + "/api/analysis/run",
                json={"query": "工业富联供应链"},
            ) as resp:
                print_result("POST /api/analysis/run 建立连接", resp.status_code == 200, f"HTTP {resp.status_code}")
                event_count = 0
                async for line in resp.aiter_lines():
                    if line.startswith("event:") or line.startswith("data:"):
                        print("       ", line[:500])
                    if line.startswith("event:"):
                        event_count += 1
                    if event_count >= 6:
                        break
                print_result("SSE事件接收", event_count > 0, f"收到event行数量: {event_count}")
    except Exception as exc:
        print_result("SSE分析接口", False, repr(exc))


async def main() -> None:
    """按依赖顺序执行全部接口测试"""
    config = await test_config()
    await test_llm_models(config)
    await test_llm_chat(config)
    await test_agent_tools()
    await test_market_services()
    await test_local_api()
    await test_sse_analysis()


if __name__ == "__main__":
    asyncio.run(main())
