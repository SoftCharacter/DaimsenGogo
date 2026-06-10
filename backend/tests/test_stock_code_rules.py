import unittest

from backend.agent import hybrid_loop, tools
from backend.services import akshare_adapter


class StockCodeRulesTest(unittest.TestCase):
    def test_akshare_format_stock_code_pads_and_routes_by_prefix(self):
        cases = {
            "600000": "SH:600000",
            "000001": "SZ:000001",
            "300750": "SZ:300750",
            "430047": "BJ:430047",
            "830799": "BJ:830799",
            "12345": "SZ:012345",
            "900001": "SZ:900001",
        }

        for raw_code, expected in cases.items():
            with self.subTest(raw_code=raw_code):
                self.assertEqual(akshare_adapter.format_stock_code(raw_code), expected)

    def test_akshare_extract_numeric_code_returns_first_six_digits_or_trimmed_input(self):
        cases = {
            "SH:601138": "601138",
            "SZ002261": "002261",
            "股票 300750 宁德时代": "300750",
            "abc": "abc",
            "  abc  ": "abc",
        }

        for raw_code, expected in cases.items():
            with self.subTest(raw_code=raw_code):
                self.assertEqual(akshare_adapter.extract_numeric_code(raw_code), expected)

    def test_tools_normalize_stock_code_accepts_common_llm_formats(self):
        cases = {
            "SH:600000": "SH:600000",
            "sh600000": "SH:600000",
            "SZ：002261": "SZ:002261",
            "  'bj 430047'  ": "BJ:430047",
            "600000.SH": "SH:600000",
            "sz:002261": "SZ:002261",
            "未知文本": "未知文本",
        }

        for raw_code, expected in cases.items():
            with self.subTest(raw_code=raw_code):
                self.assertEqual(tools._normalize_stock_code(raw_code), expected)

    def test_tools_split_stock_codes_extracts_prefixed_or_plain_codes(self):
        self.assertEqual(
            tools._split_stock_codes("SH:600000, sz002261\nBJ：430047 300750"),
            ["SH:600000", "sz002261", "BJ：430047", "300750"],
        )
        self.assertEqual(
            tools._split_stock_codes("foo,bar；baz"),
            ["foo", "bar", "baz"],
        )

    def test_hybrid_normalize_stock_code_returns_none_for_unrecognized_input(self):
        cases = {
            "SH:600000": "SH:600000",
            "sh600000": "SH:600000",
            "SZ：002261": "SZ:002261",
            "600000.SH": "SH:600000",
            "纯数字 300750": "SZ:300750",
            "430047": "BJ:430047",
            "未知文本": None,
        }

        for raw_code, expected in cases.items():
            with self.subTest(raw_code=raw_code):
                self.assertEqual(hybrid_loop._normalize_stock_code(raw_code), expected)


if __name__ == "__main__":
    unittest.main()
