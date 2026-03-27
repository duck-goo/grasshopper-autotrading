# backend/strategy/condition.py
import pandas as pd
import numpy as np

def calculate_rsi(prices: list, period: int = 14) -> float:
    """RSI 계산"""
    if len(prices) < period + 1:
        return None

    df = pd.Series(prices)
    delta = df.diff()
    gain = delta.where(delta > 0, 0).rolling(period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return round(rsi.iloc[-1], 2)

def calculate_macd(prices: list):
    """MACD 계산"""
    if len(prices) < 26:
        return None, None, None

    df = pd.Series(prices)
    ema12 = df.ewm(span=12, adjust=False).mean()
    ema26 = df.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    return round(macd.iloc[-1], 2), round(signal.iloc[-1], 2), round(hist.iloc[-1], 2)

def calculate_ma(prices: list, period: int) -> float:
    """이동평균선 계산"""
    if len(prices) < period:
        return None
    return round(sum(prices[-period:]) / period, 2)

def check_condition(condition: dict, prices: list, current_price: float) -> bool:
    """
    조건식 체크
    condition 예시:
    {"type": "RSI", "operator": "<=", "value": 30}
    {"type": "MA_CROSS", "short": 5, "long": 20}
    {"type": "PRICE", "operator": ">=", "value": 80000}
    """
    ctype = condition.get("type")

    if ctype == "RSI":
        rsi = calculate_rsi(prices)
        if rsi is None:
            return False
        return _compare(rsi, condition["operator"], condition["value"])

    elif ctype == "MACD":
        macd, signal, hist = calculate_macd(prices)
        if macd is None:
            return False
        # MACD 골든크로스 (MACD > Signal)
        return macd > signal

    elif ctype == "MA_CROSS":
        short_ma = calculate_ma(prices, condition["short"])
        long_ma = calculate_ma(prices, condition["long"])
        if short_ma is None or long_ma is None:
            return False
        return short_ma > long_ma

    elif ctype == "PRICE":
        return _compare(current_price, condition["operator"], condition["value"])

    return False

def _compare(value, operator: str, target) -> bool:
    """비교 연산자 처리"""
    if operator == ">=":
        return value >= target
    elif operator == "<=":
        return value <= target
    elif operator == ">":
        return value > target
    elif operator == "<":
        return value < target
    elif operator == "==":
        return value == target
    return False