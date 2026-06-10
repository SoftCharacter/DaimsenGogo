import tempfile
import unittest
from pathlib import Path

from backend.models.config_models import AppConfig
from backend.models.diagnosis_models import StockDiagnosisResponse
from backend.models.stock_models import KLinePoint
from backend.routers import stock_router
from backend.services import akshare_adapter, stock_diagnosis_service, stock_service


class StockServiceImplicitRulesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original_kline_cache = stock_service._kline_cache
        self.original_search_cache = stock_service._stock_search_cache
        self.original_fetch_recent_daily_kline_sync = stock_service.fetch_recent_daily_kline_sync
        self.original_get_stock_list = stock_service.get_stock_list
        stock_service._kline_cache = {}
        stock_service._stock_search_cache = {}

    def tearDown(self):
        stock_service._kline_cache = self.original_kline_cache
        stock_service._stock_search_cache = self.original_search_cache
        stock_service.fetch_recent_daily_kline_sync = self.original_fetch_recent_daily_kline_sync
        stock_service.get_stock_list = self.original_get_stock_list

    async def test_fetch_kline_ignores_period_and_count_for_cache_key(self):
        calls: list[tuple[str, str | None]] = []
        points = [KLinePoint(date="2026-01-01", open=1, high=2, low=0.5, close=1.5, volume=100)]

        def fake_fetch_recent_daily_kline_sync(code: str, task_id: str | None = None):
            calls.append((code, task_id))
            return points

        stock_service.fetch_recent_daily_kline_sync = fake_fetch_recent_daily_kline_sync

        first = await stock_service.fetch_kline("SZ:002261", period="daily", count=22, task_id="task_1")
        second = await stock_service.fetch_kline("SZ:002261", period="60min", count=500, task_id="task_1")

        self.assertEqual(first, points)
        self.assertEqual(second, points)
        self.assertEqual(calls, [("SZ:002261", "task_1")])
        self.assertIn("task_1|SZ:002261|daily|month", stock_service._kline_cache)
        self.assertEqual(stock_service.MONTH_KLINE_PERIOD, "daily")
        self.assertEqual(stock_service.MONTH_KLINE_COUNT, 22)

    def test_kline_route_documents_fixed_month_daily_rule(self):
        route = next(route for route in stock_router.router.routes if getattr(route, "path", "") == "/kline")
        descriptions = {param.name: param.field_info.description for param in route.dependant.query_params}

        self.assertEqual(descriptions["period"], "兼容参数；当前固定返回 daily 日K")
        self.assertEqual(descriptions["count"], "兼容参数；当前固定返回最近22个交易日日K")

    async def test_fetch_kline_returns_cached_data_when_external_source_fails(self):
        calls = 0
        points = [KLinePoint(date="2026-01-01", open=1, high=2, low=0.5, close=1.5, volume=100)]

        def fake_fetch_recent_daily_kline_sync(code: str, task_id: str | None = None):
            nonlocal calls
            calls += 1
            if calls == 1:
                return points
            raise RuntimeError("外部数据源失败")

        stock_service.fetch_recent_daily_kline_sync = fake_fetch_recent_daily_kline_sync
        await stock_service.fetch_kline("SH:600000", task_id="task_2")
        stock_service._kline_cache["task_2|SH:600000|daily|month"] = (0, points)

        fallback = await stock_service.fetch_kline("SH:600000", period="daily", count=22, task_id="task_2")

        self.assertEqual(fallback, points)
        self.assertEqual(calls, 2)

    async def test_search_stocks_returns_zero_current_price(self):
        def fake_get_stock_list(task_id: str | None = None):
            return [
                {"code": "SZ:002261", "name": "拓维信息"},
                {"code": "SH:600000", "name": "浦发银行"},
            ]

        stock_service.get_stock_list = fake_get_stock_list

        results = await stock_service.search_stocks("拓维", task_id="task_3")

        self.assertEqual(results, [{"code": "SZ:002261", "name": "拓维信息", "current_price": 0.0}])


class AkshareCacheVisibilityTest(unittest.TestCase):
    def test_cache_label_includes_specific_cache_file_name(self):
        label = akshare_adapter._cache_label(Path("task_1") / "akshare_kline_cache.json")

        self.assertEqual(label, "akshare:akshare_kline_cache")


class StockDiagnosisImplicitRulesTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_cache_dir = stock_diagnosis_service._DIAGNOSIS_CACHE_DIR
        self.original_last_cache_cleanup = stock_diagnosis_service._last_cache_cleanup
        self.original_load_config = stock_diagnosis_service.load_config
        self.original_create_client = stock_diagnosis_service.create_client
        self.original_chat_complete = stock_diagnosis_service.chat_complete
        stock_diagnosis_service._DIAGNOSIS_CACHE_DIR = Path(self.temp_dir.name) / "diagnosis_cache"
        stock_diagnosis_service._last_cache_cleanup = 0.0

    def tearDown(self):
        stock_diagnosis_service._DIAGNOSIS_CACHE_DIR = self.original_cache_dir
        stock_diagnosis_service._last_cache_cleanup = self.original_last_cache_cleanup
        stock_diagnosis_service.load_config = self.original_load_config
        stock_diagnosis_service.create_client = self.original_create_client
        stock_diagnosis_service.chat_complete = self.original_chat_complete
        self.temp_dir.cleanup()

    async def test_try_llm_summaries_returns_error_status_and_fallback_report_on_llm_failure(self):
        config = AppConfig()
        config.provider.api_key = "api-key"
        config.provider.base_url = "https://provider.example.com/v1"
        config.selected_model = "model-a"
        stock_diagnosis_service.load_config = lambda: config
        stock_diagnosis_service.create_client = lambda loaded_config: object()

        async def failing_chat_complete(*args, **kwargs):
            raise RuntimeError("LLM失败")

        stock_diagnosis_service.chat_complete = failing_chat_complete

        event_summary, diagnosis_report, llm_status = await stock_diagnosis_service._try_llm_summaries(
            "测试股票",
            "SZ:002261",
            [],
            [],
            [],
            [],
            None,
        )

        self.assertEqual(llm_status, "error")
        self.assertIsInstance(event_summary, str)
        self.assertIsInstance(diagnosis_report, str)
        self.assertNotEqual(diagnosis_report, "")

    def test_write_diagnosis_cache_skips_failed_enhanced_response(self):
        response = StockDiagnosisResponse(
            code="SZ:002261",
            name="拓维信息",
            generated_at="2026-06-09 00:00:00",
            source="xueqiu_akshare",
            timings_ms={},
            moving_averages=[],
            macd=[],
            shareholders=[],
            net_profit=[],
            events=[],
            chip_distribution=None,
            event_summary="",
            diagnosis_report="fallback",
            llm_status="error",
            data_errors={},
        )

        stock_diagnosis_service._write_diagnosis_cache(response, include_llm=True)

        self.assertFalse(stock_diagnosis_service._DIAGNOSIS_CACHE_DIR.exists())


if __name__ == "__main__":
    unittest.main()
