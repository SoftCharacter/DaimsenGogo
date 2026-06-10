"""
AkShare 数据源 client。
只负责调用 AkShare 原始接口，不处理业务缓存和上层模型转换。
"""
import contextlib
import io
import os
from typing import Callable, TypeVar

T = TypeVar("T")

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


def run_without_proxy(func: Callable[[], T]) -> T:
    """临时清除代理环境变量，避免本机代理影响 AkShare 请求。"""
    old_values = {key: os.environ.get(key) for key in _PROXY_ENV_KEYS}
    try:
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
        return func()
    finally:
        for key, value in old_values.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def run_quietly(func: Callable[[], T]) -> T:
    """屏蔽第三方数据源的进度条输出，保留业务日志可读性。"""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return func()


def fetch_a_spot_em():
    """获取东方财富 A 股实时行情 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(ak.stock_zh_a_spot_em))


def fetch_a_spot_sina():
    """获取新浪 A 股实时行情 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(ak.stock_zh_a_spot))


def fetch_hist_tx(symbol: str):
    """获取腾讯历史行情 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(lambda: ak.stock_zh_a_hist_tx(symbol=symbol, adjust="qfq")))


def fetch_daily_sina(symbol: str):
    """获取新浪历史日线 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(lambda: ak.stock_zh_a_daily(symbol=symbol, adjust="qfq")))


def fetch_individual_info(symbol: str):
    """获取上市公司基础信息 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(lambda: ak.stock_individual_info_em(symbol=symbol)))


def fetch_business_ths(symbol: str):
    """获取同花顺主营介绍 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(lambda: ak.stock_zyjs_ths(symbol=symbol)))


def fetch_profile_cninfo(symbol: str):
    """获取巨潮公司资料 DataFrame。"""
    import akshare as ak

    return run_without_proxy(lambda: run_quietly(lambda: ak.stock_profile_cninfo(symbol=symbol)))
