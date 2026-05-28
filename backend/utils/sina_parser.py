"""
新浪API解析器
负责GBK解码和行情字段解析，将新浪财经API原始文本
转换为标准的 StockQuote 数据模型
"""
import re
from typing import Optional

from backend.models.stock_models import StockQuote


def code_to_sina(code: str) -> str:
    """
    将统一代码转换为新浪行情API格式
    统一格式使用大写前缀+冒号分隔，新浪格式为小写前缀直连
    示例: 'SZ:002261' -> 'sz002261'
          'SH:600000' -> 'sh600000'
    """
    # 以冒号分割市场前缀和股票代码
    parts = code.split(":")
    if len(parts) != 2:
        return code.lower()
    market, num = parts
    # 拼接为新浪格式：小写市场前缀 + 数字代码
    return f"{market.lower()}{num}"


def sina_to_code(sina_code: str) -> str:
    """
    新浪格式转统一代码格式
    新浪返回的代码为小写前缀直连数字，需转换为统一的大写+冒号格式
    示例: 'sz002261' -> 'SZ:002261'
          'sh600000' -> 'SH:600000'
    """
    # 新浪代码固定为2位市场前缀 + 6位数字代码
    if len(sina_code) < 8:
        return sina_code.upper()
    market = sina_code[:2].upper()
    num = sina_code[2:]
    return f"{market}:{num}"


def format_volume(volume: float) -> str:
    """
    格式化成交额为易读的中文单位
    规则:
      >= 1亿 -> "X.XX亿"
      >= 1万 -> "X.XX万"
      否则  -> 保留两位小数的原值字符串
    """
    if volume >= 1e8:
        # 亿级别：除以1亿并保留两位小数
        return f"{volume / 1e8:.2f}亿"
    if volume >= 1e4:
        # 万级别：除以1万并保留两位小数
        return f"{volume / 1e4:.2f}万"
    # 小于1万：直接输出数字
    return f"{volume:.2f}"


def parse_sina_line(line: str) -> Optional[StockQuote]:
    """
    解析新浪行情API返回的单行原始文本
    新浪API每行格式为:
      var hq_str_sz002261="拓维信息,18.90,18.74,19.28,...";
    字段顺序(共33个，以逗号分隔):
      0:名称, 1:今开, 2:昨收, 3:当前价, 4:最高, 5:最低,
      6:买一价, 7:卖一价, 8:成交量(股), 9:成交额(元),
      ...
      30:日期, 31:时间
    返回:
      解析成功返回 StockQuote 实例，失败返回 None
    """
    # 使用正则提取新浪代码和引号内的数据体
    match = re.search(r"hq_str_(\w+)=\"(.+?)\"", line)
    if not match:
        return None

    sina_code = match.group(1)  # 如 'sz002261'
    data_str = match.group(2)   # 逗号分隔的字段字符串

    # 按逗号切分所有字段
    fields = data_str.split(",")
    # 新浪行情至少需要32个字段才算完整数据
    if len(fields) < 32:
        return None

    try:
        # 提取关键字段并转换为浮点数
        name = fields[0]                    # 股票名称
        open_price = float(fields[1])       # 今日开盘价
        prev_close = float(fields[2])       # 昨日收盘价
        current = float(fields[3])          # 当前最新价
        high = float(fields[4])             # 今日最高价
        low = float(fields[5])              # 今日最低价
        volume_amount = float(fields[9])    # 成交额(元)
        date_str = fields[30]               # 日期
        time_str = fields[31]               # 时间

        # 计算涨跌额和涨跌幅
        change = current - prev_close
        # 防止昨收为0导致除零错误
        change_pct = (change / prev_close * 100) if prev_close else 0.0

        # 构建统一代码格式
        code = sina_to_code(sina_code)

        return StockQuote(
            code=code,
            name=name,
            current_price=round(current, 2),
            prev_close=round(prev_close, 2),
            open_price=round(open_price, 2),
            high=round(high, 2),
            low=round(low, 2),
            change=round(change, 2),
            change_percent=round(change_pct, 2),
            volume=volume_amount,
            volume_display=format_volume(volume_amount),
            timestamp=f"{date_str} {time_str}",
        )
    except (ValueError, IndexError):
        # 字段格式异常时返回None，不抛出异常
        return None
