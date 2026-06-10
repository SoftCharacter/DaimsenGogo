"""股票代码格式化与归一化工具。"""
import re

_MARKET_CODE_PATTERN = re.compile(r"\b(?:SH|SZ|BJ)[:：]?\s*(\d{6})\b", re.IGNORECASE)
_DIGIT_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_STOCK_CODE_SPLIT_PATTERN = re.compile(r"[,，、;；\s]+")
_STOCK_CODE_TOKEN_PATTERN = re.compile(r"(?:SH|SZ|BJ)?\s*[:：]?\s*\d{6}", flags=re.IGNORECASE)


def extract_numeric_code(code: str) -> str:
    """从统一代码或混合文本中提取首个6位数字代码。"""
    match = re.search(r"\d{6}", code)
    return match.group() if match else code.strip()


def format_stock_code(raw_code: str) -> str:
    """将数字股票代码转换为项目统一的市场前缀格式。"""
    code = str(raw_code).zfill(6)
    if code.startswith("6"):
        return f"SH:{code}"
    if code.startswith(("0", "3")):
        return f"SZ:{code}"
    if code.startswith(("4", "8")):
        return f"BJ:{code}"
    return f"SZ:{code}"


def normalize_stock_code(raw_code: str, *, strict: bool = False) -> str | None:
    """兼容常见股票代码写法，并归一化为 SH/SZ/BJ:000000 格式。"""
    cleaned = raw_code.strip().strip('"').strip("'").strip().upper().replace("：", ":")
    market_match = _MARKET_CODE_PATTERN.search(cleaned)
    if market_match:
        prefix = cleaned[:market_match.start(1)].replace(" ", "").replace(":", "")[-2:]
        return f"{prefix}:{market_match.group(1)}"

    digit_match = _DIGIT_CODE_PATTERN.search(cleaned)
    if digit_match:
        return format_stock_code(digit_match.group())

    return None if strict else cleaned


def split_stock_codes(codes: str) -> list[str]:
    """从逗号、空格、换行或 JSON 样式文本中提取股票代码片段。"""
    matches = _STOCK_CODE_TOKEN_PATTERN.findall(codes)
    if matches:
        return [item.strip() for item in matches]
    return [item.strip() for item in _STOCK_CODE_SPLIT_PATTERN.split(codes) if item.strip()]


def is_valid_market_code(code: str) -> bool:
    """判断代码是否为项目内部标准格式。"""
    return bool(re.fullmatch(r"(?:SH|SZ|BJ):\d{6}", code))
